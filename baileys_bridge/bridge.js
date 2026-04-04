/**
 * ScreenerClaw — Baileys WhatsApp Bridge
 *
 * Runs as a Node.js sidecar. Connects your WhatsApp account via QR code scan
 * (WhatsApp Web protocol, reverse-engineered by @whiskeysockets/baileys).
 *
 * On first run: scan the QR code that appears in the terminal.
 * Subsequent runs: reconnects automatically using saved credentials.
 *
 * HTTP API (for Python):
 *   GET  /status          — connection status + linked JID
 *   GET  /qr              — current QR code string (before auth)
 *   POST /send            — send a WhatsApp message
 *   POST /send-typing     — send typing indicator
 *   POST /webhook/config  — update Python webhook URL at runtime
 *
 * Incoming messages → POST to PYTHON_WEBHOOK_URL
 *
 * Env vars:
 *   PORT                — HTTP API port (default: 3000)
 *   PYTHON_WEBHOOK_URL  — where to POST incoming messages (default: http://localhost:8080/whatsapp/webhook)
 *   AUTH_DIR            — path to store session files (default: ./auth_info_baileys)
 *   LOG_LEVEL           — pino log level (default: info)
 */

import express from 'express'
import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  jidNormalizedUser,
} from '@whiskeysockets/baileys'
import qrcodeTerminal from 'qrcode-terminal'
import axios from 'axios'
import pino from 'pino'
import { existsSync, mkdirSync, rmSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

// ── Config ────────────────────────────────────────────────────────────────────

const PORT = parseInt(process.env.PORT || '3000', 10)
const AUTH_DIR = process.env.AUTH_DIR || join(__dirname, 'auth_info_baileys')
let PYTHON_WEBHOOK_URL = process.env.PYTHON_WEBHOOK_URL || 'http://localhost:8080/whatsapp/webhook'
const LOG_LEVEL = process.env.LOG_LEVEL || 'info'

// Ensure auth dir exists
if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true })

// ── Logger (minimal output — QR code must be readable) ───────────────────────

const logger = pino({
  level: LOG_LEVEL,
  transport: { target: 'pino-pretty', options: { colorize: true, ignore: 'pid,hostname' } },
}).child({ module: 'baileys-bridge' })

// ── State ─────────────────────────────────────────────────────────────────────

let sock = null
let currentQR = null
let connectionState = 'disconnected'  // 'disconnected' | 'connecting' | 'open'
let linkedJid = null   // phone-based JID number, e.g. "917021564726"
let linkedLid = null   // LID-based JID number, e.g. "235269852786714"
let reconnectAttempts = 0
const MAX_RECONNECT_DELAY_MS = 30_000

// Bad MAC / session corruption tracking
let badMacCount = 0
const BAD_MAC_THRESHOLD = 5  // wipe session after this many consecutive failures

function clearSessionAndRestart(reason) {
  logger.warn('Session corrupted (%s). Wiping auth_info_baileys/ and requesting fresh QR scan...', reason)
  console.log('\n' + '!'.repeat(60))
  console.log('  SESSION CORRUPTED — Clearing saved session...')
  console.log('  A new QR code will appear. Please scan it with WhatsApp.')
  console.log('!'.repeat(60) + '\n')
  try {
    rmSync(AUTH_DIR, { recursive: true, force: true })
    mkdirSync(AUTH_DIR, { recursive: true })
    logger.info('Auth directory cleared. Restarting Baileys with fresh session...')
  } catch (err) {
    logger.error({ err }, 'Failed to clear auth directory')
  }
  badMacCount = 0
  reconnectAttempts = 0
  setTimeout(startBaileys, 1000)
}

// ── Express ───────────────────────────────────────────────────────────────────

const app = express()
app.use(express.json())

/** GET /status — connection status */
app.get('/status', (req, res) => {
  res.json({
    connected: connectionState === 'open',
    state: connectionState,
    jid: linkedJid,
    webhook: PYTHON_WEBHOOK_URL,
  })
})

/** GET /qr — current QR string (null if already authed) */
app.get('/qr', (req, res) => {
  if (currentQR) {
    res.json({ qr: currentQR, hint: 'Scan with WhatsApp > Settings > Linked Devices > Link a Device' })
  } else if (connectionState === 'open') {
    res.json({ message: 'Already authenticated', jid: linkedJid })
  } else {
    res.json({ message: 'QR not yet generated — bridge may still be connecting' })
  }
})

/** POST /send — send a WhatsApp message
 *  Body: { phone: "91XXXXXXXXXX", message: "text" }
 *  For groups: { jid: "GROUPID@g.us", message: "text" }
 */
