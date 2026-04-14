"""
Assumptions Agent — Phase 3
Uses LLM to derive valuation assumptions from financial data.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from backend.llm_client import LLMClient
from backend.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a senior equity research analyst specialising in Indian listed companies.
You have deep knowledge of valuation frameworks: Graham, Greenwald EPV, DCF, PEG, and DDM.
Respond ONLY with valid JSON. No markdown, no preamble."""

ASSUMPTIONS_PROMPT = """## Company Financial Data
{financial_summary}

## Task: Derive Valuation Assumptions

Based on the financial data above, reason carefully and output the following JSON:

{{
  "business_type": "commodity_processor|brand_play|specialty_niche|franchise|hybrid|services|technology",
  "is_cyclical": true or false,
  "cyclicality_explanation": "string",

  "normalized_eps": {{
    "method": "how you derived it (avg/median/regression)",
    "value": number,
    "rationale": "string"
  }},

  "normalized_roce": {{
    "value": number,
    "rationale": "use 5-10yr median, adjust for one-offs"
  }},

  "growth_scenarios": {{
    "bear": {{ "g": number (as %, e.g. 8), "rationale": "string" }},
    "base": {{ "g": number (as %, e.g. 12), "rationale": "string" }},
    "bull": {{ "g": number (as %, e.g. 18), "rationale": "string" }}
  }},

  "required_return_r": {{
    "value": number (as %, e.g. 12),
    "rationale": "based on business risk, sector, size"
  }},

  "risk_free_rate_y": 7,

  "capital_invested_per_share": number (book value per share in INR),
  "shares_outstanding_cr": number (in Crores),
  "dps_latest": number (dividend per share, latest year, 0 if no dividend),
  "dividend_payout_pct": number (%, average last 3 years),

  "capex_avg_3yr": number (average annual capex in Cr, from investing CF),
  "operating_cf_avg_3yr": number (average annual operating CF in Cr),

  "key_assumptions_warning": ["any flags or concerns"],

  "valuation_methods_applicable": {{
    "dcf_eps": true or false,
    "dcf_fcf": true or false,
    "graham_formula": true or false,
    "pe_based": true or false,
    "epv": true or false,
    "ddm": true or false,
    "reverse_dcf": true or false,
    "greenwald_growth": true or false
  }},

  "sotp_segments": [],

  "why_methods_excluded": "explain any excluded methods"
}}

SOTP SEGMENTS SCHEMA (populate sotp_segments ONLY if stock_type == "CONGLOMERATE", else leave as []):
Each element in sotp_segments must be:
{{
  "name": "string — segment name, e.g. Jio Platforms",
  "segment_type": "string — telecom|retail|o2c|oil_gas|renewable|financial|it|fmcg|auto|infrastructure|generic",
  "ebitda_cr": number or null,     // estimated annual EBITDA in Rs crore
  "revenue_cr": number or null,    // annual revenue in Rs crore (use if EBITDA not available)
  "book_value_cr": number or null, // for financial segments only
  "stake_pct": number,             // parent company's ownership %
  "note": "string — data source or key assumption"
}}
For CONGLOMERATE stock types, populate sotp_segments with best-estimate segment data from the
financial data and web research provided. Use the business description, annual report excerpts,
and peer data to estimate segment EBITDA. This is the PRIMARY valuation input for conglomerates.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 0 — CLASSIFY BUSINESS TYPE BEFORE DOING ANYTHING ELSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A "Stock Type" hint is provided in the data. Use it, and confirm with the financials.

┌─ SECULAR GROWTH — set is_cyclical=false ────────────────────┐
│ Identify when ANY TWO of the following are true:             │
│  (a) Stock Type is: CAPITAL_MARKETS, QUALITY_COMPOUNDER,    │
│      GROWTH, or FINANCIAL (non-bank)                         │
│  (b) Profit CAGR 5yr > 15% AND relatively consistent         │
│      (not alternating boom/bust)                             │
│  (c) ROCE consistently > 20% for last 3+ years              │
│  (d) Asset-light / franchise model: software, brands,        │
│      regulatory licence, network effects                     │
│  (e) Sector: IT Services, Capital Markets, FMCG, Pharma,    │
│      Insurance, Healthcare, Specialty Chemicals (niche),     │
│      Financial Services, Asset Management                    │
│                                                              │
│ NORMALIZATION RULE:                                          │
│   normalized_eps = average of last 2-3 ANNUAL EPS years     │
│   HARD FLOOR: normalized_eps ≥ 75% of TTM EPS               │
│   NEVER use 5yr or 10yr backward average — secular growth   │
│   companies compound; old years represent a much smaller     │
│   business. A 10yr average for a 30% CAGR compounder gives  │
│   a figure 5-7x below today's true earning power.           │
└──────────────────────────────────────────────────────────────┘

┌─ CYCLICAL — set is_cyclical=true ───────────────────────────┐
│ Identify when ANY ONE is true:                               │
│  (a) Sector: Metals & Mining, Steel, Aluminium, Coal,        │
│      Cement, Oil & Gas (upstream/refining), Commodity        │
│      Chemicals, Shipping, Airlines, Power (merchant)         │
│  (b) EPS swings > 50% between adjacent years regularly      │
│      (e.g. EPS goes 50 → 10 → 80 in consecutive years)     │
│  (c) Revenue/margins directly driven by commodity prices     │
│  (d) ROCE < 10% in any of the last 5 years (down-cycle)     │
│                                                              │
│ NORMALIZATION RULE:                                          │
│   normalized_eps = 5yr or 10yr average/median (mid-cycle)   │
│   NEVER use peak-cycle EPS — overvalues by 3-5×             │
│   Use the trough year + peak year average as a sanity check  │
└──────────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REMAINING RULES (apply after classifying business type)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- High-ROCE businesses (ROCE > 20%): Greenwald growth model most relevant
- DDM applicable only if dividend payout consistently > 20%
- Negative earnings: EPV and Graham may not apply (set to false)
- Graham number needs EPS > 0 and Book Value > 0
- risk_free_rate_y is ALWAYS 7 (India 10yr G-Sec)
- required_return_r guidance:
    10-11%  → Regulated monopoly/duopoly with predictable cash flows
              (exchanges, depositories, NSDL/CDSL, power transmission, toll roads)
    11-12%  → Large, stable, quality compounder (top FMCG, IT majors, large private banks)
    12-13%  → Mid-large quality but with competitive or regulatory risk
    13-15%  → Mid/small cap or businesses with earnings volatility
    15-18%  → Early-stage, high-risk, turnaround, or distressed
- Growth rate G in growth_scenarios = EXPECTED 5-year EPS CAGR.
  G CAN legally exceed required_return_r — this is mathematically valid in a
  multi-stage DCF where G is stage-1 growth, not terminal growth.
  DO NOT cap G at (r - 1). That restriction applies ONLY to perpetuity/terminal growth.
- shares_outstanding_cr: derive from market_cap / current_price if not directly available"""


