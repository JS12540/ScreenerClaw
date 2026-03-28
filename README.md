# ScreenerClaw 🦞
### AI-Native Indian Stock Discovery, Screening & Analysis Platform

ScreenerClaw is a production-ready AI-powered stock screener inspired by Screener.in, but with full natural-language querying, automated multi-source data aggregation, comprehensive valuation models, and Claude AI-generated investment reports.

---

## Features

- **Full Indian Stock Universe** — NSE + BSE, 5000+ stocks across all sectors and market cap buckets
- **Natural Language Screening** — Ask in plain English, get structured results
- **Multi-Source Data** — Screener.in + Yahoo Finance + NSE + BSE
- **10+ Valuation Methods** — DCF, Graham Number, Graham Formula, P/E based, PEG, EBO Model, Owner Earnings, DDM, EPV
- **Bull/Normal/Bear Scenarios** — 3yr, 5yr, 10yr price projections
- **AI Investment Reports** — Claude-powered deep analysis for each stock
- **Comprehensive Scoring** — Quality + Growth + Valuation + Health + Consistency (0–100)

---

## Quick Start

### 1. Clone & Setup

```bash
cd screener_agent
python setup.py
```

### 2. Configure API Key

Edit `.env`:
```
ANTHROPIC_API_KEY=your_key_here
```

### 3. Run Backend

```bash
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

uvicorn backend.main:app --reload --port 8000
```

### 4. Run Frontend

```bash
cd frontend
npm install
npm run dev
```

### 5. Open App

Visit: **http://localhost:3000**

---

## Architecture

```
screener_agent/
├── backend/
│   ├── main.py                    # FastAPI app, all endpoints
│   ├── pipeline.py                # Main data orchestrator
│   ├── database.py                # SQLAlchemy async setup
│   ├── models.py                  # ORM models
│   ├── config.py                  # Settings, constants
│   ├── agents/
│   │   ├── universe_agent.py      # Build/maintain full stock universe
│   │   ├── prompt_agent.py        # NL → structured filters (Claude AI)
│   │   ├── discovery_agent.py     # Filter candidates from universe
│   │   ├── api_agent.py           # yfinance + NSE + BSE data
│   │   ├── analysis_agent.py      # Compute 50+ financial metrics
│   │   ├── ranking_agent.py       # Score stocks 0-100
│   │   ├── report_agent.py        # AI investment reports (Claude)
│   │   ├── normalization_agent.py # Standardize multi-source data
│   │   └── cache_agent.py         # TTL caching
│   ├── scrapers/
│   │   ├── screener_scraper.py    # Screener.in HTML scraper
│   │   ├── nse_scraper.py         # NSE public API
│   │   └── bse_scraper.py         # BSE data
│   └── valuation/
│       ├── dcf.py                 # GuruFocus DCF, reverse DCF, scenarios
│       ├── graham.py              # Graham Number, Graham Formula, EPV, DDM
│       └── earnings_based.py      # PEG, EBO, EBITDA multiple, residual income
├── frontend/                      # Next.js 14 + TypeScript + Tailwind
├── requirements.txt
├── setup.py
└── test_screener.py               # End-to-end test
```

---

## Example Queries

```
Find undervalued IT companies in India
High ROCE midcap stocks with low debt
Top pharma companies with consistent profit growth
Find smallcap companies with sales CAGR above 15%
Best fundamentally strong railway stocks in India
Find all Indian stocks where PE is below sector average but ROE is above 18%
Suggest top 10 long-term compounders
Show me high cash flow defensive stocks
```

---

## Valuation Methods

| Method | Description |
|--------|-------------|
| **GuruFocus DCF** | Two-stage EPS-based DCF (10yr growth + 10yr terminal) |
| **FCF DCF** | Same model using Free Cash Flow per share |
| **Graham Number** | √(22.5 × EPS × Book Value) |
| **Graham Formula** | V = EPS × (8.5 + 2g) × 4.4 / AAA_yield |
| **P/E Based** | Sector PE, Historical PE, PEG, Graham PE (15x) |
| **EPV** | Earnings Power Value (Greenwald) |
| **Owner Earnings** | Buffett's Owner Earnings DCF |
| **DDM** | Gordon Growth Model (for dividend stocks) |
| **PEG Ratio** | Peter Lynch's PEG < 1 test |
| **EBO/Residual Income** | Edwards-Bell-Ohlson model |
| **EV/EBITDA** | Enterprise value to EBITDA multiple |
| **P/B Justified** | Justified P/B = ROE / Cost of Equity |

---

## Scoring System

| Component | Weight (Balanced) | What it measures |
|-----------|-------------------|-----------------|
| Quality | 30% | ROCE, ROE, OPM |
| Growth | 25% | Revenue CAGR, Profit CAGR, EPS CAGR |
| Valuation | 20% | PE, PB (inverted — cheaper = higher) |
| Financial Health | 15% | D/E, Current ratio, Interest coverage, CFO/PAT |
| Consistency | 10% | Profit consistency %, Margin stability |

**Verdicts:** STRONG BUY (≥70) | BUY (≥60) | WATCHLIST (≥50) | NEUTRAL (≥40) | AVOID (<40)

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/screen` | Screen stocks with natural language query |
| GET | `/api/stock/{symbol}` | Full detail for one stock |
| GET | `/api/universe/stats` | Universe coverage statistics |
| POST | `/api/universe/refresh` | Trigger universe refresh |
| GET | `/api/search/autocomplete` | Symbol/name autocomplete |
| GET | `/api/recent-screens` | Recent screening history |
| GET | `/api/sectors` | All sectors with stock count |
| GET | `/api/health` | Health check |

---

## Risk Discount Rates (India)

- Risk-free rate: **7%** (10-year G-Sec approximation)
- Equity risk premium: **6%**
- Default discount rate: **13%**
- Terminal growth rate: **4%**

---

## Data Sources

- **Screener.in** — Primary fundamental data, 10-year history, peers, shareholding
- **Yahoo Finance** — Price data, financial statements, market metrics
- **NSE** — Live prices, sector metadata, index constituents
- **BSE** — Company metadata, BSE codes

---

## Disclaimer

ScreenerClaw is an educational and research tool. Nothing on this platform constitutes investment advice. Always do your own due diligence before investing.