app.post('/send', async (req, res) => {
  if (connectionState !== 'open') {
    return res.status(503).json({ error: 'WhatsApp not connected', state: connectionState })
  }

  const { phone, jid, message } = req.body
  if (!message) return res.status(400).json({ error: 'message is required' })

  const targetJid = jid || (phone ? `${phone.replace(/\D/g, '')}@s.whatsapp.net` : null)
  if (!targetJid) return res.status(400).json({ error: 'phone or jid is required' })

  try {
    await sock.sendMessage(targetJid, { text: message })
    res.json({ success: true, to: targetJid })
  } catch (err) {
    logger.error({ err }, 'Send failed')
    res.status(500).json({ error: err.message })
  }
})

/** POST /send-typing — send typing indicator (cosmetic) */
app.post('/send-typing', async (req, res) => {
  const { phone, jid } = req.body
  const targetJid = jid || `${(phone || '').replace(/\D/g, '')}@s.whatsapp.net`
  try {
    await sock.sendPresenceUpdate('composing', targetJid)
    setTimeout(() => sock.sendPresenceUpdate('paused', targetJid), 3000)
    res.json({ success: true })
  } catch (err) {
    res.status(500).json({ error: err.message })
  }
})

/** POST /send-document — send a PDF or other file as a WhatsApp document
 *  Body: { phone, fileName, data (base64), mimetype, caption }
 *  For groups: { jid, ... }
 */
app.post('/send-document', async (req, res) => {
  if (connectionState !== 'open') {
    return res.status(503).json({ error: 'WhatsApp not connected', state: connectionState })
  }

  const { phone, jid, fileName, data, mimetype, caption } = req.body
  if (!data) return res.status(400).json({ error: 'data (base64) is required' })

  const targetJid = jid || (phone ? `${phone.replace(/\D/g, '')}@s.whatsapp.net` : null)
  if (!targetJid) return res.status(400).json({ error: 'phone or jid is required' })

  try {
    const buffer = Buffer.from(data, 'base64')
    const msgContent = {
      document: buffer,
      mimetype: mimetype || 'application/pdf',
      fileName: fileName || 'report.pdf',
    }
    if (caption) msgContent.caption = caption
    await sock.sendMessage(targetJid, msgContent)
    res.json({ success: true, to: targetJid, fileName })
  } catch (err) {
    logger.error({ err }, 'Send document failed')
    res.status(500).json({ error: err.message })
  }
})

/** POST /webhook/config — update Python webhook URL at runtime */
app.post('/webhook/config', (req, res) => {
  const { url } = req.body
  if (!url) return res.status(400).json({ error: 'url is required' })
  PYTHON_WEBHOOK_URL = url
  logger.info('Webhook URL updated: %s', url)
  res.json({ success: true, webhook: PYTHON_WEBHOOK_URL })
})

// ── Baileys Connection ────────────────────────────────────────────────────────