def _make_financial_summary(data: dict) -> str:
    """Condense raw scraped data into a text summary for the LLM prompt."""
    lines = []

    name = data.get("company_name") or data.get("symbol", "Unknown")
    stock_type_hint = data.get("_stock_type", "UNKNOWN")
    lines.append(f"Company: {name} ({data.get('symbol', '')})")
    lines.append(f"Stock Type (classifier): {stock_type_hint}")
    lines.append(f"Sector: {data.get('sector')} | Industry: {data.get('industry')}")
    lines.append(f"Current Price: Rs{data.get('current_price')}")
    lines.append(f"Market Cap: Rs{data.get('market_cap')} Cr")
    lines.append(f"Stock P/E: {data.get('pe')} | P/B: {data.get('pb')}")
    lines.append(f"Book Value: Rs{data.get('book_value')} | EPS (TTM): Rs{data.get('eps_ttm')}")
    lines.append(f"ROCE: {data.get('roce')}% | ROE: {data.get('roe')}%")
    lines.append(f"Dividend Yield: {data.get('dividend_yield')}%")
    lines.append(f"Face Value: Rs{data.get('face_value')}")
    lines.append("")

    # P&L history (last 10 years)
    sales = data.get("pl_sales", [])
    profits = data.get("pl_net_profit", [])
    eps = data.get("pl_eps", [])
    opm = data.get("pl_opm_pct", [])

    # Filter to only dict entries (scraped arrays sometimes contain raw floats)
    sales = [x for x in sales if isinstance(x, dict)]
    profits = [x for x in profits if isinstance(x, dict)]
    eps = [x for x in eps if isinstance(x, dict)]
    opm = [x for x in opm if isinstance(x, dict)]

    if sales:
        lines.append("Annual P&L (Sales, Net Profit, EPS, OPM%) [Rs Cr]:")
        for i, yr_data in enumerate(sales[-10:]):
            yr = yr_data.get("year", "")
            s = yr_data.get("value")
            p = profits[i].get("value") if i < len(profits) else None
            e = eps[i].get("value") if i < len(eps) else None
            o = opm[i].get("value") if i < len(opm) else None
            lines.append(
                f"  {yr}: Sales={s}, Profit={p}, EPS={e}, OPM={o}%"
            )
    lines.append("")

    # CAGR tables
    sc = data.get("sales_growth_cagr", {})
    pc = data.get("profit_growth_cagr", {})
    roe_cagr = data.get("roe_history_cagr", {})
    if sc:
        lines.append(f"Sales Growth CAGR: 10yr={sc.get('10_years') or sc.get('10yr')}% "
                     f"5yr={sc.get('5_years') or sc.get('5yr')}% "
                     f"3yr={sc.get('3_years') or sc.get('3yr')}% "
                     f"TTM={sc.get('ttm')}%")
    if pc:
        lines.append(f"Profit Growth CAGR: 10yr={pc.get('10_years') or pc.get('10yr')}% "
                     f"5yr={pc.get('5_years') or pc.get('5yr')}% "
                     f"3yr={pc.get('3_years') or pc.get('3yr')}% "
                     f"TTM={pc.get('ttm')}%")
    if roe_cagr:
        lines.append(f"ROE: 10yr={roe_cagr.get('10_years') or roe_cagr.get('10yr')}% "
                     f"5yr={roe_cagr.get('5_years') or roe_cagr.get('5yr')}% "
                     f"Last year={roe_cagr.get('last_year')}%")
    lines.append("")

    # Balance sheet highlights
    bs = data.get("balance_sheet", {})
    bs_years = bs.get("years", [])
    reserves = bs.get("reserves", [])
    borrowings = bs.get("borrowings", [])
    equity_cap = bs.get("equity_capital", [])
    reserves = [x for x in reserves if isinstance(x, dict)]
    borrowings = [x for x in borrowings if isinstance(x, dict)]
    equity_cap = [x for x in equity_cap if isinstance(x, dict)]
    if bs_years:
        latest = -1
        yr = bs_years[latest] if bs_years else "Latest"
        r = reserves[latest].get("value") if reserves else None
        b = borrowings[latest].get("value") if borrowings else None
        e = equity_cap[latest].get("value") if equity_cap else None
        lines.append(f"Balance Sheet ({yr}): Equity Capital={e}, Reserves={r}, Borrowings={b}")
    lines.append("")

    # Cash flow
    cf = data.get("cash_flow", {})
    cf_years = cf.get("years", [])
    ops_cf = cf.get("operating", [])
    inv_cf = cf.get("investing", [])
    if cf_years and ops_cf:
        lines.append("Cash Flow (last 3 years) [Rs Cr]:")
        for yr_data, ops, inv in zip(
            cf_years[-3:],
            ops_cf[-3:] if len(ops_cf) >= 3 else ops_cf,
            inv_cf[-3:] if len(inv_cf) >= 3 else inv_cf,
        ):
            ops_val = ops.get("value") if isinstance(ops, dict) else None
            inv_val = inv.get("value") if isinstance(inv, dict) else None
            lines.append(f"  {yr_data}: Operating={ops_val}, Investing={inv_val}")
    lines.append("")

    # Ratios annual (ROCE trend)
    ratios = data.get("ratios_annual", {})
    roce_trend = ratios.get("roce_pct", [])
    if roce_trend:
        recent = roce_trend[-5:]
        lines.append(f"ROCE trend (last 5yr): {[(r.get('year'), r.get('value')) for r in recent]}")
    lines.append("")

    # Shareholding
    sh = data.get("shareholding", {})
    lines.append(
        f"Shareholding: Promoters={sh.get('promoters')}% "
        f"FIIs={sh.get('fiis')}% DIIs={sh.get('diis')}% Public={sh.get('public')}%"
    )

    # Pros / cons
    pros = data.get("pros", [])
    cons = data.get("cons", [])
    if pros:
        lines.append(f"Pros: {'; '.join(pros[:5])}")
    if cons:
        lines.append(f"Cons: {'; '.join(cons[:5])}")

    return "\n".join(lines)


