---
name: valuation-engine
version: 1.0.0
description: 12-method adaptive valuation engine for Indian listed companies
---

# Overview
The ValuationEngine computes up to 12 valuation methods depending on stock type classification.
All methods produce a `value_per_share` in ₹ and a `margin_of_safety` percentage vs current market price.

# India Valuation Parameters
| Parameter | Value | Notes |
|-----------|-------|-------|
| WACC | 13% | India equity risk premium ~6% + risk-free 7% |
| Terminal growth rate | 6% | Nominal GDP growth anchor |
| EPV discount rate (R) | 12% | Greenwald framework, slightly below WACC |
| Risk-free rate (Y) | 7% | RBI G-Sec 10-year yield |
| Graham multiplier (Y) | 7% | Used in Graham Number formula |
| Default required return | 12% | For EPS-based methods |

# Margin of Safety by Stock Type
| Stock Type | MoS Required |
|-----------|-------------|
| Value / Asset-heavy | 35-40% |
| Quality compounder | 25-30% |
| Growth stock | 20-25% |
| Cyclical | 40-45% |
| Turnaround / Distressed | 50%+ |

# 12 Valuation Methods

## 1. Graham Number
**Formula:** `√(22.5 × EPS × BVPS)`
- Classic Benjamin Graham fair value anchor
- Works best for asset-heavy, stable earnings businesses
- Not suitable for high-growth or negative-book companies
- India adjustment: use normalized EPS (3-5yr average), not trailing

## 2. Greenwald EPV (Earnings Power Value)
**Formula:** `Latest EPS (TTM) × Shares / R`
- Bruce Greenwald's core valuation — assumes zero growth
- Uses latest reported EPS (TTM), not normalized EPS
- If EPV < market price: you are paying for growth
- If EPV > market price: growth is free — strong value signal
- Most useful for stable-margin businesses with predictable earnings
- India R: 12–13%

## 3. Greenwald Growth Value
**Formula:** `Capital × (ROC − G) / (R − G)`
- Extension of EPV when the company has a genuine competitive advantage
- Only apply when moat is confirmed (moat_score > 60)
- Growth (g) is the warranted growth rate, not management guidance
- Uses latest EPS (TTM) for the EPV base, same as Method 2

## 4. DCF — Base Case
**Formula:** Standard discounted free cash flow (10-year projection + terminal value)
- Uses base-case growth assumption from AssumptionsAgent
- Terminal growth: 6%
- Discount rate: WACC 13%
- FCF = Operating CF - Capex (3-year average capex ratio)

## 5. DCF — Bear Case
- Same as DCF Base but using bear-case growth assumption
- Stress test: if bear case > CMP, strong downside protection

## 6. DCF — Bull Case
- Same as DCF Base but using bull-case growth assumption
- If CMP > bull case, stock is pricing in unrealistic optimism

## 7. PE-Based Valuation
**Formula:** `Normalized EPS × Sector PE`
- Uses sector median PE from peer comparison data
- Appropriate for stable, predictable earnings businesses
- India FMCG/IT typically trade at 30-50x — flag if PE is high

## 8. EV/EBITDA
**Formula:** `EBITDA × Sector EV/EBITDA multiple - Net Debt`
- Better than PE for capital-intensive or leveraged businesses
- Sector multiples derived from peer data or India defaults
- India industrials/cement: 8-12x; FMCG: 20-35x; IT services: 15-25x

## 9. Price-to-Book (P/BV)
**Formula:** `BVPS × Sector P/BV multiple`
- Most relevant for banks, NBFCs, and asset-heavy companies
- Unreliable for asset-light or intangible-heavy businesses
- India banks: 1.5-3.5x; PSU banks: 0.5-1.5x

## 10. Dividend Discount Model (DDM)
**Formula:** `DPS / (r - g)` where DPS = current annual dividend
- Only computed if dividend yield > 1% and payout ratio > 20%
- India: most growth companies retain earnings — DDM often not applicable
- Use for mature PSUs, utilities, stable dividend payers

## 11. Asset Replacement Value
**Formula:** Estimated cost to replicate the business from scratch
- Greenwald framework — what would it cost a new entrant to build this?
- Considers: fixed assets, brand value, customer relationships, regulatory licenses
- If MCap < replacement cost: potential deep value signal

## 12. Reverse DCF (Implied Growth)
**Formula:** Solve for g given CMP: `g = r - FCF_yield × (1 + r) / (CMP + FCF)`
- Answers: "What growth rate is the market pricing in?"
- Compare implied growth to historical growth and analyst estimates
- If implied growth >> historical growth: optimism is priced in

# Greenwald Framework Summary
The Greenwald framework has three valuation layers:
1. **Asset Value (AV)** — replacement cost of assets
2. **Earnings Power Value (EPV)** — value assuming no growth, no decline
3. **Growth Value (GV)** — EPV adjusted for competitive advantage + growth

Decision rules:
- AV > EPV: business earns below its cost of capital — value trap risk
- EPV > AV: business has a genuine franchise / intangible advantage
- GV > EPV: only justified if confirmed moat exists
- CMP < AV: deep value — getting the business below replacement cost

# AssumptionsAgent Outputs
The AssumptionsAgent derives these inputs for the ValuationEngine:
- `normalized_eps` — 3-5 year average EPS, adjusted for one-offs
- `normalized_roce` — Cycle-normalized ROCE
- `normalized_ebit` — Adjusted EBIT (removes exceptional items)
- `growth_scenarios.bear.g` — Conservative growth (typically 5-8%)
- `growth_scenarios.base.g` — Base growth (typically 10-15%)
- `growth_scenarios.bull.g` — Optimistic growth (typically 18-25%)
- `required_return_r` — Required return, default 12%
- `risk_free_rate_y` — G-Sec yield, default 7%
- `business_type` — Classification used to select valuation methods
