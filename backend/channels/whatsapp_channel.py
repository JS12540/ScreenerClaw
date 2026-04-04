"""
ScreenerClaw — WhatsApp Channel (Baileys bridge)

Architecture:
  Python (this file)  <──────────────────────────────>  Node.js bridge (baileys_bridge/bridge.js)
    - Spawns bridge as subprocess                          - Handles WhatsApp Web protocol
    - Runs webhook server (FastAPI on port 8080)           - Shows QR code in terminal on first run
    - Sends messages via HTTP POST to bridge               - Saves session to auth_info_baileys/
    - Receives messages via webhook from bridge            - POSTs incoming msgs to Python webhook

First run:
  1. python run_bot.py --channel whatsapp
  2. Bridge starts and prints a QR code to the terminal
  3. Open WhatsApp > Settings > Linked Devices > Link a Device > Scan QR
  4. Done — session is saved, subsequent runs reconnect automatically

Requirements:
  - Node.js >= 18
  - npm install  (run once inside baileys_bridge/ directory)
  - WHATSAPP_WEBHOOK_PORT in .env (default: 8080)
  - WHATSAPP_BRIDGE_PORT in .env (default: 3000)
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx

from backend.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.logger import get_logger

logger = get_logger(__name__)

# Path to the Baileys bridge directory
BRIDGE_DIR = Path(__file__).parent.parent.parent / "baileys_bridge"


class WhatsAppChannel(BaseChannel):
    """
    WhatsApp channel via Baileys Node.js bridge.
    Manages the bridge subprocess and exposes a webhook for incoming messages.
    """

    def __init__(
        self,
        bridge_port: int = 3000,
        webhook_port: int = 8080,
    ) -> None:
        super().__init__("whatsapp")
        self._bridge_port = bridge_port
        self._webhook_port = webhook_port
        self._bridge_url = f"http://localhost:{bridge_port}"
        self._webhook_url = f"http://localhost:{webhook_port}/whatsapp/webhook"
        self._bridge_proc: Optional[subprocess.Popen] = None
        self._webhook_server = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        self._ensure_deps_installed()
        self._start_bridge_subprocess()
        await self._wait_for_bridge()
        await self._start_webhook_server()
        logger.info("WhatsApp channel ready (bridge=%s, webhook=%s)", self._bridge_url, self._webhook_url)

        # Keep start() blocking — same pattern as CLI/Telegram channels.
        # Without this, gateway.start_all() returns immediately and kills the bridge.
        while self._running:
            # Exit if bridge subprocess died unexpectedly
            if self._bridge_proc and self._bridge_proc.poll() is not None:
                logger.error("Baileys bridge subprocess exited (code %d)", self._bridge_proc.returncode)
                break
            await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False
        if self._webhook_server:
            self._webhook_server.close()
        if self._bridge_proc:
            self._bridge_proc.terminate()
            try:
                self._bridge_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._bridge_proc.kill()
            logger.info("WhatsApp bridge stopped.")

    # ── Sending ───────────────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> None:
        """Send a WhatsApp message. Full analysis reports are sent as PDF; short messages as text."""
        import base64
        from datetime import date

        phone = msg.metadata.get("phone") or msg.user_id
        if not phone:
            logger.error("WhatsApp send: no phone number in message metadata", extra={"metadata": msg.metadata})
            return

        # If we have a single-stock pipeline result, generate a PDF and send as document
        pipeline_result = msg.metadata.get("pipeline_result", {})
        if pipeline_result and pipeline_result.get("mode") == "single_stock" and not pipeline_result.get("error"):
            await self._send_pdf_report(phone, pipeline_result)
            return

        # Screening results — send PDF if available
        if pipeline_result and pipeline_result.get("screening_pdf_bytes"):
            await self._send_screening_pdf(phone, pipeline_result, msg.text)
            return

        # Fallback: send as text chunks (used for errors, screening results, short messages)
        chunks = self._chunk_text(msg.text, max_len=4000)
        logger.info(
            "WhatsApp sending text response",
            extra={"phone": phone, "chunks": len(chunks), "total_chars": len(msg.text)},
        )
        for i, chunk in enumerate(chunks, 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{self._bridge_url}/send",
                        json={"phone": phone, "message": chunk},
                    )
                    logger.info(
                        "WhatsApp chunk sent",
                        extra={"phone": phone, "chunk": i, "of": len(chunks), "status": resp.status_code},
                    )
            except Exception as exc:
                logger.error(
                    "WhatsApp send failed",
                    extra={"phone": phone, "chunk": i, "error": str(exc)},
                )

    async def _send_screening_pdf(self, phone: str, pipeline_result: dict, text: str) -> None:
        """Send screening results as PDF via WhatsApp."""
        import base64
        pdf_bytes = pipeline_result.get("screening_pdf_bytes")
        query = pipeline_result.get("screener_query_used") or pipeline_result.get("query", "Screen")
        total = pipeline_result.get("result_count", len(pipeline_result.get("results", [])))
        today = __import__("datetime").date.today().isoformat()
        file_name = f"ScreenerClaw_Screen_{today}.pdf"
        caption = f"*Screening Results* — {total} stocks\n{today}"

        logger.info("Sending screening PDF via WhatsApp", extra={"phone": phone, "total": total})

        # Send text preview first
        preview = text[:2000] if len(text) > 2000 else text
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(f"{self._bridge_url}/send", json={"phone": phone, "message": preview})
        except Exception as exc:
            logger.error("WhatsApp screening text preview failed", extra={"error": str(exc)})

        # Send PDF
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._bridge_url}/send-document",
                    json={
                        "phone": phone,
                        "fileName": file_name,
                        "data": base64.b64encode(pdf_bytes).decode(),
                        "mimetype": "application/pdf",
                        "caption": caption,
                    },
                )
                logger.info("WhatsApp screening PDF sent", extra={"phone": phone, "status": resp.status_code})
        except Exception as exc:
            logger.error("WhatsApp screening PDF failed", extra={"phone": phone, "error": str(exc)})

    async def _send_pdf_report(self, phone: str, result: dict) -> None:
        """Generate a PDF from the pipeline result and send it as a WhatsApp document."""
        import base64

        ticker  = result.get("ticker", "Report")
        company = result.get("company_name", ticker)
        score   = (result.get("scoring") or {}).get("composite_score", "—")
        verdict = (result.get("scoring") or {}).get("verdict", "—")
        today   = __import__("datetime").date.today().isoformat()
        file_name = f"{ticker}_ScreenerClaw_{today}.pdf"

        logger.info("Generating PDF report", extra={"phone": phone, "ticker": ticker})
        try:
            from backend.pdf_generator import generate_report_pdf
            pdf_bytes = generate_report_pdf(result)
            logger.info(
                "PDF generated",
                extra={"phone": phone, "ticker": ticker, "size_kb": round(len(pdf_bytes) / 1024, 1)},
            )
        except Exception as exc:
            logger.error("PDF generation failed", extra={"phone": phone, "ticker": ticker, "error": str(exc)})
            # Fallback to text
            chunks = self._chunk_text(result.get("report_markdown", str(exc)), max_len=4000)
            for chunk in chunks:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await client.post(f"{self._bridge_url}/send", json={"phone": phone, "message": chunk})
            return

        caption = f"*{company} ({ticker})* — ScreenerClaw Analysis\nScore: {score}/100 | {verdict}\n_{today}_"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._bridge_url}/send-document",
                    json={
                        "phone": phone,
                        "fileName": file_name,
                        "data": base64.b64encode(pdf_bytes).decode(),
                        "mimetype": "application/pdf",
                        "caption": caption,
                    },
                )
                logger.info(
                    "PDF report sent",
                    extra={"phone": phone, "ticker": ticker, "status": resp.status_code, "file": file_name},
                )
        except Exception as exc:
            logger.error("PDF send failed", extra={"phone": phone, "ticker": ticker, "error": str(exc)})

    # ── Bridge subprocess ─────────────────────────────────────────────────────

    def _ensure_deps_installed(self) -> None:
        """Run npm install inside baileys_bridge/ if node_modules is missing."""
        node_modules = BRIDGE_DIR / "node_modules"
        if not node_modules.exists():
            logger.info("Installing Baileys bridge dependencies (npm install)...")
            print("\n[ScreenerClaw] Installing WhatsApp bridge Node.js dependencies...\n")
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(BRIDGE_DIR),
                capture_output=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "npm install failed in baileys_bridge/. "
                    "Make sure Node.js >= 18 is installed."
                )

    def _start_bridge_subprocess(self) -> None:
        """Start the Baileys bridge as a subprocess."""
        env = {
            **os.environ,
            "PORT": str(self._bridge_port),
            "PYTHON_WEBHOOK_URL": self._webhook_url,
            "AUTH_DIR": str(BRIDGE_DIR / "auth_info_baileys"),
            "LOG_LEVEL": "info",
        }

        logger.info("Starting Baileys bridge on port %d...", self._bridge_port)
        self._bridge_proc = subprocess.Popen(
            ["node", "bridge.js"],
            cwd=str(BRIDGE_DIR),
            env=env,
            # Let stdout/stderr flow directly to terminal so the QR code is visible
            stdout=None,
            stderr=None,
        )
        logger.info("Bridge subprocess PID: %d", self._bridge_proc.pid)

    async def _wait_for_bridge(self, timeout: float = 30.0, interval: float = 1.0) -> None:
        """Poll until the bridge HTTP API responds."""
        logger.info("Waiting for bridge to be ready...")
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{self._bridge_url}/status")
                    if resp.status_code == 200:
                        logger.info("Bridge is ready: %s", resp.json())
                        return
            except Exception:
                pass
            await asyncio.sleep(interval)
        raise TimeoutError(
            f"Baileys bridge did not start within {timeout}s. "
            "Check that Node.js is installed and npm install completed in baileys_bridge/."
        )

    # ── Webhook server ────────────────────────────────────────────────────────

    async def _start_webhook_server(self) -> None:
        """
        Start a minimal asyncio TCP server to receive webhook POSTs from the bridge.
        Uses raw asyncio streams instead of uvicorn to avoid FastAPI/Starlette
        version-specific request validation issues.
        """
        import json as _json

        channel = self

        async def _handle_connection(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                # Read request line  (e.g. "POST /whatsapp/webhook HTTP/1.1\r\n")
                request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)

                # Read headers until blank line
                content_length = 0
                while True:
                    line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                    if line in (b"\r\n", b"\n", b""):
                        break
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if decoded.lower().startswith("content-length:"):
                        content_length = int(decoded.split(":", 1)[1].strip())

                # Read body
                body = b""
                if content_length > 0:
                    body = await asyncio.wait_for(
                        reader.read(content_length), timeout=10.0
                    )

                # Respond immediately so the bridge doesn't time out,
                # then process the message in the background.
                resp_body = b'{"ok":true}'
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(resp_body)).encode() + b"\r\n"
                    b"Connection: close\r\n"
                    b"\r\n" + resp_body
                )
                writer.write(response)
                await writer.drain()

                # Parse and dispatch in background (pipeline takes 30-60s)
                try:
                    data = _json.loads(body)
                    asyncio.create_task(channel._process_webhook(data))
                except Exception as exc:
                    logger.error("Webhook parse error: %s", exc)

            except Exception as exc:
                logger.warning("Webhook connection error: %s", exc)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        server = await asyncio.start_server(
            _handle_connection, host="0.0.0.0", port=self._webhook_port
        )
        self._webhook_server = server
        logger.info("WhatsApp webhook server listening on port %d", self._webhook_port)

    async def _process_webhook(self, data: dict) -> None:
        """Process a parsed webhook payload from the Baileys bridge."""
        logger.info("Webhook received: %s", data)
        event_type = data.get("type")

        if event_type == "connection.open":
            logger.info("WhatsApp connected: %s", data.get("jid"))
            return

        if event_type == "connection.logout":
            logger.warning("WhatsApp logged out — delete auth_info_baileys/ and re-scan QR")
            return

        if event_type != "message":
            return  # ignore non-message events

        text = data.get("text", "").strip()
        sender = data.get("sender_phone", "")
        raw_jid = data.get("from", "")
        is_group = data.get("is_group", False)

        if not text or not sender:
            return

        msg = InboundMessage(
            channel="whatsapp",
            user_id=sender,
            session_id=f"wa-{sender}",
            text=text,
            metadata={"phone": sender, "jid": raw_jid, "is_group": is_group},
        )

        logger.info(
            "WhatsApp message received",
            extra={"sender": sender, "jid": raw_jid, "text": text[:80]},
        )

        try:
            logger.info("Dispatching to pipeline", extra={"sender": sender, "text": text[:60]})
            response = await self.dispatch(msg)
            if response:
                logger.info(
                    "Pipeline returned response",
                    extra={"sender": sender, "response_len": len(response.text)},
                )
                await self.send(response)
            else:
                logger.warning("Pipeline returned no response", extra={"sender": sender, "text": text[:60]})
        except Exception as exc:
            logger.error(
                "WhatsApp handler error",
                extra={"sender": sender, "error": str(exc)},
            )