async function startBaileys() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const { version } = await fetchLatestBaileysVersion()

  logger.info('Baileys version: %s', version.join('.'))
  connectionState = 'connecting'

  // Custom Baileys logger — silent except we intercept Bad MAC errors
  const baileysLogger = pino({ level: 'silent' })
  const _origError = baileysLogger.error.bind(baileysLogger)
  baileysLogger.error = (obj, ...args) => {
    const msg = typeof obj === 'string' ? obj : (obj?.msg || JSON.stringify(obj))
    if (msg && msg.toLowerCase().includes('bad mac')) {
      badMacCount++
      logger.warn('Bad MAC decryption error #%d/%d', badMacCount, BAD_MAC_THRESHOLD)
      if (badMacCount >= BAD_MAC_THRESHOLD) {
        clearSessionAndRestart('Bad MAC x' + BAD_MAC_THRESHOLD)
        return
      }
    }
    // Don't forward to pino (keep silent)
  }

  sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,   // we handle QR ourselves
    logger: baileysLogger,
    browser: ['ScreenerClaw', 'Chrome', '1.0.0'],
    connectTimeoutMs: 60_000,
    defaultQueryTimeoutMs: 60_000,
  })

  // ── Persist credentials on update ────────────────────────────────────────

  sock.ev.on('creds.update', saveCreds)

  // ── Connection state + QR code ────────────────────────────────────────────

  sock.ev.on('connection.update', (update) => {
    const { connection, qr, lastDisconnect, isNewLogin } = update

    if (qr) {
      currentQR = qr
      connectionState = 'connecting'
      console.log('\n' + '='.repeat(60))
      console.log('  SCREENER CLAW — Scan this QR code with WhatsApp')
      console.log('  WhatsApp > Settings > Linked Devices > Link a Device')
      console.log('='.repeat(60) + '\n')
      qrcodeTerminal.generate(qr, { small: true })
      console.log('\n  Waiting for scan...\n')
    }

    if (connection === 'open') {
      currentQR = null
      connectionState = 'open'
      reconnectAttempts = 0
      badMacCount = 0
      linkedJid = jidNormalizedUser(sock.user?.id || '')
      // Also capture LID (Linked ID) — WhatsApp uses this for self-chat on newer clients
      const rawLid = sock.user?.lid || ''
      linkedLid = rawLid ? rawLid.split(':')[0].split('@')[0] : null
      logger.info('WhatsApp connected as %s (LID: %s)', linkedJid, linkedLid || 'none')
      console.log(`\n  Connected as: ${linkedJid} (LID: ${linkedLid || 'none'})\n`)

      // Notify Python that WhatsApp is connected
      postWebhook({ type: 'connection.open', jid: linkedJid }).catch(() => {})
    }

    if (connection === 'close') {
      connectionState = 'disconnected'
      const statusCode = lastDisconnect?.error?.output?.statusCode
      const loggedOut = statusCode === DisconnectReason.loggedOut

      if (loggedOut) {
        logger.warn('Logged out from WhatsApp — clearing session and restarting for QR scan.')
        postWebhook({ type: 'connection.logout' }).catch(() => {})
        clearSessionAndRestart('logged out')
      } else {
        // Exponential backoff reconnect
        reconnectAttempts++
        const delay = Math.min(1000 * 2 ** reconnectAttempts, MAX_RECONNECT_DELAY_MS)
        logger.info('Connection closed (code %d). Reconnecting in %dms...', statusCode, delay)
        setTimeout(startBaileys, delay)
      }
    }
  })

  // ── Incoming messages → Python webhook ───────────────────────────────────

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    logger.info('messages.upsert fired: type=%s count=%d', type, messages.length)

    // 'append' = echo of messages we just sent (report chunks being synced back).
    // Only process 'notify' (new incoming messages the user typed on their phone).
    if (type !== 'notify') {
      logger.info('messages.upsert: skipping non-notify type=%s', type)
      return
    }

    for (const msg of messages) {
      const from = msg.key.remoteJid || ''
      const fromMe = msg.key.fromMe
      const hasContent = !!msg.message
      const text = hasContent ? extractText(msg) : null

      logger.info(
        'MSG: fromMe=%s from=%s hasContent=%s text=%s',
        fromMe, from, hasContent, text ? text.substring(0, 60) : 'null'
      )

      // Skip messages with no content or no text (images, stickers, etc.)
      if (!hasContent || !text) continue

      // Only process self-messages (messages sent to your own number / saved messages).
      // Check both phone JID and LID since WhatsApp uses both formats.
      const isGroup = from.endsWith('@g.us')
      const ownPhone = linkedJid ? linkedJid.split('@')[0] : null
      const fromNumber = from.split('@')[0]
      const matchesPhone = ownPhone && fromNumber === ownPhone
      const matchesLid = linkedLid && fromNumber === linkedLid
      const isSelfMessage = fromMe && (matchesPhone || matchesLid)

      if (!isSelfMessage) {
        logger.info('Skipping (not a self-message): fromMe=%s from=%s ownPhone=%s ownLid=%s', fromMe, from, ownPhone, linkedLid)
        continue
      }

      // For self-messages matched via LID, use the real phone number so replies route correctly
      const senderId = matchesLid && linkedJid ? linkedJid : fromNumber
      logger.info('Dispatching to webhook: from=%s sender=%s (lid=%s) text=%s', from, senderId, matchesLid, text.substring(0, 60))

      await postWebhook({
        type: 'message',
        from,
        sender_phone: senderId,
        is_group: isGroup,
        text,
        timestamp: msg.messageTimestamp,
        message_id: msg.key.id,
      })
    }
  })
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function extractText(msg) {
  const m = msg.message
  if (!m) return null
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    m.documentMessage?.caption ||
    null
  )
}

async function postWebhook(payload) {
  if (!PYTHON_WEBHOOK_URL) return
  try {
    const resp = await axios.post(PYTHON_WEBHOOK_URL, payload, { timeout: 10_000 })
    logger.info('Webhook delivered: status=%d body=%s', resp.status, JSON.stringify(resp.data))
  } catch (err) {
    const status = err.response?.status
    const body = JSON.stringify(err.response?.data)
    logger.warn('Webhook delivery failed (%s): status=%s body=%s msg=%s', PYTHON_WEBHOOK_URL, status, body, err.message)
  }
}

// ── Start ─────────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  logger.info('Baileys bridge HTTP API listening on port %d', PORT)
})

startBaileys().catch((err) => {
  logger.error({ err }, 'Failed to start Baileys')
  process.exit(1)
})