class AssumptionsAgent:

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    async def derive(self, raw_data: dict) -> dict[str, Any]:
        """Derive valuation assumptions from raw scraped data."""
        t0 = time.monotonic()
        company = raw_data.get("company_name", raw_data.get("symbol", "Company"))
        logger.info("AssumptionsAgent starting", extra={"company": company})

        financial_summary = _make_financial_summary(raw_data)
        prompt = ASSUMPTIONS_PROMPT.format(financial_summary=financial_summary)

        try:
            raw = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.1,
                json_mode=True,
            )
            result = _parse_json(raw)
        except Exception as exc:
            logger.error("AssumptionsAgent failed", extra={"company": company, "error": str(exc)})
            result = _fallback_assumptions(raw_data)

        # Ensure required keys exist
        result = _validate_assumptions(result, raw_data)
        logger.info(
            "AssumptionsAgent done",
            extra={
                "company": company,
                "eps": result.get("normalized_eps", {}).get("value", 0),
                "roce": result.get("normalized_roce", {}).get("value", 0),
                "g_base": result.get("growth_scenarios", {}).get("base", {}).get("g", 0),
                "r": result.get("required_return_r", {}).get("value", 12),
                "elapsed_s": round(time.monotonic() - t0, 1),
            },
        )
        return result


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def _fallback_assumptions(data: dict) -> dict:
    """Heuristic fallback when LLM call fails."""
    eps = data.get("eps_ttm") or 0
    roce = data.get("roce") or 15
    bv = data.get("book_value") or 0
    mc = data.get("market_cap") or 1
    price = data.get("current_price") or 1

    shares_cr = (mc / price) if price else 0

    # Estimate growth from CAGR tables
    sg = data.get("sales_growth_cagr", {})
    g_5yr = sg.get("5_years") or sg.get("5yr") or 12

    return {
        "business_type": "services",
        "is_cyclical": False,
        "cyclicality_explanation": "Fallback — could not determine",
        "normalized_eps": {"method": "TTM EPS (fallback)", "value": eps, "rationale": "Using TTM EPS"},
        "normalized_roce": {"value": roce, "rationale": "Using current ROCE"},
        "growth_scenarios": {
            "bear": {"g": max(4, g_5yr * 0.6), "rationale": "60% of 5yr CAGR"},
            "base": {"g": g_5yr, "rationale": "5yr CAGR"},
            "bull": {"g": min(25, g_5yr * 1.4), "rationale": "140% of 5yr CAGR"},
        },
        "required_return_r": {"value": 12, "rationale": "Standard 12% for Indian equity"},
        "risk_free_rate_y": 7,
        "capital_invested_per_share": bv,
        "shares_outstanding_cr": shares_cr,
        "dps_latest": 0,
        "dividend_payout_pct": 0,
        "capex_avg_3yr": 0,
        "operating_cf_avg_3yr": 0,
        "key_assumptions_warning": ["Fallback assumptions — LLM call failed"],
        "valuation_methods_applicable": {
            "dcf_eps": True,
            "dcf_fcf": True,
            "graham_formula": eps > 0,
            "pe_based": eps > 0,
            "epv": eps > 0,
            "ddm": False,
            "reverse_dcf": eps > 0,
            "greenwald_growth": True,
        },
        "why_methods_excluded": "Fallback mode",
    }


