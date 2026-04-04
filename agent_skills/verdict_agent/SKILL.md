---
name: verdict-agent
version: 1.0.0
description: Final investment verdict synthesis agent — Step 4b of the ScreenerClaw pipeline
---

# System Prompt
You are a senior investment analyst synthesising a final investment verdict.
Respond ONLY with valid JSON. No markdown, no preamble.

# Prompt Template Variables
The main `VERDICT_PROMPT` template accepts these variables:

- `{company_name}` — Company name
- `{ticker}` — NSE/BSE ticker symbol
- `{current_price}` — Current market price (₹)
- `{valuation_table}` — Formatted text listing all valuation method results:
  - Format: `  <Method> [<assumption>]: ₹<value> — above/below market (<pct>%) | MoS=<pct>%`
  - Includes all 12 methods computed by ValuationEngine
- `{business_type}` — Stock type classification (e.g. "services", "commodity_processor")
- `{moat_verdict}` — Overall moat verdict string from BusinessAgent
- `{analyst_summary}` — First 300 chars of analyst_summary from BusinessAgent
- `{norm_eps}` — Normalized EPS (₹) from AssumptionsAgent
- `{norm_roce}` — Normalized ROCE (%) from AssumptionsAgent
- `{g_bear}` — Bear-case growth assumption (%)
- `{g_base}` — Base-case growth assumption (%)
- `{g_bull}` — Bull-case growth assumption (%)
- `{r}` — Required return rate (%) — typically 12%
- `{y}` — Risk-free rate (%) — G-Sec 10yr yield, typically 7%

# Memory Inputs
Before running this agent, load:

- `companies/<TICKER>.md` — Prior verdicts for this company (track record of accuracy)
- `sectors/<sector_slug>.md` — Sector valuation norms (typical P/E, EV/EBITDA ranges)

# Learning Outputs
After this agent completes, extract and write to memory:

- **Company file** (`companies/<TICKER>.md`):
  - `valuation_zone` — Deep Value / Fair Value / Growth Priced / Overvalued
  - `buy_ranges[0]` — The primary action tier with price range
  - `probability_score.total` — Composite conviction score

- **Calibration log** (in `agent_skills/MEMORY.md`):
  - When a verdict is later proven wrong, record the date, verdict, actual outcome, and lesson

# Notes
- This agent runs after ValuationEngine computes all 12 methods
- LLM: execution model (gpt-4.1-mini by default), max_tokens=2048, temperature=0.1, json_mode=True
- Valuation zones:
  - Deep Value: stock < EPV (Greenwald) — growth for free
  - Fair Value: stock near mid-range of all valuations
  - Growth Priced: stock > EPV but < bull case — growth priced in
  - Overvalued: stock > bull case valuation
- Buy ranges must have 5 tiers: Strong Buy / Buy / Accumulate / Hold-Watch / Avoid
- Probability score: 40-60 for average, 70+ only for exceptional — be honest
- Implied growth formula: G = (V / (EPS × Y/R) - 8.5) / 2 (Graham formula reverse)
- Fallback: if LLM fails, generates default buy ranges at -40%, -20%, -10%, ±10%, +10% of CMP
