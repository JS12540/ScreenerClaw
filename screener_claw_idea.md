# 🦞 ScreenerClaw — AI-Native Indian Stock Discovery & Intelligence Platform
### *OpenClaw-Inspired Multi-Agent Architecture for Autonomous Stock Intelligence*

> **Philosophy:** ScreenerClaw is not a screener with AI bolted on. It is an OpenClaw-style **autonomous agent system** where each agent has a role, memory, skills, and the ability to learn — applied entirely to Indian equity markets.
>
> The job of ScreenerClaw is not just to filter stocks. It is to **understand businesses** — their models, competitive moats, macro exposures, geopolitical sensitivities — and only then to value them. Valuation is step two. Business understanding is step one, always.

---

## 📋 Table of Contents

- [Core Design Principles](#-core-design-principles)
- [Authentication — The OpenClaw Way](#-authentication--the-openclaw-way)
- [High-Level Architecture](#-high-level-architecture)
- [Low-Level Architecture — Inside the Gateway](#-low-level-architecture--inside-the-gateway)
- [Multi-Agent System — Every Agent's Role](#-multi-agent-system--every-agents-role)
- [Agent Loop — How Every Query Becomes Intelligence](#-agent-loop--how-every-query-becomes-intelligence)
- [Channel System](#-channel-system)
- [Memory & Learning System](#-memory--learning-system)
- [Skills System](#-skills-system)
- [Data Pipeline — Sources, Fetching, Self-Healing](#-data-pipeline--sources-fetching-self-healing)
- [Step 1 — Business Understanding Engine](#-step-1--business-understanding-engine)
- [Step 2 — Macro and Geopolitical Impact Analysis](#-step-2--macro-and-geopolitical-impact-analysis)
- [Step 3 — Business Report and Outlook](#-step-3--business-report-and-outlook)
- [Step 4 — Valuation Engine (Stock-Type Adaptive)](#-step-4--valuation-engine-stock-type-adaptive)
- [Step 5 — Scoring and Ranking (Past + Future)](#-step-5--scoring-and-ranking-past--future)
- [Automation Layer — Cron, Alerts, Digests](#-automation-layer--cron-alerts-digests)
- [LLM Provider Abstraction](#-llm-provider-abstraction)
- [Security Model](#-security-model)
- [Configuration Reference](#-configuration-reference)
- [Installation and Setup](#-installation-and-setup)
- [Project File Structure](#-project-file-structure)
- [Example Interactions](#-example-interactions)

---

## 🎯 Core Design Principles

ScreenerClaw is built on the same philosophical pillars as OpenClaw:

| Principle | What it means for ScreenerClaw |
|-----------|-------------------------------|
| **Business-first** | Understand the business model, moat, and macro before any number is touched |
| **Channel-agnostic** | WhatsApp, Telegram, Slack, CLI, Web — same brain, any interface |
| **Self-improving** | Agents learn your investment style over time and personalise outputs |
| **Multi-agent** | Specialised agents collaborate — no monolith |
| **LLM-agnostic** | Claude, GPT-4, Gemini, Mistral, Ollama — swap freely |
| **Automation-first** | Cron jobs, price alerts, earnings alerts — works while you sleep |
| **No hidden cloud** | Data flows: source → your machine → LLM API → you. Nothing else. |
| **Stock-type aware** | Different stock types (cyclical, FMCG, bank, infra, pharma) get different valuation models |

---

## 🔑 Authentication — The OpenClaw Way

### Channel-Level DM Policies

```
dmPolicy options:
  pairing    → Unknown sender gets a 6-digit code. You approve once.
               That sender is permanently in your allowlist.
  allowlist  → Only pre-approved IDs can interact
  open       → Anyone can query (NOT recommended for personal financial data)
  disabled   → Channel inactive
```

### Pairing Flow (Default and Recommended)

```
1. Someone messages your ScreenerClaw bot for the first time
2. Bot replies: "Send code 847-291 to +91-XXXXX to pair this device"
3. You send the code from your phone — confirmed
4. That sender is permanently approved — no login ever again
5. Revoke anytime: screenerclaw pairing revoke <channel> <id>
```

### Screener.in Authentication

ScreenerClaw uses **your Screener.in account credentials** to log in and perform filtered searches, then parses the resulting HTML. This gives access to all of Screener.in's pre-built filters, custom screens, and the full export endpoint.

```bash
# Store credentials securely (AES-256 encrypted at rest)
screenerclaw secrets set SCREENER_USERNAME "your@email.com"
screenerclaw secrets set SCREENER_PASSWORD "yourpassword"

# ScreenerClaw logs in via session, maintains cookie, auto-refreshes on expiry
# Login URL: https://www.screener.in/login/
# After login: uses session cookie for all subsequent requests
```

**Why credentials?** Screener.in's filter export endpoint (`https://www.screener.in/screen/raw/?query=...`) requires a logged-in session and returns full tabular data — this is how ScreenerClaw fetches bulk filtered results efficiently without scraping individual pages.

### API Token Auth (for programmatic access)

```bash
# Generate a token for your scripts / dashboard
screenerclaw auth token create --name "my-dashboard"
# returns: sck_live_XXXXXXXXXXXXXXXX

# Use in HTTP requests:
# Authorization: Bearer sck_live_XXXXXXXXXXXXXXXX
```

### Secrets Management

```bash
screenerclaw secrets set ANTHROPIC_API_KEY   "sk-ant-..."
screenerclaw secrets set SCREENER_USERNAME   "you@email.com"
screenerclaw secrets set SCREENER_PASSWORD   "yourpassword"
screenerclaw secrets set ALPHAVANTAGE_KEY    "XXXXXXXX"

# Stored in ~/.screenerclaw/secrets/ (AES-256 encrypted)
# Never appear in logs, transcripts, config files, or LLM context
```

---

## 🏗 High-Level Architecture

```mermaid
flowchart TB
    subgraph CHANNELS["📡 Channels (Input)"]
        direction LR
        WA["📱 WhatsApp"] --- TG["✈️ Telegram"] --- SL["💬 Slack"] --- DC["🎮 Discord"] --- CLI["💻 CLI"] --- WEB["🌐 WebUI"]
    end

    subgraph GATEWAY["🏛 ScreenerClaw Gateway  port 18900"]
        GW["Gateway Server\nWebSocket + HTTP"]
        ROUTER["Binding Router\n(which agent handles this?)"]
        AUTH["Auth Layer\n(pairing / token / allowlist)"]
        GW --> AUTH --> ROUTER
    end

    subgraph AGENTS["🤖 Multi-Agent System"]
        direction LR
        ORCH["🎭 Orchestrator\n(routes, delegates)"]
        BIZ["🏢 Business Understanding\n(model, moat, costs)"]
        MACRO["🌍 Macro and Geo Agent\n(India context, impact)"]
        DATA["📊 Data Agent\n(multi-source fetcher)"]
        VAL["🧮 Valuation Agent\n(adaptive per stock type)"]
        RANK["🏆 Ranking Agent\n(past and future scoring)"]
        REPORT["📝 Report Agent\n(LLM-generated analysis)"]
        ALERT["🔔 Alert Agent\n(price and fundamental)"]
        LEARN["🧠 Learning Agent\n(memory, skills, config)"]
    end

    subgraph MEMORY["💾 Memory and Storage"]
        SESS["Session History\n~/.screenerclaw/sessions/"]
        MEMF["User Memory\n~/.screenerclaw/memory.md"]
        SKILLS_D["Skills\n~/.screenerclaw/skills/"]
        WATCH["Watchlists\n~/.screenerclaw/watchlists/"]
    end

    subgraph SOURCES["🌐 Data Sources"]
        SCR["Screener.in\n(login + filter + HTML parse)"]
        NSEPY["nsepython\n(NSE live + historical)"]
        YF["Yahoo Finance\nyfinance"]
        BSE_S["BSE API\n(announcements, metadata)"]
    end

    subgraph LLM["🧠 LLM Providers"]
        direction LR
        CLAUDE["Anthropic Claude"] --- GPT["OpenAI GPT"] --- GEMINI["Gemini"] --- OLLAMA["Ollama (local)"]
    end

    CHANNELS --> GATEWAY
    GATEWAY --> AGENTS
    AGENTS <--> MEMORY
    AGENTS --> SOURCES
    AGENTS --> LLM
```

---

## 🔬 Low-Level Architecture — Inside the Gateway

```mermaid
flowchart LR
    subgraph INBOUND["📥 Inbound Path"]
        CH_ADAPTER["Channel Adapter\n(Telegram/WhatsApp/CLI)"]
        MSG_NORM["Message Normalizer\n(envelope + intent)"]
        ACCESS["Access Control\n(allowlist / pairing)"]
        DEDUP["Deduplication\n(idempotency cache)"]
    end

    subgraph ROUTING["🔀 Routing Engine"]
        INTENT["Intent Classifier\n(screen / analyse / alert / report)"]
        BINDING["Binding Matcher\n(intent → agentId)"]
        QUEUE["Command Queue\n(per-session lane)"]
    end

    subgraph SESSION["🗂 Session Layer"]
        SID["Session ID Resolver\n(main / group / cli)"]
        LOCK["Write Lock\n(serialize per session)"]
        CTX["Context Engine\n(memory.md + history + skills)"]
        PRUNE["Auto-Compaction\n(token budget)"]
    end

    subgraph EXEC["⚙️ Execution Layer — 5-Step Pipeline"]
        S1["Step 1: Business Understanding\n(model, moat, costs, products)"]
        S2["Step 2: Macro and Geopolitical\n(India context + earnings impact)"]
        S3["Step 3: Report and Outlook\n(short / mid / long term)"]
        S4["Step 4: Valuation\n(adaptive per stock type)"]
        S5["Step 5: Scoring and Ranking\n(past + forward looking)"]
    end

    subgraph OUTBOUND["📤 Outbound Path"]
        CHUNK["Response Chunker\n(4000 char per message)"]
        SEND["Channel Sender\n(typed per platform)"]
        TYPING["Typing Indicator\n(presence)"]
    end

    CH_ADAPTER --> MSG_NORM --> ACCESS --> DEDUP
    DEDUP --> INTENT --> BINDING --> QUEUE
    QUEUE --> SID --> LOCK --> CTX --> PRUNE
    PRUNE --> S1 --> S2 --> S3 --> S4 --> S5
    S5 --> CHUNK --> TYPING --> SEND
```

---

## 🤖 Multi-Agent System — Every Agent's Role

### Agent Roster

```json5
// ~/.screenerclaw/config.json5

{
  agents: {
    list: [
      {
        id: "personal",
        role: "orchestrator",
        default: true,
        workspace: "~/.screenerclaw/workspace-personal",
        model: "anthropic/claude-sonnet-4-6",
        memory: "~/.screenerclaw/memory.md",
        skills: ["screener-in", "nsepython", "business-analysis", "valuation-india", "sector-india"],
      },
      {
        id: "business-analyst",
        role: "business_understanding",
        workspace: "~/.screenerclaw/workspace-business",
        model: "anthropic/claude-opus-4-6",   // best model — deep reading and reasoning
        skills: ["business-analysis", "moat-framework", "sector-india", "management-quality"],
      },
      {
        id: "macro-agent",
        role: "macro_geopolitical",
        workspace: "~/.screenerclaw/workspace-macro",
        model: "anthropic/claude-sonnet-4-6",
        skills: ["india-macro", "rbi-policy", "geopolitical-risks", "sector-cyclicality"],
      },
      {
        id: "data-fetcher",
        role: "data",
        workspace: "~/.screenerclaw/workspace-data",
        model: "openai/gpt-4o-mini",           // cheaper model — structured data tasks only
        tools: {
          allow: ["bash", "http_fetch", "cache_read", "cache_write", "screener_filter"],
          deny:  ["report_generate"],
        },
      },
      {
        id: "valuation-agent",
        role: "valuation",
        workspace: "~/.screenerclaw/workspace-valuation",
        model: "anthropic/claude-opus-4-6",
        skills: ["valuation-india", "dcf-india", "cyclical-valuation", "margin-of-safety"],
      },
      {
        id: "ranking-agent",
        role: "ranking",
        workspace: "~/.screenerclaw/workspace-ranking",
        model: "anthropic/claude-sonnet-4-6",
        skills: ["scoring-framework", "forward-looking"],
      },
      {
        id: "report-agent",
        role: "report_generation",
        workspace: "~/.screenerclaw/workspace-report",
        model: "anthropic/claude-opus-4-6",    // best model — final investor report
      },
      {
        id: "learning-agent",
        role: "learning",
        workspace: "~/.screenerclaw/workspace-learning",
        model: "anthropic/claude-sonnet-4-6",
        tools: {
          allow: ["memory_write", "skills_write", "config_write", "watchlist_write"],
        },
      },
    ]
  }
}
```

### Binding Resolution — Which Agent Handles What

```mermaid
flowchart TD
    MSG["Inbound message"] --> IC["Intent Classifier"]
    IC -->|"analyse / understand / moat / business"| BA["business-analyst\nclaude-opus"]
    IC -->|"macro / geopolitical / RBI / impact"| MA["macro-agent\nclaude-sonnet"]
    IC -->|"fetch / data / financials / screener"| DF["data-fetcher\ngpt-4o-mini"]
    IC -->|"value / DCF / fair price / MOS"| VA["valuation-agent\nclaude-opus"]
    IC -->|"rank / score / compare / best"| RA["ranking-agent\nclaude-sonnet"]
    IC -->|"report / deep dive / full analysis"| REP["report-agent\nclaude-opus"]
    IC -->|"alert / notify / watch / remind"| AW["alert-watcher\ngemini-flash"]
    IC -->|"remember / save / define / update"| LA["learning-agent\nclaude-sonnet"]
    IC -->|"screen / find / general query"| ORCH["personal orchestrator\nclaude-sonnet"]
    ORCH -->|"delegates subtasks"| BA & DF & VA & RA & REP
```

**Priority for binding resolution (most to least specific):**

```
1. Explicit agent mention     "business-analyst, tell me about Pidilite's moat"
2. Intent classification      "set alert" → alert-watcher; "understand" → business-analyst
3. Channel binding            WhatsApp → personal (default orchestrator)
4. Task complexity            Multi-step → orchestrator delegates
5. Default agent              personal
```

### Agent-to-Agent Orchestration — Full Example

```
You (WhatsApp): "Find 5 undervalued pharma stocks and give a deep report on the best one"

Orchestrator:
  1. sessions_send(data-fetcher,
       "Fetch all NSE pharma stocks. Filter: ROCE > 15%, D/E < 0.5, 5yr profit CAGR > 12%")
     returns: 18 candidates

  2. sessions_send(business-analyst,
       "For each candidate: summarise business model, competitive advantage,
        revenue model, key products, cost structure in 3 sentences each")
     returns: business profiles for 18 companies

  3. sessions_send(macro-agent,
       "How does current India macro (RBI rates, USD/INR, API pricing, China competition)
        affect each candidate? Rank by macro tailwind/headwind score.")
     returns: macro scores per company

  4. sessions_send(valuation-agent,
       "Value each company using the appropriate method for pharma. Pick top 3 undervalued.")
     returns: 3 candidates with valuations and MOS prices

  5. sessions_send(ranking-agent,
       "Score and rank these 3 on quality + growth + business strength + future outlook.")
     returns: Ajanta Pharma as number 1

  6. sessions_send(report-agent,
       "Generate full brutally honest investment report for Ajanta Pharma.
        Business deep dive, macro analysis, valuation, outlook short/mid/long term.")
     returns: 2500-word investment report

  7. Orchestrator synthesises top 5 list + full report on number 1
     Sends to WhatsApp in chunked messages
```

---

## 📡 Channel System

### Supported Channels

| Channel | Auth method | What you need |
|---------|-------------|--------------|
| **WhatsApp** | Pairing (QR scan once) | Dedicated SIM or personal number |
| **Telegram** | BotFather token | 30 seconds to create |
| **Slack** | Slack App + tokens | Free personal workspace |
| **Discord** | Bot Application | Discord developer portal |
| **CLI** | Local (always trusted) | Built-in, no setup |
| **WebUI** | Bearer token | Auto-generated on install |

### Channel Configuration

```json5
{
  channels: {
    whatsapp: {
      dmPolicy: "pairing",
      allowFrom: ["+919876543210"],
      groupPolicy: "allowlist",
      allowedGroups: ["120363XXXXXXXXXX@g.us"],  // your private investing group
      ackReaction: { emoji: "📊", direct: true, group: "mentions" },
      textChunkLimit: 4000,
    },
    telegram: {
      botToken: "123456:ABC...",
      dmPolicy: "pairing",
      groupPolicy: "allowlist",
      allowedGroups: ["-1001234567890"],
    },
    slack: {
      botToken: "xoxb-...",
      appToken: "xapp-...",
      dmPolicy: "allowlist",
      allowFrom: ["U0123456789"],
    },
    cli: {
      dmPolicy: "open",    // local CLI always trusted
    },
  }
}
```

---

## 🧠 Memory and Learning System

ScreenerClaw agents maintain **four memory layers**, exactly mirroring the OpenClaw model:

### Layer 1 — Session History (Short-Term)

```
~/.screenerclaw/sessions/
  personal-main.md          # all your personal DM sessions (all channels)
  business-analyst-42.md    # business analyst working session
  alert-watcher.md          # alert agent ongoing log
  valuation-session-18.md   # valuation working memory
```

Auto-compaction kicks in when context grows too long. Old turns are summarised into a compressed block. The agent never loses material facts — only conversational filler is trimmed.

### Layer 2 — User Memory (Long-Term Facts)

The agent writes to `memory.md` whenever it learns something about you:

```markdown
# ScreenerClaw User Memory — Updated 2025-07-14

## Investment Style
- Prefers: Quality compounder stocks (ROCE > 20%, consistent profit growth > 15% for 5+ yrs)
- Avoids: High debt companies (D/E > 1.5), loss-making companies, commodity-only businesses
- Typical holding period: 3-5 years (long-term investor, not a trader)
- Portfolio size: 12-15 stocks, max 12% single stock weight
- Risk tolerance: Moderate — large/midcap preferred, smallcap only with strong moat evidence

## Sector Preferences
- Interested in: Pharma (domestic formulations), Private Banking, FMCG, Capital Goods, IT Services
- Avoids: PSU banks (governance), Real estate (accounting opacity), Pure commodity plays

## Custom Vocabulary (Learned Definitions)
- "fortress balance sheet" means D/E < 0.3, current ratio > 2.0, interest coverage > 10, CFO/PAT > 0.8
- "compounder" means 10yr profit CAGR > 15%, ROCE > 20%, promoter holding > 50%, consistent margins
- "undervalued" means PE < sector average AND PB < 3 AND PEG < 1.2
- "safe dividend" means yield > 2%, payout ratio < 60%, D/E < 0.5, 5yr dividend CAGR > 8%

## Watchlist Context
- HDFC Bank: watching since Jan 2025, entry target PE < 16, fundamentals remain strong
- Pidilite: in portfolio since 2022, tracking quarterly volume growth
- Ajanta Pharma: interested post-recent correction, waiting for Q2 clarity

## Alert Preferences
- WhatsApp: price alerts only (immediate delivery)
- Telegram: weekly digest (Sunday 9am IST), earnings alerts
- No alerts between 11pm and 7am IST

## Macro Views Noted
- User is concerned about USD/INR impact on IT margins
- User believes rural recovery will benefit FMCG in next 2 quarters
- User is tracking RBI rate cut cycle for its impact on financials
```

### Layer 3 — Skills (Domain Knowledge)

Skills are markdown files that teach agents platform-specific knowledge they cannot reliably infer:

```
~/.screenerclaw/skills/
  screener-in.md            # login flow, filter URL format, HTML parsing, rate limits
  nsepython.md              # library usage, live price, historical OHLC, corporate actions
  business-analysis.md      # framework for understanding business models and moats
  moat-framework.md         # Porter's 5 forces, Buffett moat types applied to Indian market
  india-macro.md            # RBI, inflation, monsoon, GST, PLI — how each affects sectors
  geopolitical-risks.md     # China+1, US tariffs, oil price, wars — sector-level impact
  valuation-india.md        # India-specific params: G-Sec 7%, ERP 6%, sector WACC table
  dcf-india.md              # DCF parameter choices for Indian stocks
  cyclical-valuation.md     # Midcycle EV/EBITDA, P/B at trough, replacement cost
  sector-india.md           # All NSE/BSE sectors, peer group definitions, cyclicality
  scoring-framework.md      # Past vs forward-looking weights in composite score
  management-quality.md     # Promoter integrity, governance checks, remuneration patterns
  margin-of-safety.md       # MOS calculation per stock type
  quarterly-results.md      # BSE announcement parsing, key metrics to extract
  custom-ratios.md          # User-defined custom formulas and terms (agent writes this)
```

**The agent writes its own skills.** When you define a custom term:

```
You: "From now on 'fortress balance sheet' means D/E < 0.3, current ratio > 2,
     interest coverage > 10, and CFO/PAT > 0.8"

Agent: Understood. Saving permanently to skills/custom-ratios.md
       Future sessions will use your definition automatically.
```

### Layer 4 — Config Evolution

The agent can modify `config.json5` to add new cron jobs, add watchlist entries, update alert thresholds, and change which LLM model handles which agent role — all by you telling it to in plain English.

---

## 📦 Skills System

### Built-in Skills (Auto-installed on Setup)

| Skill | What it teaches the agent |
|-------|--------------------------|
| `screener-in` | Login flow, filter URL construction, HTML parse selectors, rate limiting, export endpoint |
| `nsepython` | Library import patterns, live price fetch, historical OHLCV, corporate actions, index data |
| `business-analysis` | Framework for decomposing business model, revenue streams, cost structure, moat types |
| `moat-framework` | Porter's 5 forces, network effects, switching costs, cost advantages applied to Indian sectors |
| `india-macro` | RBI rate cycles, inflation, monsoon impact on rural demand, PLI schemes, fiscal deficit trends |
| `geopolitical-risks` | China+1 opportunity, US tariff exposure, oil price sensitivities, war impact on freight |
| `valuation-india` | India-specific DCF parameters, sector WACC table, G-Sec rate auto-fetch, ERP |
| `dcf-india` | Two-stage DCF, FCF DCF, reverse DCF with India parameters |
| `cyclical-valuation` | Midcycle EV/EBITDA, P/B at trough, replacement cost for metals, cement, chemicals |
| `sector-india` | NSE sector taxonomy, peer group definitions, which metrics matter per sector |
| `margin-of-safety` | How to calculate MOS per stock type — conservative vs base case |
| `scoring-framework` | How to combine past financials and forward-looking estimates into composite score |
| `management-quality` | Promoter holding trend, pledging, related party transactions, governance red flags |
| `quarterly-results` | BSE XBRL/PDF announcement parsing, key line items, beat/miss detection |

---

## 🔄 Data Pipeline — Sources, Fetching, Self-Healing

### Data Sources

| Source | Library / Method | What it provides |
|--------|-----------------|-----------------|
| **Screener.in** | Login → session cookie → filter URL → HTML parse | 10-year P&L, Balance sheet, Cash flow, Peer comparison, Shareholding, filter results |
| **nsepython** | `pip install nsepython` | Live price, historical OHLCV, corporate actions, index constituents, market cap, sector |
| **Yahoo Finance** | `yfinance` | Financial statements, TTM metrics, price history, dividends |
| **BSE** | BSE REST API (public) | Corporate announcements, quarterly results, XBRL filings, company metadata |

**No local stock database is maintained.** All data is fetched fresh on demand and cached with appropriate TTLs.

### Screener.in Integration — How It Works

```python
# backend/scrapers/screener_scraper.py

class ScreenerClient:
    """
    Login once per session, maintain cookie, use filter export endpoint.
    No per-page scraping needed for bulk screening.
    """

    LOGIN_URL   = "https://www.screener.in/login/"
    FILTER_URL  = "https://www.screener.in/screen/raw/"
    COMPANY_URL = "https://www.screener.in/company/{symbol}/consolidated/"

    async def login(self):
        # 1. GET login page, extract CSRF token
        # 2. POST username + password + CSRF to LOGIN_URL
        # 3. Store session cookie -> auto-refresh on 403

    async def screen(self, query: str) -> list[dict]:
        """
        Convert NL query to Screener.in filter string via LLM,
        POST to FILTER_URL, parse returned table.

        Filter URL format:
        ?query=Market+Capitalization+>+500+AND+ROCE+>+20
        &sort=Market+Capitalization&order=desc&limit=50&page=1
        """

    async def get_company(self, symbol: str) -> dict:
        """
        Fetch full company page for one stock.
        Parse: 10yr P&L table, Balance Sheet, Cash Flow, Key Ratios, Peers, Shareholding.
        """
```

### nsepython Integration

```python
# backend/scrapers/nse_scraper.py

from nsepython import nse_eq, equity_history, nse_get_index_list

class NSEClient:
    def get_live_price(self, symbol: str) -> dict:
        return nse_eq(symbol)
        # Returns: lastPrice, change, pChange, totalTradedVolume, marketCap, etc.

    def get_historical(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        return equity_history(symbol, "EQ", start, end)

    def get_index_constituents(self, index: str = "NIFTY 500") -> list[str]:
        return nse_get_index_list(index)

    def classify_market_cap(self, market_cap_cr: float) -> str:
        if market_cap_cr > 20000: return "large"
        if market_cap_cr > 5000:  return "mid"
        return "small"
```

### Cache Strategy (File-Based, No Database)

```python
CACHE_TTL = {
    "fundamentals":    86400,    # 24 hours — Screener.in full company page
    "screener_filter": 1800,     # 30 minutes — NL filter query results
}
```

### Self-Healing Fetch Logic

```
Screener.in 403 (session expired)
  → Re-login automatically with stored credentials
  → Retry the original request
  → If credentials also fail: alert user "Please check your Screener.in password"

NSE API timeout or 429
  → Exponential backoff: 1s, 2s, 4s, 8s (max 3 retries)
  → Fall back to Yahoo Finance for same data
  → Log as stale, mark timestamp

Yahoo Finance missing data
  → Fall back to Screener.in for same field
  → If all sources fail: mark metric as N/A, do not block pipeline

BSE announcement fetch fail
  → Retry after 30s
  → Use last known announcement data with stale marker
```

---

## 🏢 Step 1 — Business Understanding Engine

> **This is always the first step before any financial analysis.**
> A stock is a fractional ownership of a real business. Understanding what that business does, how it makes money, what protects it from competition, and what it costs to run — this must come before any P/E ratio is examined.

### What the Business-Analyst Agent Does

The business-analyst agent (running Claude Opus) builds a comprehensive business profile by reading the company description from Screener.in, annual report key sections from BSE filings, management commentary from concalls, and peer comparison data.

### Dimension 1 — Business Model

```
Questions answered:
  What does this company sell — products, services, or both?
  Who are its customers — B2B, B2C, Government, or Export?
  How does it reach customers — direct, distributor, platform, or tender?
  What is the revenue model — transactional, subscription, project, annuity, or mixed?
  Is revenue recurring or lumpy?
  What percentage of revenue is repeat vs new customer?
  Geography mix — domestic vs export, key export markets
```

### Dimension 2 — Competitive Advantage (Moat Analysis)

```
Moat types checked using the moat-framework skill:

  Cost advantage:      Can they produce cheaper than peers? Why?
  Switching costs:     How painful is it for a customer to leave?
  Network effects:     Does the product get more valuable with more users?
  Intangible assets:   Brands, patents, regulatory licences, proprietary formulations
  Efficient scale:     Natural monopoly or duopoly in a niche market?

For each moat type:
  → Present / Absent / Weak / Moderate / Strong
  → Specific evidence from the business (not just assertion)
  → Moat durability: is it strengthening or eroding?

Replacement cost analysis:
  How much would it cost to build this business from scratch today?
  What barriers would a new entrant face — regulatory, capital, time, relationships?
  Is the market cap justified relative to replacement cost?
```

### Dimension 3 — Revenue Deep Dive

```
  Revenue segments: Break down by product, geography, customer type
  Growth drivers per segment: what causes each segment to grow?
  Revenue quality: Is it cash-collecting or deferred? Receivables trend?
  Pricing power: Can they raise prices without losing volume?
  Customer concentration risk: top 10 customers as % of revenue
  Seasonality: which quarter is strongest and weakest and why?
```

### Dimension 4 — Cost Structure and Raw Materials

```
  Fixed vs variable cost split — operating leverage implications
  Key raw materials: what are they, who supplies them, price volatility
  Input cost pass-through ability: can they pass cost inflation to customers?
  Labour cost sensitivity: skilled vs unskilled, wage inflation exposure
  Energy cost exposure: power-intensive or not?
  Freight and logistics sensitivity: domestic or export-dependent
  Operating margin trend: expanding, compressing, or stable?
```

### Dimension 5 — Management Quality

```
  Promoter holding trend — increasing signals confidence, decreasing signals concern
  Promoter pledge level — any pledge is a red flag, quantify it
  Related party transactions as % of revenue — high means governance risk
  Management remuneration vs profit growth — are they extracting value?
  Capital allocation history — acquisitions value-creating?, capex discipline
  Dividend policy — consistent, increasing, or erratic?
  Track record — have they delivered on past guidance?
```

### Business Understanding Output Format

```markdown
## Business Profile — Ajanta Pharma (AJANTPHARM)

### Business Model
Specialty generics pharma company. Revenue mix: ~35% domestic formulations (branded),
~65% international generics (Africa 32%, Asia 18%, USA 15%). Revenue model is
transactional — prescription fill — with branded domestic being annuity-like because
doctors prescribe repeatedly, and export being competitive tender-based.

### Moat Assessment — MODERATE-STRONG
Cost advantage (MODERATE): Vertically integrated for key APIs. Lower cost base than US/EU peers.
Intangible assets (STRONG): 2,000+ product registrations across 30+ countries.
  Regulatory filings are a 2-5 year moat. USFDA-approved Dahej plant.
Switching costs (MODERATE in domestic): Doctors develop prescribing habits.
  Weak in export generics — pure price competition.
Replacement cost: Rs 8,000–10,000 Cr to replicate global registrations, plant, brand equity.
  Current MCap Rs 22,000 Cr = 2.2–2.75x replacement cost.

### Revenue Breakdown
Domestic 35%: Ophthalmology, Dermatology, Cardiology specialty segments.
Export Africa 32%: Malaria, anti-infectives — volume-driven, stable.
Export Asia 18%: Branded generics — higher margin than Africa.
USA 15%: Growing from low base. 60 ANDA filings pending.

### Cost Structure
Raw material: ~35% of revenue (API costs, partially in-house)
Employee: ~18% (R&D-heavy, skilled workforce)
R&D expense: 6-7% of revenue (high for generics — sustaining registrations)
Power/fuel: Low sensitivity (pharma is not energy-intensive)

### Management Quality
Promoter holding: 66.1% (stable, no pledge). Family-run Mannalal Group.
Related party: less than 2% revenue — clean.
Remuneration: less than 3% of PAT — reasonable.
Capital allocation: Conservative — no debt-funded acquisitions. Steady R&D investment.
Track record: Delivered 5yr profit CAGR of 14.8% vs guidance of 12-15%.
```

---

## 🌍 Step 2 — Macro and Geopolitical Impact Analysis

> After understanding the business, the macro-agent maps the current Indian and global macro environment to the specific business model. This is not generic commentary — it is a targeted assessment of how each factor specifically impacts this company's earnings.

### India Macro Factors Assessed

| Factor | What is assessed |
|--------|-----------------|
| **RBI Rate Cycle** | Expansionary or contractionary? Impact on cost of capital, consumer demand, NBFC/banking spreads |
| **INR/USD Rate** | For exporters: revenue in USD translated to INR — tailwind or headwind. For importers of raw materials: cost impact |
| **Inflation (CPI/WPI)** | Input cost pressure. Can the company pass it on? Margin impact. |
| **Monsoon and Rural Demand** | For FMCG, Agri, 2W, tractor companies — quantify rural sales exposure |
| **Government Capex and PLI** | For capital goods, defence, infra, manufacturing — PLI eligibility and beneficiary status |
| **GST Collections** | Proxy for economic activity and government capacity to spend |
| **Credit Growth** | For banks and NBFCs — is credit growth accelerating or slowing? NPA cycle status |
| **Real Estate Cycle** | For building materials, paints, cables, sanitaryware — where are we in the cycle? |
| **Crude Oil Price** | For paints, chemicals, logistics, aviation — quantify crude as % of COGS |

### Geopolitical Factors Assessed

| Factor | What is assessed |
|--------|-----------------|
| **China+1 Manufacturing Shift** | Is this company a beneficiary? What % of global orders could shift to India? |
| **US Tariffs and Trade Policy** | For IT services, pharma, textiles — US revenue exposure and tariff risk |
| **Middle East Conflict and Shipping** | Freight cost impact — especially for export-heavy businesses |
| **Russia-Ukraine and European Demand** | For IT services (EU clients), specialty chemicals, bulk pharma |
| **China Competition** | For specialty chemicals, APIs, solar, steel — is Chinese supply undercutting? |
| **US FDA and EU Regulatory** | For pharma — USFDA import alerts, plant inspection outcomes |

### Macro Output Format

```markdown
## Macro and Geopolitical Impact — Ajanta Pharma (July 2025 context)

### Tailwinds
INR depreciation vs USD: Ajanta earns ~65% revenue in foreign currency.
  For every 1% INR depreciation, EBIT improves ~Rs 30-35 Cr (estimated).

China+1 API opportunity: India gaining global API supply chain share.
  Ajanta's in-house API integration insulates it AND positions for new supply contracts.

Africa pharma demand: WHO-supported antimalarial programs plus rising middle class.
  Multi-year secular tailwind — not cyclical.

RBI rate cuts expected H2 2025: Lower cost of capital. Ajanta is debt-free.
  Indirect benefit via better consumer credit enabling more prescription fills.

### Headwinds
US Generic Price Erosion: Industry-wide 6-10% annual price erosion in US generics.
  Ajanta's 15% US revenue at risk — partially offset by new ANDAs.

API Input Cost Volatility: Some APIs sourced from China. Trade friction risk.
  Mitigation: 40% vertical integration, working to increase.

USFDA Inspection Risk: Dahej facility due for re-inspection. Binary risk.

### Net Macro Verdict: POSITIVE with watchpoints
Near-term: INR weakness + Africa volume growth = earnings tailwind.
Medium-term: US ANDA pipeline materialising = earnings inflection.
Key risk: FDA inspection outcome + China API supply disruption.
```

---

## 📝 Step 3 — Business Report and Outlook

> Two documents are generated. The first synthesises business understanding and macro impact. The second gives a brutally honest short/medium/long-term outlook with direct earnings impact estimates.

### Report 1 — Business Intelligence Report (~1500-2000 words)

```
1. Business overview in plain English (no jargon)
2. What makes this business tick (or not tick)
3. Moat — how wide, how durable, what is eroding it
4. Revenue model and growth engines
5. Cost structure and margin dynamics
6. Management track record and governance
7. Macro tailwinds and headwinds — quantified where possible
8. Geopolitical exposure — specific risks and opportunities
9. Key risks (business, regulatory, macro, competitive)
10. What needs to go right for this business to outperform
```

### Report 2 — Brutally Honest Outlook

**Short Term (0–12 months):**
```
  What are the 2-3 quarterly catalysts or risks?
  What is management guiding for? Is it credible?
  What events (FDA inspection, rate decision, monsoon data, election) move this stock?
  Near-term EPS estimate and probability distribution
  Honest assessment: is this a good entry point right now?
```

**Medium Term (1–3 years):**
```
  What is the earnings trajectory most likely to look like?
  Will the moat strengthen or erode over this period?
  What are the 2-3 things that could derail the thesis?
  Estimated EPS range for year 2 and year 3 (base, bear, bull)
  What would make you sell?
```

**Long Term (3–10 years):**
```
  Is this a business that will be meaningfully larger in 10 years?
  What structural trends support or threaten the business?
  What is the plausible compounding rate of earnings?
  Is management thinking in decades or quarters?
  What would change your long-term thesis?
```

---

## 🧮 Step 4 — Valuation Engine (Stock-Type Adaptive)

> **Valuation method selection depends on the type of business.** A single method applied to all stocks is wrong. ScreenerClaw classifies each stock and picks the appropriate 4–5 methods. Cyclicals get midcycle EV/EBITDA, not DCF. Banks get P/Book adjusted for RoE, not PE.

### Full Valuation Tool Registry

All valuation models are implemented as callable Python tools. The valuation agent selects 4–5 of these per stock based on its classified type:

```python
# valuation/registry.py — complete tool set available to the valuation agent

VALUATION_TOOLS = [
    "dcf_gurufocus",    # Two-stage EPS DCF — 10yr high-growth + 10yr terminal (GuruFocus method)
    "dcf_fcf",          # Same two-stage structure but uses Free Cash Flow per share instead of EPS
    "graham_number",    # √(22.5 × EPS × Book Value per share) — Benjamin Graham's absolute floor
    "graham_formula",   # EPS × (8.5 + 2g) × 4.4 / AAA_yield — growth-adjusted intrinsic value
    "pe_based",         # PE vs sector median, vs own 5yr/10yr avg, vs Graham's fair PE of 15x
    "epv",              # Earnings Power Value (Greenwald) — zero-growth sustainable earnings value
    "owner_earnings",   # Buffett's Owner Earnings DCF: PAT + D&A - Maintenance Capex, discounted
    "ddm",              # Gordon Growth Model: D1 / (CoE - g) — for consistent dividend payers
    "peg_ratio",        # Peter Lynch: PEG = PE / EPS_CAGR — PEG < 1 signals undervaluation
    "reverse_dcf",      # Invert DCF: what EPS CAGR does today's price imply? Compare to reality.
    "ev_ebitda",        # EV / EBITDA vs sector median and historical — primary for cyclicals/infra
]

# Each tool outputs: { bear, base, bull } intrinsic values
# Each tool also outputs: implied_upside, margin_of_safety_price, mos_gap_pct
```

### Method-to-Tool Mapping Reference

| Tool | Best for | Not suitable for |
|------|----------|-----------------|
| `dcf_gurufocus` | Quality compounders with predictable EPS growth | Cyclicals, loss-makers, banks |
| `dcf_fcf` | Asset-light businesses with strong FCF | Capital-intensive, early-stage |
| `graham_number` | Value check on profitable, asset-backed firms | High-PE growth stocks, banks |
| `graham_formula` | Moderate-growth profitable businesses | Cyclicals, negative-EPS years |
| `pe_based` | Any profitable business as context | Primary valuation for any type |
| `epv` | Stable businesses — what are current earnings worth with zero growth? | Cyclicals at peak |
| `owner_earnings` | Mature businesses with clear capex split | Early-stage, unpredictable capex |
| `ddm` | Dividend-paying defensives, utilities, mature PSUs | Non-dividend payers, growth stocks |
| `peg_ratio` | Mid-growth businesses where PE alone is insufficient | Cyclicals, loss-makers |
| `reverse_dcf` | **All types** — cross-check what market is pricing in | Never use as primary method |
| `ev_ebitda` | Cyclicals, infra, capital goods, banks not applicable | Asset-light, zero-EBITDA firms |

---

### Stock Type Classification

```python
STOCK_TYPES = {
    "QUALITY_COMPOUNDER":  ["Pharma", "FMCG", "Specialty Chemicals", "IT Services", "Consumer Brands"],
    "CYCLICAL":            ["Metals", "Mining", "Cement", "Chemicals (commodity)", "Capital Goods"],
    "FINANCIAL":           ["Private Banks", "PSU Banks", "NBFCs", "Insurance", "Mutual Fund AMC"],
    "INFRASTRUCTURE":      ["Roads", "Railways", "Power", "Ports", "Airport", "Defence"],
    "REAL_ASSET":          ["Real Estate", "Hospitality", "Media"],
    "GROWTH":              ["New-age tech", "D2C brands", "SaaS"],
    "DIVIDEND_YIELD":      ["Utilities", "Mature PSUs", "Cash-generative defensives"],
    "HOLDING_COMPANY":     ["Pure holding companies with listed investments"],
}
```

### Valuation Methods by Stock Type

#### Quality Compounders (Pharma, FMCG, IT, Consumer Brands)

```python
methods = [
    "dcf_gurufocus",   # PRIMARY — Two-stage EPS DCF, 10yr growth + 10yr terminal
    "dcf_fcf",         # CROSS-CHECK — same structure using Free Cash Flow
    "epv",             # FLOOR — what are current earnings worth with zero growth?
    "owner_earnings",  # BUFFETT CHECK — PAT + D&A - maintenance capex, discounted
    "pe_based",        # CONTEXT — vs sector median, own 5yr/10yr avg, Graham PE 15x
    "reverse_dcf",     # SANITY CHECK — what growth does today's price imply?
]
# Choose 4-5 of these per stock. Always include reverse_dcf as a cross-check.
# Drop epv/owner_earnings for early-stage or pre-profitability compounders.
```

**DCF Parameters for Compounders:**
```python
COMPOUNDER_DCF = {
    "stage1_years":         10,
    "stage1_growth":        "5yr_avg_EPS_CAGR * 0.8",  # apply conservatism
    "stage2_years":         10,
    "stage2_growth":        0.06,      # terminal: 6% nominal
    "discount_rate":        0.13,      # G-Sec 7% + ERP 6%
    "margin_of_safety":     0.25,      # 25% discount to DCF intrinsic value
}
```

#### Cyclical Stocks (Metals, Cement, Commodity Chemicals)

```
Do NOT use dcf_gurufocus or pe_based as primary for cyclicals at the top of the cycle.
Earnings are inflated at the peak — standard DCF will massively overvalue.

Methods:
  ev_ebitda at normalised midcycle EBITDA          PRIMARY (from registry)
  graham_number — book-value anchor at trough       SUPPORT
  Replacement cost analysis                         ANCHOR (not a registry tool — manual calc)
  EV per tonne or EV per capacity unit              SANITY CHECK (sector-specific multiple)
  reverse_dcf                                       CROSS-CHECK (what is market implying?)

Midcycle EBITDA = average EBITDA over the last full commodity cycle (10yr Screener.in data)
Apply sector median EV/EBITDA to midcycle EBITDA = Enterprise Value → Equity Value

Margin of Safety: 30-40% for cyclicals (higher uncertainty, higher required discount)
```

#### Financial Stocks (Banks, NBFCs, Insurance)

```
Banks and NBFCs cannot be valued on pe_based or ev_ebitda.
Debt is their raw material, not a liability to be stripped out.

Methods (from registry where applicable):
  Justified P/B from RoE and growth                PRIMARY (manual — not in generic registry)
    Formula: P/B = (RoE - g) / (CoE - g)
    If RoE > CoE then P/B > 1 is justified — high-quality banks earn this premium
  ddm (Gordon Growth Model on dividends)            FOR MATURE STABLE BANKS
  Excess Return Model: spread of RoE over CoE       QUALITY PREMIUM INDICATOR (manual)
  pe_based                                          DIRECTIONAL CROSS-CHECK only
  reverse_dcf                                       SANITY CHECK — market pricing implied growth

Key inputs for banks:
  NIM trend (Net Interest Margin)
  GNPA and NNPA (asset quality — bad loans)
  PCR (Provision Coverage Ratio)
  Credit cost cycle position
  Capital adequacy CET1

Margin of Safety: 20-30% for high-quality private banks, 35-50% for PSU banks
```

#### Infrastructure and Capital Goods

```
Long gestation periods, lumpy revenue, order-book driven earnings.

Methods:
  ev_ebitda on order book × margin = forward EBITDA  PRIMARY (from registry)
  EV divided by Order book multiple (sector standard) SECTOR SANITY CHECK
  dcf_gurufocus with 15-20yr horizon, WACC 14-15%    LONG-HORIZON DCF
  owner_earnings for asset-heavy infra businesses    MAINTENANCE CAPEX CHECK
  Sum-of-parts (SOTP) if multiple divisions          MANUAL — not a registry tool

Key inputs:
  Order inflow trend — the leading indicator of future revenue
  Order book as multiple of revenue — execution pipeline length
  Working capital cycle — infra companies often have high WC requirements
  Government spending plans in the relevant segment
```

#### Dividend Yield Stocks (Mature PSUs, Utilities, Cash-Generative Defensives)

```
Methods (from registry):
  ddm (Gordon Growth Model)                          PRIMARY
    Price = D1 / (CoE - g)  where g = sustainable dividend growth
  pe_based (low growth means PE is more stable)      CONTEXT
  Yield vs G-Sec spread normalised to 10yr G-Sec     RELATIVE VALUE CHECK
  owner_earnings DCF (Buffett — mature stable capex) INTRINSIC VALUE FLOOR
  peg_ratio for dividend growers with moderate PE    GROWTH QUALITY CHECK

Key inputs:
  Dividend history and payout ratio sustainability
  CFO/PAT ratio — can the dividend be funded purely from operations?
  Debt level — dividends must never be debt-funded
```

#### Growth Stocks (New-Age Tech, High-Growth Small Caps)

```
Traditional pe_based meaningless when P/E exceeds 100 or the company is loss-making.

Methods:
  reverse_dcf — what growth rate does current price assume? Is it achievable?  PRIMARY LENS
  Revenue multiple (P/Sales) vs growth rate vs global peers                    RELATIVE
  Path to profitability analysis — when does unit economics reach breakeven?   QUALITATIVE
  TAM analysis — total addressable market, penetration, market share trajectory QUALITATIVE
  epv as a floor — what is the business worth if growth stops entirely?        DOWNSIDE FLOOR

Margin of Safety: 40-50% — high uncertainty and high execution risk
```

### Valuation Output Format (All Types)

```markdown
## Valuation — Ajanta Pharma (classified as: Quality Compounder)

### Method 1: Two-Stage EPS DCF (PRIMARY)
Stage 1 growth (yr 1-10): 14% EPS CAGR (5yr avg 16.2% with conservatism applied)
Stage 2 growth (yr 11-20): 6% terminal nominal growth
Discount rate: 13% (G-Sec 7% + ERP 6%)
Intrinsic value: Rs 2,650 per share
Margin of safety at 25%: Rs 1,988 per share

### Method 2: FCF DCF (CROSS-CHECK)
FCF 5yr average growth: 11.4%
Intrinsic value: Rs 2,420 per share

### Method 3: Historical PE (CONTEXT)
10yr average PE: 28x | 5yr average PE: 24x
FY26E EPS estimated at Rs 95
At 24x PE: Rs 2,280 | At trough 18x: Rs 1,710 (bear) | At peak 35x: Rs 3,325 (bull)

### Method 4: Reverse DCF (CROSS-CHECK)
Current price Rs 2,100 implies: EPS CAGR of 10.8% for 10 years
Actual 5yr EPS CAGR: 16.2%. Actual 10yr EPS CAGR: 19.1%.
Price implies meaningful slowdown — opportunity if slowdown thesis is wrong.

### Valuation Summary
| Scenario | Intrinsic Value   | Implied Upside from Rs 2,100 |
|----------|-------------------|------------------------------|
| Bear     | Rs 1,700–1,900    | -10% to -19%                 |
| Base     | Rs 2,280–2,650    | +9% to +26%                  |
| Bull     | Rs 3,100–3,325    | +48% to +58%                 |

Margin of Safety Price: Rs 1,988 (25% below base DCF value)
Current Price: Rs 2,100
MOS Gap: -5.6% (just above MOS price — acceptable for staggered buying)
```

### India-Specific Valuation Parameters

```python
INDIA_PARAMS = {
    "risk_free_rate":           0.070,   # 10yr G-Sec (auto-fetched weekly via nsepython)
    "equity_risk_premium":      0.060,   # India ERP (Damodaran estimate)
    "default_wacc":             0.130,
    "terminal_growth_real":     0.040,   # India long-run real GDP growth
    "terminal_growth_nominal":  0.060,   # 4% real + 2% inflation
    "aaa_bond_yield":           0.075,   # For Graham Formula denominator

    "sector_wacc": {
        "Private Banking":       0.115,
        "FMCG":                  0.110,
        "IT Services":           0.120,
        "Pharma":                0.130,
        "Specialty Chemicals":   0.135,
        "Capital Goods":         0.135,
        "Infrastructure":        0.145,
        "Metals and Mining":     0.150,
        "Real Estate":           0.155,
    },

    "sector_margin_of_safety": {
        "FMCG":                  0.20,
        "IT Services":           0.20,
        "Private Banking":       0.25,
        "Pharma":                0.25,
        "Specialty Chemicals":   0.30,
        "Cyclicals":             0.35,
        "PSU Banks":             0.40,
        "Infrastructure":        0.30,
    }
}
```

---

## 🏆 Step 5 — Scoring and Ranking (Past + Future)

> Scoring combines what the business has already demonstrated (past financials) and what it is likely to do (forward estimates, business quality, macro tailwinds). A pure backward-looking score is incomplete — a company with a strong past but deteriorating moat can score high incorrectly.

### Score Components

| Component | Default Weight | Sub-factors | Direction |
|-----------|---------------|-------------|-----------|
| **Business Quality** | 25% | ROCE, ROE, OPM trend, asset turnover, FCF conversion | Mostly backward, moat durability is forward |
| **Growth (Past)** | 20% | Revenue CAGR 3yr/5yr/10yr, EPS CAGR, Profit consistency % | Backward |
| **Growth (Forward)** | 20% | Estimated EPS CAGR next 3yr, order book visibility, macro tailwind score | Forward |
| **Valuation** | 15% | PE vs 5yr average, PE vs sector, MOS gap, reverse DCF implied growth | Both |
| **Financial Health** | 10% | D/E, current ratio, interest coverage, CFO/PAT, promoter pledge | Backward |
| **Business Outlook** | 10% | Moat trajectory, management quality, competitive position trend | Forward |

### Forward-Looking Sub-Scores

```
Forward Growth Score (0–100):
  LLM-estimated EPS CAGR next 3yr from business and macro analysis      40%
  Order book or revenue visibility in months of forward revenue          20%
  Macro tailwind score from macro agent (net positive/neutral/negative)  20%
  Management guidance credibility (track record of achieving guidance)   20%

Business Outlook Score (0–100):
  Moat trajectory: Strengthening 100 / Stable 70 / Eroding 30 / None 0
  Competitive position: Gaining share 100 / Stable 60 / Losing share 20
  Management quality score 0–100 from management assessment
  Sector tailwind from macro analysis 0–100
```

### Verdicts

| Score | Verdict | Signal |
|-------|---------|--------|
| 75 or above | STRONG BUY | 🟢 |
| 60 to 74 | BUY | 🔵 |
| 50 to 59 | WATCHLIST | 🟡 |
| 40 to 49 | NEUTRAL | ⚪ |
| Below 40 | AVOID | 🔴 |

### Personalised Scoring (Learning Over Time)

```
You: "I care more about business quality and future outlook than past growth"

Learning Agent updates your scoring profile:
  business_quality:  30%  (was 25%, +5)
  growth_past:       15%  (was 20%, -5)
  growth_forward:    25%  (was 20%, +5)
  valuation:         15%  (unchanged)
  financial_health:  10%  (unchanged)
  business_outlook:  15%  (was 10%, +5)

Saved to memory.md — all future scores use your weights automatically.
```

---

## ⏰ Automation Layer — Cron, Alerts, Digests

### Cron Jobs

```json5
{
  cron: [
    {
      id: "morning-market-brief",
      schedule: "0 8 * * 1-5",          // Every market day 8am IST
      agent: "personal",
      message: "Fetch NSE market status. Give me: top gainers/losers in my watchlist, any BSE announcements from last 12 hours for watchlist stocks, macro events today.",
      channel: "whatsapp",
    },
    {
      id: "watchlist-fundamentals-refresh",
      schedule: "0 9 * * 6",            // Saturday 9am
      agent: "data-fetcher",
      message: "Refresh Screener.in data for all stocks in my watchlist and portfolio. Update cache.",
    },
    {
      id: "quarterly-results-check",
      schedule: "0 */3 * * 1-5",        // Every 3 hours on market days
      agent: "data-fetcher",
      message: "Check BSE announcements for quarterly results. If any watchlist stock has new results, fetch data, run analysis, send alert on Telegram.",
    },
    {
      id: "weekly-digest",
      schedule: "0 9 * * 0",            // Sunday 9am
      agent: "personal",
      message: "Generate weekly digest: portfolio performance vs Nifty, watchlist updates, 3 screening ideas matching my investment style, macro events next week.",
      channel: "telegram",
    },
    {
      id: "monthly-portfolio-review",
      schedule: "0 10 1 * *",           // 1st of every month 10am
      agent: "personal",
      message: "Monthly portfolio review. For each holding: update business outlook, check if thesis is intact, flag any concerns. Compute XIRR vs Nifty 50.",
      channel: "telegram",
    },
    {
      id: "rbi-macro-update",
      schedule: "0 12 * * 3",           // Every Wednesday noon
      agent: "macro-agent",
      message: "Check for RBI policy updates, G-Sec yield changes, CPI data releases this week. Update WACC parameters if G-Sec moved more than 25bps. Alert on Telegram if significant.",
    },
  ]
}
```

### Price and Fundamental Alerts

```
You: "Alert me when HDFC Bank falls below Rs 1,500"

Agent: Sets alert using nsepython live price feed.
       Checks every 60 seconds during market hours (9:15am to 3:30pm IST).
       When triggered:
       WhatsApp: HDFC Bank Rs 1,498 (-2.3%)
                 You were watching at Rs 1,500.
                 Current PE: 16.2 (5yr avg: 19.1). NIM last Q: 4.1%.
                 Want a quick fundamental check?

You: "Alert me if any watchlist stock's quarterly PAT falls more than 15% year on year"

Agent: Monitors BSE announcements for results.
       Parses PAT and compares to same quarter previous year.
       Sends Telegram alert with business context and thesis check when triggered.
```

---

## 🔌 LLM Provider Abstraction

### Provider Configuration

```json5
{
  llm: {
    default_provider: "anthropic",
    providers: {
      anthropic: {
        api_key_secret: "ANTHROPIC_API_KEY",
        models: { fast: "claude-haiku-4-5", default: "claude-sonnet-4-6", deep: "claude-opus-4-6" }
      },
      openai: {
        api_key_secret: "OPENAI_API_KEY",
        models: { fast: "gpt-4o-mini", default: "gpt-4o" }
      },
      google: {
        api_key_secret: "GOOGLE_API_KEY",
        models: { fast: "gemini-2.0-flash", default: "gemini-1.5-pro" }
      },
      ollama: {
        base_url: "http://localhost:11434",
        default_model: "llama3.1:8b",
        // Fully local — no API key, no data leaves your machine
      },
    },

    // Route by task type — use the expensive model only where it matters
    routing: {
      business_understanding: { provider: "anthropic", tier: "deep"    },
      macro_analysis:         { provider: "anthropic", tier: "default" },
      data_fetch:             { provider: "openai",    tier: "fast"    },
      valuation:              { provider: "anthropic", tier: "deep"    },
      scoring:                { provider: "anthropic", tier: "default" },
      report_generation:      { provider: "anthropic", tier: "deep"    },
      alerts:                 { provider: "google",    tier: "fast"    },
      local_tasks:            { provider: "ollama",    tier: "default" },
    }
  }
}
```

### Unified Provider Interface

```python
# backend/llm/provider.py

class LLMProvider:
    """
    Unified interface — agents never import anthropic or openai directly.
    They call provider.complete() and the routing config decides the rest.
    """

    async def complete(
        self,
        messages: list[dict],
        task_type: str = "default",
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        provider_name, model = self._resolve(task_type)
        return await self._adapters[provider_name].complete(messages, model, tools, stream)

    def _resolve(self, task_type: str) -> tuple[str, str]:
        routing = self.config.llm.routing.get(task_type, {})
        provider = routing.get("provider", self.config.llm.default_provider)
        tier = routing.get("tier", "default")
        model = self.config.llm.providers[provider].models[tier]
        return provider, model
```

### Switching Provider

```bash
# Go fully offline for a session
screenerclaw chat --provider ollama

# Permanent change via config
screenerclaw config set llm.routing.report_generation.provider openai

# Or tell the agent directly:
# "Use Gemini for all future reports to save costs"
# Agent updates config automatically
```

---

## 🔐 Security Model

```mermaid
flowchart TD
    INBOUND["📨 Inbound message"] --> ALLOWLIST["allowFrom / dmPolicy check"]
    ALLOWLIST -->|known sender| PERSONAL["Full access — personal session"]
    ALLOWLIST -->|unknown sender| PAIRING["Pairing code issued\nMessage blocked until approved"]
    PAIRING -->|code approved| PERSONAL
    PAIRING -->|not approved| BLOCKED["❌ Blocked"]
    PERSONAL -->|main session| TOOL_ACL["Tool ACL check\n(allow/deny per agent)"]
    PERSONAL -->|group session| READONLY["Read-only access\nNo portfolio write\nNo config write"]
    TOOL_ACL --> DATA["All data local\n~/.screenerclaw/"]
```

### Default Security Posture

```
Personal DM (WhatsApp, Telegram, CLI):
  Full access: screen, analyse, report, alert, portfolio, watchlist, config
  All tools enabled
  LLM receives full context

Group sessions:
  Read-only: screen and report only
  Cannot access portfolio data — private by design
  Cannot modify watchlists, alerts, or config
  Rate-limited: 5 queries per hour per group

Local CLI:
  Always trusted — no auth required
  All tools enabled

Financial Data Privacy:
  Portfolio data:    Local only. Never in LLM context unless you explicitly ask.
  Watchlist data:    Local only. In LLM context only for analysis queries.
  API keys/secrets:  AES-256 encrypted. Never in logs or transcripts.
  Session history:   Local markdown files. You own them. Delete anytime.
  Ollama option:     100% local operation — no data leaves your machine at all.
```

---

## ⚙️ Configuration Reference

```json5
// ~/.screenerclaw/config.json5  (JSON5 format — comments allowed)

{
  // Identity
  meta: {
    name: "ScreenerClaw",
    timezone: "Asia/Kolkata",
    market_open:  "09:15",
    market_close: "15:30",
  },

  // LLM providers and routing
  llm: { /* see LLM section */ },

  // Agent roster with roles, models, skills
  agents: {
    defaults: {
      memory: "~/.screenerclaw/memory.md",
      skills_dir: "~/.screenerclaw/skills/",
      sandbox: { mode: "non-main" },
    },
    list: [ /* see agent roster */ ],
  },

  // Channels
  channels: { /* see channel config */ },

  // Binding rules
  bindings: [
    { agentId: "personal",      match: { channel: "whatsapp" } },
    { agentId: "personal",      match: { channel: "telegram" } },
    { agentId: "alert-watcher", match: { intent: "alert" } },
  ],

  // Cron jobs
  cron: [ /* see automation section */ ],

  // Data sources
  data: {
    sources: {
      screener_in: {
        enabled: true,
        username_secret: "SCREENER_USERNAME",
        password_secret: "SCREENER_PASSWORD",
        rate_limit_rps: 0.5,
        session_refresh_hours: 12,
      },
      nsepython: { enabled: true, rate_limit_rps: 5 },
      yahoo_finance: { enabled: true, rate_limit_rps: 2 },
      bse: { enabled: true, rate_limit_rps: 2 },
    },
    cache_dir: "~/.screenerclaw/cache/",
  },

  // Valuation parameters (auto-updated weekly from NSE G-Sec data)
  valuation: {
    risk_free_rate:           0.070,
    equity_risk_premium:      0.060,
    default_wacc:             0.130,
    terminal_growth_nominal:  0.060,
    auto_refresh_gsec:        true,
  },

  // Scoring weights (personalised over time by learning agent)
  scoring: {
    weights: {
      business_quality: 0.25,
      growth_past:      0.20,
      growth_forward:   0.20,
      valuation:        0.15,
      financial_health: 0.10,
      business_outlook: 0.10,
    }
  },

  // Gateway
  gateway: {
    port: 18900,
    bind: "loopback",
    auth: { mode: "pairing" },
    tailscale: { mode: "serve" },    // off | serve | funnel
  },
}
```

---

## 🚀 Installation and Setup

### Prerequisites

```bash
python --version   # Python 3.11 or higher
node --version     # Node 18 or higher (WebUI only — optional)
```

### Install

```bash
# Clone
git clone https://github.com/yourorg/screenerclaw
cd screenerclaw

# Python environment
python -m venv venv
source venv/bin/activate          # Mac/Linux
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
# Key packages: fastapi uvicorn anthropic openai nsepython yfinance
#               beautifulsoup4 httpx pydantic aiofiles cryptography

# Guided setup (recommended)
python -m screenerclaw onboard

# The wizard will:
# 1. Ask for your preferred LLM provider and API key
# 2. Set up Screener.in login (username + password stored encrypted)
# 3. Configure your first channel (Telegram recommended for beginners)
# 4. Run a test screen to verify data fetching works
# 5. Start the gateway daemon (systemd on Linux, launchd on macOS)
```

### Manual Start

```bash
# Gateway (foreground, verbose logs)
python -m screenerclaw gateway --port 18900 --verbose

# Health check
python -m screenerclaw doctor

# Test a screen
python -m screenerclaw screen "undervalued pharma midcap"
```

### Directory Created on Install

```
~/.screenerclaw/
├── config.json5                    # Main config (JSON5 — comments OK)
├── secrets/                        # AES-256 encrypted credentials
│   ├── SCREENER_USERNAME.enc
│   ├── SCREENER_PASSWORD.enc
│   └── ANTHROPIC_API_KEY.enc
├── memory.md                       # Your long-term user memory (agent writes here)
├── sessions/                       # Conversation transcripts (plain markdown)
│   └── personal-main.md
├── skills/                         # Domain knowledge skill files
│   ├── screener-in.md
│   ├── nsepython.md
│   ├── business-analysis.md
│   ├── moat-framework.md
│   ├── india-macro.md
│   ├── geopolitical-risks.md
│   ├── valuation-india.md
│   ├── cyclical-valuation.md
│   ├── sector-india.md
│   ├── margin-of-safety.md
│   ├── scoring-framework.md
│   ├── management-quality.md
│   ├── quarterly-results.md
│   └── custom-ratios.md            # User's own custom terms (agent writes here)
├── workspace/                      # Agent working directory
├── watchlists/
│   ├── portfolio.md                # Holdings: symbol, quantity, average cost
│   ├── main.md                     # Primary watchlist
│   └── tracking.md                 # Loosely monitoring
└── cache/                          # TTL file cache (auto-expired JSON files)
    ├── screener_filter_*.json
    ├── nse_price_*.json
    └── fundamentals_*.json
```

---

## 🗂 Project File Structure (Python)

```
screenerclaw/
├── screenerclaw/
│   ├── __main__.py                  # Entry point: CLI dispatcher
│   ├── gateway/
│   │   ├── server.py                # FastAPI + WebSocket gateway server
│   │   ├── router.py                # Binding resolution + intent classification
│   │   ├── auth.py                  # Pairing, token auth, allowlist enforcement
│   │   └── session_queue.py         # Per-session serialized execution queue
│   ├── agents/
│   │   ├── base.py                  # Base agent: LLM call, tool dispatch, memory, streaming
│   │   ├── orchestrator.py          # Routes messages, delegates to specialists, synthesises
│   │   ├── business_analyst.py      # Step 1: Business model, moat, costs, management
│   │   ├── macro_agent.py           # Step 2: India macro + geopolitical impact on earnings
│   │   ├── data_fetcher.py          # Screener.in + nsepython + yfinance + BSE fetching
│   │   ├── valuation_agent.py       # Step 4: Stock type classifier + adaptive valuation
│   │   ├── ranking_agent.py         # Step 5: Past + forward composite scoring + ranking
│   │   ├── report_agent.py          # Business report + outlook + full investment report
│   │   ├── alert_watcher.py         # Price alerts + fundamental change monitoring
│   │   └── learning_agent.py        # memory.md + skills + config updates
│   ├── channels/
│   │   ├── whatsapp.py              # WhatsApp bridge (Baileys subprocess or python-whatsapp)
│   │   ├── telegram.py              # python-telegram-bot
│   │   ├── slack.py                 # slack_bolt
│   │   ├── discord.py               # discord.py
│   │   └── cli.py                   # Rich terminal interface
│   ├── llm/
│   │   ├── provider.py              # Unified interface — agents never import SDK directly
│   │   ├── anthropic_adapter.py     # Claude (streaming + tool use)
│   │   ├── openai_adapter.py        # GPT (streaming + tool use)
│   │   ├── google_adapter.py        # Gemini (streaming + tool use)
│   │   └── ollama_adapter.py        # Ollama local (streaming)
│   ├── data/
│   │   ├── screener/
│   │   │   ├── client.py            # Login, session management, filter endpoint
│   │   │   ├── parser.py            # HTML parsing: P&L, BS, CF, ratios, peers
│   │   │   └── filter_builder.py    # NL → Screener.in query string via LLM
│   │   ├── nse/
│   │   │   ├── client.py            # nsepython wrapper: live, historical, corporate actions
│   │   │   └── universe.py          # Index constituents, market cap segment classification
│   │   ├── bse/
│   │   │   ├── announcements.py     # BSE announcement feed + quarterly results
│   │   │   └── xbrl_parser.py       # XBRL financial data extraction
│   │   ├── yahoo/
│   │   │   └── client.py            # yfinance wrapper: statements, TTM, price history
│   │   ├── normalizer.py            # Standardise multi-source data into common schema
│   │   └── cache.py                 # File-based TTL cache (no database needed)
│   ├── valuation/
│   │   ├── classifier.py            # Classify stock type → select appropriate methods
│   │   ├── dcf.py                   # Two-stage EPS DCF, FCF DCF, reverse DCF
│   │   ├── graham.py                # Graham Number, Graham Formula, EPV
│   │   ├── cyclical.py              # Midcycle EV/EBITDA, P/B trough, replacement cost
│   │   ├── financials.py            # Banks: justified P/B, Gordon DDM, excess return model
│   │   ├── infra.py                 # Order book EV, sum-of-parts, long-horizon DCF
│   │   ├── dividend.py              # DDM, yield vs G-Sec, owner earnings DCF
│   │   └── scenarios.py             # Bear / base / bull scenario builder for any method
│   ├── scoring/
│   │   ├── engine.py                # Composite scorer combining past and forward
│   │   ├── backward.py              # Historical financial ratios scorer
│   │   ├── forward.py               # Forward estimates + macro + moat trajectory scorer
│   │   └── personaliser.py          # Apply user custom weight profile from memory.md
│   ├── memory/
│   │   ├── session.py               # Session transcript read/write + auto-compaction
│   │   ├── workspace.py             # memory.md read/write
│   │   └── skills.py                # Skill file loading + injection into system prompt
│   ├── tools/
│   │   ├── registry.py              # All agent-callable tools with schemas
│   │   ├── screen.py                # Run Screener.in filter, return candidates
│   │   ├── fetch_company.py         # Full company data fetch from all sources
│   │   ├── run_valuation.py         # Run adaptive valuation suite for a stock
│   │   ├── score_stock.py           # Run composite scoring
│   │   ├── alert_manage.py          # Set, list, delete price and fundamental alerts
│   │   ├── portfolio_rw.py          # Portfolio markdown read/write
│   │   └── watchlist_rw.py          # Watchlist markdown read/write
│   ├── config.py                    # Config loading, validation, hot-reload
│   └── secrets.py                   # AES-256 secret management
├── frontend/                        # Next.js 14 + TypeScript + Tailwind (optional)
├── requirements.txt
├── setup.py
└── tests/
    ├── test_screener.py
    ├── test_valuation.py
    └── test_agents.py
```

---

## 💬 Example Interactions

### Natural Language Screening

```
You: "Find me undervalued pharma midcaps with consistent profits"

ScreenerClaw:
  [Data Agent] Logging into Screener.in...
  [Data Agent] Filtering: sector=Pharma, mcap 5000-30000Cr, ROCE>15%, 5yr profit CAGR>10%...
  [Data Agent] 23 candidates found.
  [Business Analyst] Quick moat and quality check on top 15 by score...
  [Ranking Agent] Composite scoring on quality + growth + valuation + forward outlook...

  Top 5 Results:
  🟢 Ajanta Pharma         Score 81 | ROCE 28% | 5yr PAT CAGR 16% | PE 22 (hist avg 28) | MOS: Rs 1,988
  🔵 Alkem Laboratories    Score 74 | ROCE 24% | 5yr PAT CAGR 14% | PE 18 (hist avg 22)
  🔵 Sanofi India          Score 71 | ROCE 41% | 5yr PAT CAGR 11% | PE 24 (hist avg 27)
  🟡 Ipca Laboratories     Score 65 | ROCE 19% | 5yr PAT CAGR 12% | PE 20 (hist avg 26)
  🟡 JB Chemicals          Score 63 | ROCE 22% | 5yr PAT CAGR 13% | PE 21 (hist avg 24)

  Reply "deep [number]" for full business + valuation + outlook report.
```

### Deep Investment Report

```
You: "deep 1"

[Building full report for Ajanta Pharma — business analyst, macro, valuation, report agents — ~60 seconds]

AJANTA PHARMA — FULL INVESTMENT REPORT

BUSINESS UNDERSTANDING
[Business model, moat: MODERATE-STRONG, revenue breakdown, cost structure, management quality — 600 words]

MACRO AND GEOPOLITICAL IMPACT
[INR tailwind +Rs 30-35Cr per 1% depreciation, China+1 API opportunity, Africa demand secular, FDA binary risk — 300 words]

VALUATION (Quality Compounder methods)
DCF intrinsic: Rs 2,650 | FCF cross-check: Rs 2,420 | MOS price: Rs 1,988 | Current: Rs 2,100
Base case upside: +9% to +26% | Bull case: +48% to +58%

BRUTALLY HONEST OUTLOOK
Short term (0-12 months): Q2 results + FDA inspection = binary events. Cautious entry.
Medium term (1-3 years): US ANDA pipeline + Africa volume growth = earnings inflection likely.
Long term (3-10 years): Strong compounder if moat holds. India pharma + Africa secular demand.

VERDICT: 🔵 BUY at Rs 1,988 MOS price. Current Rs 2,100 is marginally above — acceptable for staggered accumulation.
```

### Teaching the Agent Your Terms

```
You: "When I say 'debt-free compounder' I mean: D/E < 0.1, ROCE > 20%,
     10yr profit CAGR > 15%, promoter holding > 50%"

ScreenerClaw: Saved to skills/custom-ratios.md permanently.
              I will apply your exact definition every time you use that term.

You: "Find me debt-free compounders in the chemical space"

ScreenerClaw: [applies your exact definition — no re-explanation needed]
```

### Automated Weekly Digest (Telegram, Sunday 9am)

```
ScreenerClaw: 📊 Weekly Digest — July 14, 2025

YOUR PORTFOLIO
Up 1.4% this week. XIRR since inception: 19.4% (Nifty 50: 14.2%)
Best: Pidilite +4.2% (volume data strong), Ajanta Pharma +3.1%
Worst: Bharti Airtel -1.8% (weak Q1 ARPU guidance — checking thesis)

WATCHLIST ALERTS
HDFC Bank: PE 16.1 — approaching your entry target of PE 16. Getting close.
Asian Paints: Q1 volume +8% YoY — recovery confirmed, thesis intact.

MACRO THIS WEEK
G-Sec yield: 6.98% (slight dip — WACC auto-updated to 12.98%)
RBI minutes: neutral tone, rate cut most likely Q4 2025
INR: 83.6 vs USD — pharma and IT exporters benefiting

3 SCREENING IDEAS MATCHING YOUR STYLE
Narayana Hrudayalaya (Score 76): hospital chain expansion, moat strengthening
PI Industries (Score 74): CSM export pipeline strong, India agri tailwind
Divi's Laboratories (Score 72): API + nutraceutical, post-correction opportunity

Reply "deep [company name]" for full report on any of these.
```

---

## 📝 Summary — The 5-Step Pipeline

ScreenerClaw reimagines Indian stock research as a **sequential 5-step autonomous pipeline** that must be followed in order:

```
Step 1: Business Understanding
        What is this company? What protects it? How does it make money?
        What does it cost to run? Who manages it and how?

Step 2: Macro and Geopolitical Impact
        How does today's India macro (RBI, INR, monsoon, PLI) affect this specific business?
        How do geopolitical events (China+1, US tariffs, wars) impact earnings?

Step 3: Business Report and Brutally Honest Outlook
        Synthesised intelligence report.
        Short, medium, and long-term earnings outlook — no sugar-coating.

Step 4: Adaptive Valuation
        Choose 4-5 methods appropriate for this stock type.
        Generate bear, base, bull scenarios with margin of safety prices.

Step 5: Composite Scoring and Ranking
        Combine backward-looking financials and forward-looking estimates.
        Personalised to your investment style weights.
        Final verdict: Strong Buy / Buy / Watchlist / Neutral / Avoid
```

The key difference from any existing Indian stock screener:

| Traditional Screener | ScreenerClaw |
|---------------------|--------------|
| Starts with ratios | Starts with business understanding |
| Same valuation model for every stock | Adaptive valuation by stock type |
| Backward-looking scores only | Past financials plus forward outlook combined |
| Manual analysis after filtering | Automated 5-step multi-agent intelligence pipeline |
| One interface — web browser login | WhatsApp, Telegram, Slack, CLI, Web |
| No memory of you | Learns your style, remembers your terms permanently |
| You interpret the data | Agent synthesises, reports, and recommends |
| Static tool | Autonomous: alerts, digests, portfolio tracking, cron jobs |

---

*Inspired by OpenClaw's agent architecture. Built for the serious Indian equity investor.*

*Data sources: Screener.in (with login) · nsepython · Yahoo Finance · BSE*

*Models: Claude Opus (business analysis, valuation, reports) · Claude Sonnet (orchestration, macro, scoring) · Gemini Flash (alerts) · GPT-4o-mini (data fetch)*