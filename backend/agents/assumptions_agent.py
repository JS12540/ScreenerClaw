"""
Assumptions Agent — Phase 3
Uses LLM to derive valuation assumptions from financial data.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.llm_client import LLMClient

logger = logging.getLogger(__name__)

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
    "graham_number": true or false,
    "graham_formula": true or false,
    "peg": true or false,
    "dcf": true or false,
    "ddm": true or false,
    "greenwald_epv": true or false,
    "greenwald_growth": true or false
  }},

  "why_methods_excluded": "explain any excluded methods"
}}

REASONING RULES:
- Cyclical companies: use mid-cycle normalized EPS, NOT peak EPS
- High-ROCE businesses (ROCE > 20%): Greenwald growth model most relevant
- DDM applicable only if dividend payout consistently > 20%
- Negative earnings: EPV and Graham may not apply (set to false)
- Graham number needs EPS > 0 and Book Value > 0
- risk_free_rate_y is ALWAYS 7 (India 10yr G-Sec)
- required_return_r: 10-12% for large stable; 13-15% for mid/small; 15-18% for risky
- Growth rate G must be < R (required return) — cap G at R minus 1%
- shares_outstanding_cr: derive from market_cap / current_price if not directly available"""


def _make_financial_summary(data: dict) -> str:
    """Condense raw scraped data into a text summary for the LLM prompt."""
    lines = []

    name = data.get("company_name") or data.get("symbol", "Unknown")
    lines.append(f"Company: {name} ({data.get('symbol', '')})")
    lines.append(f"Sector: {data.get('sector')} | Industry: {data.get('industry')}")
    lines.append(f"Current Price: ₹{data.get('current_price')}")
    lines.append(f"Market Cap: ₹{data.get('market_cap')} Cr")
    lines.append(f"Stock P/E: {data.get('pe')} | P/B: {data.get('pb')}")
    lines.append(f"Book Value: ₹{data.get('book_value')} | EPS (TTM): ₹{data.get('eps_ttm')}")
    lines.append(f"ROCE: {data.get('roce')}% | ROE: {data.get('roe')}%")
    lines.append(f"Dividend Yield: {data.get('dividend_yield')}%")
    lines.append(f"Face Value: ₹{data.get('face_value')}")
    lines.append("")

    # P&L history (last 10 years)
    sales = data.get("pl_sales", [])
    profits = data.get("pl_net_profit", [])
    eps = data.get("pl_eps", [])
    opm = data.get("pl_opm_pct", [])

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
            logger.error("Assumptions agent failed: %s", exc)
            result = _fallback_assumptions(raw_data)

        # Ensure required keys exist
        result = _validate_assumptions(result, raw_data)
        logger.info(
            "Assumptions derived: EPS=%.1f ROCE=%.1f G_base=%.1f R=%.1f",
            result.get("normalized_eps", {}).get("value", 0),
            result.get("normalized_roce", {}).get("value", 0),
            result.get("growth_scenarios", {}).get("base", {}).get("g", 0),
            result.get("required_return_r", {}).get("value", 12),
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
            "graham_number": eps > 0 and bv > 0,
            "graham_formula": eps > 0,
            "peg": eps > 0,
            "dcf": True,
            "ddm": False,
            "greenwald_epv": eps > 0,
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

    # Cap growth rates at R - 1
    r_val = result.get("required_return_r", {}).get("value", 12)
    gs = result.get("growth_scenarios", {})
    for scenario in ("bear", "base", "bull"):
        s = gs.get(scenario, {})
        if isinstance(s, dict) and s.get("g"):
            if s["g"] >= r_val:
                s["g"] = r_val - 1

    # Default EPS if missing
    ne = result.get("normalized_eps", {})
    if not isinstance(ne, dict):
        result["normalized_eps"] = {"method": "TTM", "value": eps, "rationale": "TTM EPS"}
    elif not ne.get("value"):
        result["normalized_eps"]["value"] = eps

    # Default capital per share
    if not result.get("capital_invested_per_share"):
        result["capital_invested_per_share"] = bv

    result.setdefault("risk_free_rate_y", 7)
    result.setdefault("dps_latest", 0)
    result.setdefault("dividend_payout_pct", 0)
    result.setdefault("capex_avg_3yr", 0)
    result.setdefault("operating_cf_avg_3yr", 0)
    result.setdefault("key_assumptions_warning", [])

    return result