def _validate_assumptions(result: dict, data: dict) -> dict:
    """Ensure all required keys are present and sensible."""
    eps = data.get("eps_ttm") or 0
    bv = data.get("book_value") or 0
    mc = data.get("market_cap") or 1
    price = data.get("current_price") or 1

    # Shares outstanding in Crores
    if not result.get("shares_outstanding_cr"):
        result["shares_outstanding_cr"] = mc / price if price else 0

    # Ensure required_return_r has sensible value
    r = result.get("required_return_r", {})
    if not isinstance(r, dict):
        result["required_return_r"] = {"value": 12, "rationale": "Default"}
    elif not r.get("value"):
        result["required_return_r"]["value"] = 12

    # Sanity-cap growth rates at 45% max to catch LLM hallucinations.
    # Stage-1 growth CAN legally exceed WACC in a multi-stage DCF — the
    # r > g restriction applies only to the terminal (perpetuity) growth rate,
    # which is already hard-coded at 6% in INDIA_PARAMS. Capping stage-1 at
    # (r-1) was wrong and severely undervalued high-growth moat businesses.
    gs = result.get("growth_scenarios", {})
    for scenario in ("bear", "base", "bull"):
        s = gs.get(scenario, {})
        if isinstance(s, dict) and s.get("g"):
            if s["g"] > 45:
                s["g"] = 45

    # Default EPS if missing
    ne = result.get("normalized_eps", {})
    if not isinstance(ne, dict):
        result["normalized_eps"] = {"method": "TTM", "value": eps, "rationale": "TTM EPS"}
    elif not ne.get("value"):
        result["normalized_eps"]["value"] = eps

    # ── Secular-growth EPS floor guard ──────────────────────────────────────
    # Prevent the LLM from using multi-year historical averages for compounders.
    # A 10yr backward average for a 20-30% CAGR business gives an EPS figure
    # 5-7× below today's earning power — producing nonsensically low valuations.
    #
    # The guard fires if EITHER:
    #   (a) LLM said is_cyclical=False, OR
    #   (b) Quantitative signals override: ROCE > 20% AND profit CAGR 5yr > 15%
    #       (these criteria identify secular compounders objectively, regardless
    #        of whether the LLM correctly classified cyclicality)

    ne_val = float((result.get("normalized_eps") or {}).get("value") or 0)
    is_cyclical_llm = result.get("is_cyclical", False)

    # Quantitative secular-growth override
    roce_val = float(data.get("roce") or 0)
    pc = data.get("profit_growth_cagr", {})
    profit_cagr_5yr = float(pc.get("5_years") or pc.get("5yr") or 0)
    profit_cagr_3yr = float(pc.get("3_years") or pc.get("3yr") or 0)
    is_quantitative_compounder = (
        roce_val > 20 and (profit_cagr_5yr > 15 or profit_cagr_3yr > 15)
    )

    # Stock-type hint from pipeline (set by classifier)
    stock_type_hint = data.get("_stock_type", "UNKNOWN")
    secular_types = {
        "CAPITAL_MARKETS", "QUALITY_COMPOUNDER", "GROWTH",
        "FINANCIAL",  # non-bank financial services compound consistently
    }
    is_secular_type = stock_type_hint in secular_types

    is_secular_growth = (
        not is_cyclical_llm
        or is_quantitative_compounder
        or is_secular_type
    )

    if is_secular_growth and float(eps) > 0 and ne_val > 0:
        # Compute annual EPS history (exclude TTM row)
        eps_hist = [
            x for x in data.get("pl_eps", [])
            if isinstance(x, dict) and str(x.get("year", "")).upper() != "TTM"
        ]
        # Best floor: most recent annual EPS × 0.80 — allows at most 20% normalisation
        # discount, which covers genuine one-off distortions without masking growth.
        latest_annual_eps = None
        for x in reversed(eps_hist):
            try:
                v = float(x["value"])
                if v > 0:
                    latest_annual_eps = v
                    break
            except (TypeError, ValueError):
                pass

        # Compute 3yr avg for extra context
        eps_recent_vals = []
        for x in eps_hist[-3:]:
            try:
                v = float(x["value"])
                if v > 0:
                    eps_recent_vals.append(v)
            except (TypeError, ValueError):
                pass
        eps_3yr_avg = (
            sum(eps_recent_vals) / len(eps_recent_vals)
            if eps_recent_vals else float(eps)
        )

        # Floor = max(80% of latest annual, 75% of TTM)
        # The latest annual EPS is the most relevant "earning power" anchor.
        ttm_eps = float(eps)
        eps_floor = max(
            (latest_annual_eps * 0.80) if latest_annual_eps else 0,
            ttm_eps * 0.75,
        )

        if ne_val < eps_floor:
            old_val = ne_val
            reason = (
                "quantitative compounder (ROCE>{:.0f}%, profit CAGR {}%)".format(
                    roce_val,
                    max(profit_cagr_5yr, profit_cagr_3yr),
                )
                if is_quantitative_compounder and is_cyclical_llm
                else "secular growth type ({})".format(stock_type_hint)
            )
            result["normalized_eps"]["value"] = round(eps_floor, 2)
            result["normalized_eps"]["method"] = (
                "Auto-corrected for secular growth: floor=max("
                "latest_annual Rs{:.2f}x0.80, TTM Rs{:.2f}x0.75) "
                "[LLM returned Rs{:.2f}]".format(
                    latest_annual_eps or 0, ttm_eps, old_val
                )
            )
            result.setdefault("key_assumptions_warning", [])
            result["key_assumptions_warning"].append(
                "norm_eps auto-corrected Rs{:.2f} -> Rs{:.2f}: "
                "LLM used historical avg for {} business "
                "(latest_annual Rs{:.2f}, 3yr_avg Rs{:.2f}, TTM Rs{:.2f})".format(
                    old_val, eps_floor, reason,
                    latest_annual_eps or 0, eps_3yr_avg, ttm_eps
                )
            )

    # Default capital per share
    if not result.get("capital_invested_per_share"):
        result["capital_invested_per_share"] = bv

    result.setdefault("risk_free_rate_y", 7)
    result.setdefault("dps_latest", 0)
    result.setdefault("dividend_payout_pct", 0)
    result.setdefault("capex_avg_3yr", 0)
    result.setdefault("operating_cf_avg_3yr", 0)
    result.setdefault("key_assumptions_warning", [])
    result.setdefault("sotp_segments", [])  # populated by LLM for CONGLOMERATE type only

    return result
