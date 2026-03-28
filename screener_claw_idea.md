# 🦞 ScreenerClaw — AI-Native Indian Stock Discovery Platform
### *OpenClaw-Inspired Multi-Agent Architecture for Automated Stock Intelligence*

> **Philosophy:** ScreenerClaw is not a screener with AI bolted on. It is an OpenClaw-style **autonomous agent system** where each agent has a role, memory, skills, and the ability to learn — applied entirely to Indian equity markets. You talk to it in plain English via any channel (WhatsApp, Telegram, CLI, Web), and it thinks, fetches, analyses, and reports back.

---

## 📋 Table of Contents

- [Core Design Principles](#-core-design-principles)
- [Authentication — The OpenClaw Way](#-authentication--the-openclaw-way)
- [High-Level Architecture](#-high-level-architecture)
- [Multi-Agent System — Every Agent's Role](#-multi-agent-system--every-agents-role)
- [Channel System — How You Talk to ScreenerClaw](#-channel-system--how-you-talk-to-screenerclaw)
- [Memory & Learning System](#-memory--learning-system)
- [Skills System](#-skills-system)
- [LLM Provider Abstraction](#-llm-provider-abstraction)
- [Security Model](#-security-model)
- [Data Pipeline — Automated & Self-Healing](#-data-pipeline--automated--self-healing)
- [Valuation Engine](#-valuation-engine)
- [Scoring & Ranking](#-scoring--ranking)
- [Webhook & Automation Layer](#-webhook--automation-layer)
- [Configuration Reference](#-configuration-reference)
- [Installation & Setup](#-installation--setup)
- [Example Interactions](#-example-interactions)

---

## 🎯 Core Design Principles

ScreenerClaw is built on the same philosophical pillars as OpenClaw:

| Principle | What it means for ScreenerClaw |
|-----------|-------------------------------|
| **Local-first** | Your portfolio, watchlists, and analysis live as plain files on your machine |
| **Channel-agnostic** | WhatsApp, Telegram, Slack, CLI, Web — same brain, any interface |
| **Self-improving** | Agents learn your investment style over time and personalise outputs |
| **Multi-agent** | Specialised agents collaborate — no single monolith |
| **LLM-agnostic** | Claude, GPT-4, Gemini, Mistral, Ollama — swap freely |
| **Automation-first** | Cron jobs, webhooks, alerts — works while you sleep |
| **No hidden cloud** | Data flows: source → your machine → LLM API → you. Nothing else. |

---

## 🔑 Authentication — The OpenClaw Way

ScreenerClaw moves away from simple username/password toward a **pairing model** — the same approach OpenClaw uses for WhatsApp. Each channel has its own access policy.

### Channel-Level Auth Policies

```
dmPolicy options:
  pairing    → Unknown sender gets a 6-digit code. You approve once.
               After that, they're in your allowlist permanently.
  allowlist  → Only pre-approved IDs can interact
  open       → Anyone who knows the bot can query (NOT recommended for financial data)
  disabled   → Channel inactive
```

### Pairing Flow (Default & Recommended)

```
1. Someone messages your ScreenerClaw bot for the first time
2. Bot replies: "Send code 847-291 to +91-XXXXX to pair this device"
3. You send the code from your phone to confirm
4. That sender is permanently approved — no login needed again
5. You can revoke anytime: screenclaw pairing revoke <channel> <id>
```

### Optional: API Token Auth (for programmatic access)

```bash
# Generate a token for your own scripts / dashboards
screenerclaw auth token create --name "my-dashboard"
# → Bearer token: sck_live_XXXXXXXXXXXXXXXX

# Use in HTTP requests:
# Authorization: Bearer sck_live_XXXXXXXXXXXXXXXX
```

### Secrets Management (for data source credentials)

Screener.in, NSE, premium data providers — credentials stored encrypted:

```bash
screenerclaw secrets set SCREENER_SESSION_COOKIE "s%3A..."
screenerclaw secrets set ALPHAVANTAGE_KEY "XXXXXXXX"
screenerclaw secrets set NSEPY_PROXY "http://..."

# Secrets are stored in ~/.screenerclaw/secrets/ (AES-256 encrypted)
# Never appear in logs, transcripts, or config files
```

---

## 🏗️ High-Level Architecture

```mermaid
flowchart TD
    subgraph CHANNELS ["📡 Channels (Input)"]
        WA["📱 WhatsApp"]
        TG["✈️ Telegram"]
        SL["💬 Slack"]
        DC["🎮 Discord"]
        CLI["💻 CLI"]
        WEB["🌐 WebUI"]
        WH["🪝 Webhooks"]
    end

    subgraph GATEWAY ["🏛️ ScreenerClaw Gateway (Python/FastAPI)"]
        GW["Gateway Server\n:18900"]
        ROUTER["Binding Router\n(which agent handles this?)"]
        AUTH["Auth Layer\n(pairing / token / allowlist)"]
        GW --> AUTH --> ROUTER
    end

    subgraph AGENTS ["🤖 Multi-Agent System"]
        ORCH["🎭 Orchestrator Agent\n(routes, delegates, synthesises)"]
        UNIV["🌍 Universe Agent\n(maintain 5000+ stock universe)"]
        SCREEN["🔍 Screener Agent\n(NL → filters → candidates)"]
        DATA["📊 Data Agent\n(multi-source fetcher)"]
        ANAL["🧮 Analysis Agent\n(50+ metrics, valuations)"]
        RANK["🏆 Ranking Agent\n(score 0-100)"]
        REPORT["📝 Report Agent\n(LLM-generated deep analysis)"]
        ALERT["🔔 Alert Agent\n(price + fundamental triggers)"]
        LEARN["🧠 Learning Agent\n(update memory, skills, config)"]
    end

    subgraph MEMORY ["💾 Memory & Storage"]
        SESS["Session History\n~/.screenerclaw/sessions/"]
        MEM["User Memory\n~/.screenerclaw/memory.md"]
        SKILLS["Skills\n~/.screenerclaw/skills/"]
        DB["Stock Database\n~/.screenerclaw/db/stocks.db"]
        CACHE["Cache Layer\n(TTL per data type)"]
        WATCH["Watchlists\n~/.screenerclaw/watchlists/"]
    end

    subgraph SOURCES ["🌐 Data Sources"]
        SCR["Screener.in"]
        YF["Yahoo Finance"]
        NSE["NSE API"]
        BSE["BSE API"]
        ALPHA["AlphaVantage"]
        MONEYC["Moneycontrol"]
    end

    subgraph LLM ["🧠 LLM Providers"]
        CLAUDE["Anthropic Claude"]
        GPT["OpenAI GPT-4"]
        GEMINI["Google Gemini"]
        MISTRAL["Mistral"]
        OLLAMA["Ollama (local)"]
    end

    CHANNELS --> GATEWAY
    GATEWAY --> AGENTS
    AGENTS <--> MEMORY
    AGENTS --> SOURCES
    AGENTS --> LLM
```

---

## 🤖 Multi-Agent System — Every Agent's Role

### Agent Roster

```python
# ~/.screenerclaw/config.json5

{
  agents: {
    list: [
      {
        id: "personal",
        role: "orchestrator",
        default: true,
        workspace: "~/.screenerclaw/workspace-personal",
        model: "anthropic/claude-sonnet-4-5",
        memory: "~/.screenerclaw/memory.md",
        skills: ["screener", "valuation", "alerts", "portfolio"],
      },
      {
        id: "data-fetcher",
        role: "data",
        workspace: "~/.screenerclaw/workspace-data",
        model: "openai/gpt-4o-mini",    # cheaper model for data tasks
        tools: {
          allow: ["bash", "http_fetch", "cache_read", "cache_write"],
          deny:  ["report_generate"],
        },
      },
      {
        id: "analyst",
        role: "analysis",
        workspace: "~/.screenerclaw/workspace-analyst",
        model: "anthropic/claude-opus-4-5",   # best model for deep analysis
        skills: ["dcf", "graham", "sector-analysis"],
      },
      {
        id: "alert-watcher",
        role: "alerts",
        workspace: "~/.screenerclaw/workspace-alerts",
        model: "google/gemini-flash",   # fast + cheap for monitoring
        always_on: true,
      },
    ]
  }
}
```

### Binding Resolution — Which Agent Handles What

```
Message routing priority (most → least specific):

1. Explicit agent mention    "analyst, analyse HDFC Bank"
2. Intent classification     "set alert" → alert-watcher
3. Channel binding           Telegram → personal (default)
4. Task type                 "fetch data" → data-fetcher
5. Default agent             personal (orchestrator)
```

### Agent-to-Agent Collaboration

```
sessions_list        → discover active agents + their status
sessions_history     → read another agent's recent work
sessions_send        → delegate a subtask to a specialist agent
sessions_spawn       → spawn a temporary sub-agent for one task
```

**Example orchestration flow:**

```
You (WhatsApp): "Find me 5 undervalued pharma stocks and give me a deep report on the best one"

Orchestrator agent:
  1. sessions_send(data-fetcher, "Get all NSE pharma stocks with PE < 20, ROCE > 15")
  2. data-fetcher runs → returns list of 12 candidates
  3. sessions_send(analyst, "Rank these 12 candidates and pick the top 1")
  4. analyst runs DCF + Graham + scoring → picks Ajanta Pharma
  5. sessions_send(analyst, "Generate full investment report for Ajanta Pharma")
  6. analyst generates 2000-word report
  7. Orchestrator synthesises → sends back to you on WhatsApp
```

---

## 📡 Channel System — How You Talk to ScreenerClaw

### Supported Channels

| Channel | Auth method | Setup needed |
|---------|------------|--------------|
| **WhatsApp** | Pairing (QR scan once) | Dedicated SIM recommended |
| **Telegram** | BotFather token | 30 seconds |
| **Slack** | Slack App + Bot token | Free workspace |
| **Discord** | Bot Application | Discord dev portal |
| **CLI** | Local (no auth) | Built-in |
| **WebUI** | Bearer token | Auto-generated |
| **Webhooks** | HMAC-SHA256 signed | Config only |

### Channel Configuration

```json5
{
  channels: {
    whatsapp: {
      dmPolicy: "pairing",
      allowFrom: ["+919876543210"],    // your number
      groupPolicy: "disabled",         // don't respond in groups (financial data is personal)
      ackReaction: { emoji: "📊", direct: true },
    },
    telegram: {
      botToken: "123456:ABC...",
      dmPolicy: "pairing",
      groupPolicy: "allowlist",
      allowedGroups: ["-1001234567890"],   // your private investment group
    },
    slack: {
      botToken: "xoxb-...",
      appToken: "xapp-...",
      dmPolicy: "allowlist",
      allowFrom: ["U0123456789"],   // your Slack user ID
    },
    cli: {
      dmPolicy: "open",    // local CLI is always trusted
    },
  }
}
```

---

## 🧠 Memory & Learning System

ScreenerClaw agents maintain **four memory layers**, mirroring the OpenClaw model exactly:

### Layer 1 — Session History (Short-Term)

Every conversation is stored as a transcript:

```
~/.screenerclaw/sessions/
  personal-main.md        # your personal DM session (all channels collapse here)
  analyst-session-42.md   # analyst agent's working session
  alert-watcher.md        # alert agent's ongoing log
```

Auto-compaction kicks in when history grows too long — old turns are summarised into a compressed block.

### Layer 2 — User Memory (Long-Term Facts)

The agent writes to `memory.md` whenever it learns something about you:

```markdown
# ScreenerClaw User Memory — Updated 2025-07-14

## Investment Style
- Prefers: Quality compounder stocks (ROCE > 20%, consistent profit growth)
- Avoids: High debt companies (D/E > 1.5), loss-making companies
- Typical holding period: 3-5 years (long-term investor)
- Portfolio size preference: 10-15 stocks, max 15% single stock
- Risk tolerance: Moderate — prefers large/midcap over smallcap

## Sector Preferences
- Interested: Pharma, IT, FMCG, Banking (private), Capital Goods
- Avoids: PSU banks, real estate, commodities

## Screening Shortcuts Learned
- "Safe dividend stock" → user means: dividend yield > 2%, payout < 60%, D/E < 0.5
- "Compounder" → user means: 10yr profit CAGR > 15%, ROCE > 20%, promoter holding > 50%
- "Undervalued" → user means: PE < sector average AND PB < 3

## Watchlist Context
- HDFC Bank: watching since Jan 2025, waiting for PE < 18
- Pidilite: in portfolio since 2022, tracking quarterly margins
- Asian Paints: tracking recovery from volume pressure

## Alert Preferences
- Prefers WhatsApp for price alerts (immediate)
- Prefers Telegram for weekly digest (Sunday 9am)
- Does NOT want alerts between 11pm and 7am IST
```

### Layer 3 — Skills (Domain Knowledge)

Skills teach the agent platform-specific knowledge it can't infer:

```
~/.screenerclaw/skills/
  screener-in.md          # how to scrape screener.in, handle rate limits
  nse-data.md             # NSE API quirks, holiday calendar
  sector-mapping.md       # Indian sector taxonomy, peer groups
  valuation-india.md      # India-specific: G-Sec rate, risk premium, sector WACC
  management-quality.md   # how to assess promoter integrity, governance
  quarterly-results.md    # how to parse BSE announcements, read results
  custom-ratios.md        # user's own custom formulas (agent writes these)
```

**The agent writes its own skills.** When you define a custom screening criterion it needs to remember:

```
You: "From now on, when I say 'fortress balance sheet', 
     I mean D/E < 0.3, current ratio > 2, interest coverage > 10, 
     and CFO/PAT > 0.8"

Agent: Understood. I'll save this as a permanent skill so I remember 
       your definition across all future sessions.
       [writes to ~/.screenerclaw/skills/custom-terms.md]
```

### Layer 4 — Config Evolution

The agent can modify `config.json5` to:
- Add new cron jobs (weekly digest, earnings season alerts)
- Add new watchlist entries
- Update alert thresholds
- Change which model handles which agent role

---

## 📦 Skills System

### Built-in Skills (Auto-installed)

| Skill | What it teaches the agent |
|-------|--------------------------|
| `screener-in` | Scraping Screener.in: URLs, pagination, data fields, rate limiting |
| `nse-live` | NSE live price API, F&O data, market holidays |
| `bse-announcements` | Parsing BSE corporate announcements, quarterly results |
| `dcf-india` | DCF with India-specific params: G-Sec 7%, ERP 6%, terminal growth 4% |
| `graham-india` | Graham Number/Formula adapted for Indian market |
| `sector-india` | All NSE sectors, sub-sectors, peer group definitions |
| `portfolio-tracker` | Portfolio P&L, XIRR, vs Nifty 50 benchmark |
| `alert-engine` | Price alerts, fundamental alerts, earnings alerts |

### Installing Community Skills

```bash
screenerclaw skills install technical-analysis   # RSI, MACD, moving averages
screenerclaw skills install bulk-deals           # NSE bulk/block deal monitoring
screenerclaw skills install promoter-activity    # promoter buying/selling tracker
screenerclaw skills install fii-dii              # FII/DII flow monitoring
screenerclaw skills install credit-ratings       # CRISIL/ICRA rating changes
```

### Skill File Format

```markdown
---
name: screener-in
version: 2.1.0
tools:
  - bash
  - http_fetch
description: Fetch fundamental data from Screener.in
auth_required: SCREENER_SESSION_COOKIE
---

# Screener.in Data Fetching Skill

## Company Page URL Pattern
https://www.screener.in/company/{SYMBOL}/consolidated/

## Key Data Locations (CSS selectors)
- PE ratio: #top-ratios li:nth-child(3) .number
- Market cap: #top-ratios li:nth-child(1) .number
- 10-year P&L table: #profit-loss table

## Rate Limiting
- Max 1 request per 2 seconds (anonymous)
- With session cookie: 1 request per 0.5 seconds
- If 429 received: back off 30 seconds, then retry

## Session Cookie Setup
The SCREENER_SESSION_COOKIE secret must be set.
To get it: log in to screener.in → DevTools → Application → Cookies → copy 'sessionid'

## Watchlist Fetch
GET https://www.screener.in/api/company/{id}/
Response: JSON with all fundamentals

## Common Errors
- 403: Session expired → alert user to refresh cookie
- 503: Market hours scrape overload → use cached data
```

---

## 🔌 LLM Provider Abstraction

ScreenerClaw never locks you into one LLM. The provider layer is fully swappable:

### Provider Configuration

```python
# ~/.screenerclaw/config.json5

{
  llm: {
    providers: {
      anthropic: {
        api_key_secret: "ANTHROPIC_API_KEY",
        default_model: "claude-sonnet-4-5",
        models: {
          fast:    "claude-haiku-4-5",
          default: "claude-sonnet-4-5",
          deep:    "claude-opus-4-5",
        }
      },
      openai: {
        api_key_secret: "OPENAI_API_KEY",
        default_model: "gpt-4o",
        models: {
          fast:    "gpt-4o-mini",
          default: "gpt-4o",
          deep:    "gpt-4o",
        }
      },
      google: {
        api_key_secret: "GOOGLE_API_KEY",
        default_model: "gemini-1.5-pro",
        models: {
          fast:    "gemini-1.5-flash",
          default: "gemini-1.5-pro",
          deep:    "gemini-1.5-pro",
        }
      },
      mistral: {
        api_key_secret: "MISTRAL_API_KEY",
        default_model: "mistral-large-latest",
      },
      ollama: {
        base_url: "http://localhost:11434",
        default_model: "llama3.1:8b",
        // No API key needed — fully local
      },
    },

    // Route by task type
    routing: {
      screening:    { provider: "anthropic", tier: "default" },
      data_fetch:   { provider: "openai",    tier: "fast"    },   // cheaper
      deep_report:  { provider: "anthropic", tier: "deep"    },   // best model
      alerts:       { provider: "google",    tier: "fast"    },   // cheapest + fast
      local_tasks:  { provider: "ollama",    tier: "default" },   // offline capable
    }
  }
}
```

### Provider Abstraction Layer (Python)

```python
# backend/llm/provider.py

class LLMProvider:
    """
    Unified interface — agents never import anthropic/openai directly.
    They call provider.complete() and the routing config decides the rest.
    """

    async def complete(
        self,
        messages: list[dict],
        task_type: str = "screening",      # drives model routing
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        provider, model = self._resolve(task_type)
        return await self._adapters[provider].complete(messages, model, tools, stream)

    def _resolve(self, task_type: str) -> tuple[str, str]:
        routing = self.config.llm.routing.get(task_type, {})
        provider = routing.get("provider", self.config.llm.default_provider)
        tier = routing.get("tier", "default")
        model = self.config.llm.providers[provider].models[tier]
        return provider, model
```

### Switching Provider Anytime

```bash
# Per-session override
screenerclaw chat --provider ollama    # go fully offline

# Permanent change
screenerclaw config set llm.routing.deep_report.provider openai

# Or just tell the agent:
# "Use Gemini for all future reports"
# Agent writes to config automatically
```

---

## 🔐 Security Model

### Default Security Posture

```
Personal DM sessions (your own WhatsApp/Telegram):
  → Full access to data tools, screener, analysis, alerts
  → Can modify watchlists, add cron jobs, update config
  → LLM reports generated with full context

Group sessions:
  → Read-only: can screen and report, cannot modify watchlists
  → Cannot access portfolio data (private by design)
  → Rate-limited: max 5 queries per hour per group

Webhook endpoints:
  → HMAC-SHA256 signature required on every request
  → IP allowlist optional (e.g., only NSE/BSE IPs for data triggers)
  → All payloads logged + audited

CLI:
  → Local only — always trusted — no auth required
```

### Data Privacy

```
Portfolio data:         Local only. Never sent to LLM unless you ask for analysis.
Watchlist data:         Local only. Sent to LLM only for screening queries.
API keys/secrets:       AES-256 encrypted at rest. Never in logs or transcripts.
Session transcripts:    Local markdown files. You own them. Delete anytime.
LLM context:            Your queries go to your chosen LLM provider.
                        Choose Ollama for 100% local operation.
```

### Tool Allow/Deny per Agent

```json5
{
  agents: {
    defaults: {
      tools: {
        allow: ["screen", "fetch_data", "analyse", "report", "alert_read"],
        deny:  ["alert_write", "config_write", "portfolio_write"],
        // Non-main sessions cannot modify persistent state
      }
    },
    list: [
      {
        id: "personal",
        tools: {
          allow: ["*"],    // your personal agent gets everything
        }
      }
    ]
  }
}
```

---

## 🔄 Data Pipeline — Automated & Self-Healing

### Universe Maintenance (Always Fresh)

```python
# Runs on cron — agent manages this automatically

cron: [
  {
    id: "universe-refresh",
    schedule: "0 8 * * 1-5",          # Every market day at 8am
    agent: "data-fetcher",
    message: "Refresh NSE + BSE universe. Update sector mappings. Flag any new listings or delistings.",
  },
  {
    id: "fundamentals-refresh",
    schedule: "0 9 * * 6",            # Every Saturday 9am
    agent: "data-fetcher",
    message: "Refresh fundamental data for all watchlist stocks + top 500 by market cap.",
  },
  {
    id: "quarterly-results",
    schedule: "0 */4 * * 1-5",        # Every 4 hours on market days
    agent: "data-fetcher",
    message: "Check BSE announcements for new quarterly results. Update database. Alert me for watchlist stocks.",
  },
  {
    id: "weekly-digest",
    schedule: "0 9 * * 0",            # Sunday 9am
    agent: "personal",
    message: "Generate my weekly investment digest: portfolio performance, watchlist updates, top screening ideas, notable market events.",
    channel: "telegram",
  },
]
```

### Self-Healing Data Fetcher

The data agent knows how to recover from failures:

```
Screener.in 403 (session expired)
  → Alert user: "Screener.in session expired. Please refresh your cookie."
  → Fall back to Yahoo Finance for the same data
  → Continue pipeline without blocking

NSE API 429 (rate limit)
  → Back off exponentially (1s, 2s, 4s, 8s...)
  → Use cached data if fresh enough (< 4 hours for fundamentals)
  → Log failure in data-fetcher session

Yahoo Finance timeout
  → Retry 3 times
  → Fall back to BSE
  → If all fail: use last known good data + mark as stale
```

### Cache Strategy

```python
# TTL by data type (agent knows these from the skill file)

CACHE_TTL = {
    "live_price":        30,          # 30 seconds
    "intraday_ohlcv":    300,         # 5 minutes
    "daily_ohlcv":       3600,        # 1 hour
    "fundamentals":      86400,       # 1 day
    "annual_results":    604800,      # 1 week
    "sector_pe":         86400,       # 1 day
    "shareholding":      7776000,     # 90 days (quarterly)
    "management_info":   2592000,     # 30 days
}
```

---

## 🧮 Valuation Engine

All valuation models run as **Python tools** the analyst agent can call:

```python
# Available valuation tools

tools = [
    "dcf_gurufocus",        # Two-stage EPS DCF (10yr + terminal)
    "dcf_fcf",              # Same but using Free Cash Flow
    "graham_number",        # √(22.5 × EPS × Book Value)
    "graham_formula",       # EPS × (8.5 + 2g) × 4.4 / AAA_yield
    "pe_based",             # vs sector PE, historical PE, Graham PE (15x)
    "epv",                  # Earnings Power Value (Greenwald)
    "owner_earnings",       # Buffett's Owner Earnings DCF
    "ddm",                  # Gordon Growth Model (dividend stocks)
    "peg_ratio",            # Peter Lynch PEG < 1
    "ebo_model",            # Edwards-Bell-Ohlson residual income
    "ev_ebitda",            # EV/EBITDA multiple
    "justified_pb",         # P/B = ROE / Cost of Equity
    "reverse_dcf",          # What growth is the current price implying?
]

# Scenario output (all models support 3 scenarios)
scenarios = ["bear", "base", "bull"]
horizons  = [3, 5, 10]   # years
```

### India-Specific Parameters (Skill-Encoded)

```python
INDIA_PARAMS = {
    "risk_free_rate":      0.070,    # 10-yr G-Sec (refreshed weekly)
    "equity_risk_premium": 0.060,    # India ERP
    "default_wacc":        0.130,    # 13%
    "terminal_growth":     0.040,    # 4% (India nominal GDP long-term)
    "aaa_bond_yield":      0.075,    # for Graham Formula denominator

    # Sector-specific WACC overrides
    "sector_wacc": {
        "Banking":           0.120,
        "FMCG":              0.110,
        "IT":                0.125,
        "Pharma":            0.130,
        "Infrastructure":    0.145,
        "Real Estate":       0.150,
    }
}
```

---

## 🏆 Scoring & Ranking

### Composite Score Components

| Component | Default Weight | What it measures |
|-----------|---------------|-----------------|
| **Quality** | 30% | ROCE, ROE, OPM, asset turnover |
| **Growth** | 25% | Revenue CAGR, Profit CAGR, EPS CAGR (3yr, 5yr, 10yr) |
| **Valuation** | 20% | PE, PB, EV/EBITDA vs sector (inverted — cheaper = higher) |
| **Financial Health** | 15% | D/E, current ratio, interest coverage, CFO/PAT |
| **Consistency** | 10% | Profit consistency %, margin stability, dividend track record |

**Verdicts:**
- 🟢 **STRONG BUY** — Score ≥ 70
- 🔵 **BUY** — Score ≥ 60
- 🟡 **WATCHLIST** — Score ≥ 50
- ⚪ **NEUTRAL** — Score ≥ 40
- 🔴 **AVOID** — Score < 40

### Personalised Scoring (Learning Over Time)

The Learning Agent adjusts weights based on your feedback:

```
You: "I don't care much about valuation right now — focus on quality and growth"

Learning Agent:
  → Updates your scoring profile:
     quality:   35% (+5)
     growth:    30% (+5)
     valuation: 10% (-10)
     health:    15% (unchanged)
     consistency: 10% (unchanged)
  → Saves to memory.md
  → Future screenings use YOUR weights, not defaults
```

---

## 🪝 Webhook & Automation Layer

### Incoming Webhooks (External → ScreenerClaw)

```json5
{
  webhooks: [
    {
      id: "bse-results",
      path: "/hooks/bse-results",
      secret: "your-hmac-secret",
      agent: "personal",
      messageTemplate: "New quarterly result from BSE: {{company}} ({{symbol}}). Revenue: {{revenue}}, PAT: {{pat}}, vs estimate: {{vs_estimate}}. Analyse if this is in my watchlist and alert me.",
    },
    {
      id: "nse-bulk-deals",
      path: "/hooks/bulk-deals",
      agent: "alert-watcher",
      messageTemplate: "Bulk deal alert: {{acquirer}} bought/sold {{quantity}} shares of {{symbol}} at ₹{{price}}. Check if relevant to my watchlist.",
    },
    {
      id: "tradingview-alert",
      path: "/hooks/tradingview",
      agent: "alert-watcher",
      messageTemplate: "TradingView alert triggered: {{symbol}} — {{message}}. Pull fundamentals and give me a buy/hold/sell view.",
    },
  ]
}
```

### Price & Fundamental Alerts (Agent-Managed)

```
You: "Alert me when HDFC Bank falls below ₹1,500"
Agent: Sets alert → monitors via NSE every 30 seconds during market hours
       → WhatsApp when triggered: "🔔 HDFC Bank hit ₹1,498! You were waiting at ₹1,500.
          Current PE: 16.2 (vs 5yr avg 19.1). Looks interesting — want a full analysis?"

You: "Alert me when any midcap IT company's ROCE drops below 15%"
Agent: Sets fundamental alert → checks weekly on Saturday refresh
       → Scans 80+ midcap IT companies each week for this condition
```

---

## ⚙️ Configuration Reference

Full config lives at `~/.screenerclaw/config.json5` (JSON5 — comments allowed):

```json5
{
  // ── Identity ──────────────────────────────────────────────────────────────
  meta: {
    name: "ScreenerClaw",
    version: "1.0.0",
    timezone: "Asia/Kolkata",
  },

  // ── LLM Providers ─────────────────────────────────────────────────────────
  llm: {
    default_provider: "anthropic",
    providers: { /* see LLM section above */ },
    routing: { /* see LLM section above */ },
  },

  // ── Agents ────────────────────────────────────────────────────────────────
  agents: {
    defaults: {
      memory: "~/.screenerclaw/memory.md",
      skills_dir: "~/.screenerclaw/skills/",
      sandbox: { mode: "non-main" },
    },
    list: [ /* see agent roster above */ ],
  },

  // ── Channels ──────────────────────────────────────────────────────────────
  channels: { /* see channel config above */ },

  // ── Bindings ──────────────────────────────────────────────────────────────
  bindings: [
    { agentId: "personal",      match: { channel: "whatsapp" } },
    { agentId: "personal",      match: { channel: "telegram" } },
    { agentId: "alert-watcher", match: { channel: "webhook" } },
  ],

  // ── Automations ───────────────────────────────────────────────────────────
  cron: [ /* see pipeline section above */ ],
  webhooks: [ /* see webhook section above */ ],

  // ── Data Sources ──────────────────────────────────────────────────────────
  data: {
    sources: {
      screener_in: {
        enabled: true,
        session_cookie_secret: "SCREENER_SESSION_COOKIE",
        rate_limit_rps: 0.5,
      },
      yahoo_finance: {
        enabled: true,
        rate_limit_rps: 2,
      },
      nse: {
        enabled: true,
        rate_limit_rps: 5,
      },
      bse: {
        enabled: true,
        rate_limit_rps: 2,
      },
    },
    cache_dir: "~/.screenerclaw/cache/",
    db_path:   "~/.screenerclaw/db/stocks.db",
  },

  // ── Valuation Defaults ────────────────────────────────────────────────────
  valuation: {
    risk_free_rate:      0.070,
    equity_risk_premium: 0.060,
    default_wacc:        0.130,
    terminal_growth:     0.040,
  },

  // ── Scoring ───────────────────────────────────────────────────────────────
  scoring: {
    weights: {
      quality:     0.30,
      growth:      0.25,
      valuation:   0.20,
      health:      0.15,
      consistency: 0.10,
    }
  },

  // ── Gateway ───────────────────────────────────────────────────────────────
  gateway: {
    port: 18900,
    bind: "loopback",
    auth: { mode: "pairing" },
    tailscale: { mode: "serve" },
  },
}
```

---

## 🚀 Installation & Setup

```bash
# Prerequisites: Python 3.11+, Node 18+ (for WebUI only)

# 1. Clone
git clone https://github.com/yourorg/screenerclaw
cd screenerclaw

# 2. Python environment
python -m venv venv
source venv/bin/activate      # Mac/Linux
# venv\Scripts\activate       # Windows

pip install -r requirements.txt

# 3. Guided setup (recommended)
python -m screenerclaw onboard

# The wizard will:
# → Ask for your preferred LLM provider + API key
# → Set up your first channel (Telegram recommended)
# → Configure Screener.in session cookie (optional but strongly recommended)
# → Run a test screen to verify everything works
# → Start the gateway daemon

# 4. Manual start (alternative)
python -m screenerclaw gateway --port 18900 --verbose

# 5. Health check
python -m screenerclaw doctor
```

### Directory Structure Created

```
~/.screenerclaw/
├── config.json5              # Main config (JSON5, comments OK)
├── secrets/                  # AES-256 encrypted API keys
├── memory.md                 # Your personal investment memory
├── sessions/                 # Conversation transcripts
├── skills/                   # Skill markdown files
│   ├── screener-in.md
│   ├── valuation-india.md
│   └── ...
├── workspace/                # Agent working files
├── watchlists/               # Your watchlists (plain markdown)
│   ├── main.md
│   └── tracking.md
├── db/
│   └── stocks.db             # SQLite stock universe + fundamentals
└── cache/                    # TTL cache for API responses
```

---

## 💬 Example Interactions

### Natural Language Screening

```
You: "Find me 5 high quality midcap companies with consistent profit growth"

ScreenerClaw:
  [Screener Agent] Translating query to filters...
  [Data Agent] Fetching midcap universe (500–30,000 Cr market cap)...
  [Analysis Agent] Computing quality + consistency scores...
  [Ranking Agent] Ranking 847 candidates...

  Top 5 results:
  1. Persistent Systems     Score: 82 | ROCE: 34% | 10yr profit CAGR: 28%
  2. Astral Poly Technik    Score: 78 | ROCE: 29% | 10yr profit CAGR: 23%
  3. Alkem Laboratories     Score: 76 | ROCE: 24% | 10yr profit CAGR: 19%
  4. Narayana Hrudayalaya  Score: 74 | ROCE: 22% | 10yr profit CAGR: 22%
  5. Deepak Nitrite         Score: 71 | ROCE: 28% | 10yr profit CAGR: 31%
  
  Reply "report [number]" for a deep analysis of any stock.
```

### Deep Report Request

```
You: "report 1"

ScreenerClaw (Analyst Agent — claude-opus):
  Generating full investment report for Persistent Systems...
  [2000-word report covering: business overview, moat analysis,
   financials, all 12 valuation models with scenarios,
   bull/bear thesis, risks, verdict]
```

### Portfolio Tracking

```
You: "How is my portfolio doing this month?"

ScreenerClaw: [reads your portfolio from watchlists/portfolio.md]
  Your portfolio (12 stocks) is up 3.2% this month vs Nifty 50 up 1.8%.
  
  Top performers: Deepak Parekh (↑8.1%), Pidilite (↑6.2%)
  Laggards: Bharti Airtel (↓2.1%), IEX (↓1.8%)
  
  XIRR since inception: 19.4% (vs Nifty: 14.2%)
```

### Automated Alert

```
[Sunday 9am — automated digest sent to Telegram]

ScreenerClaw: 📊 Weekly Digest — July 14, 2025

PORTFOLIO
• Up 1.2% this week. XIRR: 19.4%.
• HDFC Bank: Results tomorrow — consensus expects 15% NII growth

WATCHLIST UPDATES
• Asian Paints: Q1 volumes +8% YoY — recovery accelerating
• HDFC Bank: Now at PE 17.1, approaching your entry target of PE 16

NEW SCREENING IDEAS
• 3 quality midcap pharma stocks scoring above 70 — want details?

MARKET NOTES
• FII net buyers ₹4,200Cr this week
• Nifty PE at 22.1x (5yr avg: 20.8x — mildly elevated)
```

---

## 🗺️ Project File Structure (Python)

```
screenerclaw/
├── screenerclaw/
│   ├── __main__.py              # Entry point
│   ├── gateway/
│   │   ├── server.py            # FastAPI/WebSocket gateway
│   │   ├── router.py            # Binding resolution
│   │   └── auth.py              # Pairing, token auth
│   ├── agents/
│   │   ├── base.py              # Base agent class
│   │   ├── orchestrator.py      # Main routing + delegation agent
│   │   ├── screener.py          # NL → filter → candidate agent
│   │   ├── data_fetcher.py      # Multi-source data agent
│   │   ├── analyst.py           # Valuation + scoring agent
│   │   ├── report.py            # LLM report generation agent
│   │   ├── alert_watcher.py     # Price + fundamental alert agent
│   │   └── learning.py          # Memory + skill + config update agent
│   ├── channels/
│   │   ├── whatsapp.py          # Baileys bridge (via Node subprocess)
│   │   ├── telegram.py          # python-telegram-bot
│   │   ├── slack.py             # slack_bolt
│   │   ├── discord.py           # discord.py
│   │   └── cli.py               # Rich terminal UI
│   ├── llm/
│   │   ├── provider.py          # Unified LLM interface
│   │   ├── anthropic.py         # Claude adapter
│   │   ├── openai.py            # GPT adapter
│   │   ├── google.py            # Gemini adapter
│   │   ├── mistral.py           # Mistral adapter
│   │   └── ollama.py            # Ollama (local) adapter
│   ├── data/
│   │   ├── scrapers/
│   │   │   ├── screener_in.py
│   │   │   ├── nse.py
│   │   │   └── bse.py
│   │   ├── providers/
│   │   │   ├── yahoo_finance.py
│   │   │   └── alpha_vantage.py
│   │   ├── normalizer.py        # Standardise multi-source data
│   │   └── cache.py             # TTL cache
│   ├── valuation/
│   │   ├── dcf.py
│   │   ├── graham.py
│   │   └── earnings_based.py
│   ├── memory/
│   │   ├── session.py           # Session history + compaction
│   │   ├── workspace.py         # memory.md read/write
│   │   └── skills.py            # Skill file loading
│   ├── tools/
│   │   ├── registry.py          # All available tools
│   │   ├── screen.py            # Screen stocks tool
│   │   ├── fetch.py             # Fetch data tool
│   │   ├── analyse.py           # Run analysis tool
│   │   ├── alert.py             # Set/check alert tool
│   │   └── portfolio.py         # Portfolio read/write tool
│   ├── config.py                # Config loading + validation
│   └── secrets.py               # Encrypted secret management
├── frontend/                    # Next.js WebUI (optional)
├── requirements.txt
├── setup.py
└── tests/
```

---

## 📝 Summary

ScreenerClaw reimagines stock screening as an **autonomous, learning, multi-channel AI agent** — not a tool you log into, but an assistant that monitors markets 24/7, learns your investment style, and proactively surfaces opportunities.

The key differences from a traditional screener:

| Traditional Screener | ScreenerClaw |
|---------------------|--------------|
| You query it manually | It monitors and alerts proactively |
| Fixed set of filters | Natural language, learns your terms |
| Same output for everyone | Personalised to your style over time |
| One model/algorithm | Any LLM, swap anytime |
| Single interface | WhatsApp, Telegram, Web, CLI |
| You export and analyse manually | Generates full AI analysis reports |
| No memory | Remembers your portfolio, watchlists, preferences |

---

*Inspired by OpenClaw's agent architecture. Built for the Indian equity investor.*