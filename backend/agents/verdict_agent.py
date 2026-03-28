"""
Verdict Agent — Phase 7
Synthesises valuations + business analysis into final investment verdict.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.llm_client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior investment analyst synthesising a final investment verdict.
Respond ONLY with valid JSON. No markdown, no preamble."""

VERDICT_PROMPT = """## Company: {company_name} ({ticker})
## Current Market Price: ₹{current_price}

## Valuation Summary (all methods)
{valuation_table}

## Business Analysis Summary
Business Type: {business_type}
Moat: {moat_verdict}
Analyst Summary: {analyst_summary}

## Key Assumptions Used
Normalized EPS: ₹{norm_eps}
Normalized ROCE: {norm_roce}%
Growth Scenarios: Bear={g_bear}% | Base={g_base}% | Bull={g_bull}%
Required Return: {r}%
Risk-Free Rate: {y}%

## Task: Final Verdict

Respond in JSON:
{{
  "valuation_zone": "Deep Value|Fair Value|Growth Priced|Overvalued",
  "valuation_zone_rationale": "string — 2-3 sentences explaining the zone",

  "implied_growth_analysis": {{
    "implied_growth_pct": number,
    "formula_used": "Graham|Greenwald|DCF",
    "is_realistic": true or false,
    "commentary": "string — is this implied growth achievable?"
  }},

  "buy_ranges": [
    {{
      "action": "Strong Buy|Buy|Accumulate|Hold/Watch|Avoid",
      "price_from": number or null,
      "price_to": number or null,
      "rationale": "string — MoS reference and basis"
    }}
  ],

  "key_monitorables": [
    {{
      "metric": "string",
      "what_to_watch": "string",
      "threshold": "string"
    }}
  ],

  "probability_score": {{
    "total": number (0-100),
    "business_quality": number (0-40),
    "valuation_comfort": number (0-40),
    "execution_track_record": number (0-20),
    "rationale": "string"
  }}
}}

RULES:
1. Valuation zones:
   - Deep Value: stock < EPV (Greenwald) — growth for free
   - Fair Value: stock near mid-range of all valuations
   - Growth Priced: stock > EPV but < bull case — growth priced in
   - Overvalued: stock > bull case valuation

2. Implied growth: solve for G in Graham formula at current price
   V = current_price → G = (V / (EPS × Y/R) - 8.5) / 2
   Or use reverse-DCF concept

3. Buy ranges should have 5 tiers with specific price levels
4. Key monitorables: 3-5 metrics specific to THIS company
5. Probability score: be honest — score 40-60 for average, 70+ only for exceptional

For buy ranges use specific price levels derived from the valuation table."""


def _format_valuation_table(valuation_table: list[dict], current_price: float) -> str:
    """Format valuation table rows as readable text for the prompt."""
    lines = []
    for row in valuation_table:
        method = row.get("method", "")
        assumption = row.get("assumption", "")
        value = row.get("value_per_share")
        mos = row.get("mos_pct")

        if value:
            vs_market = (
                f"{'above' if value > current_price else 'below'} market "
                f"({abs((value - current_price) / current_price * 100):.0f}%)"
            )
            lines.append(
                f"  {method} [{assumption}]: ₹{value:.0f} — {vs_market} | MoS={mos:.1f}%"
                if mos is not None
                else f"  {method} [{assumption}]: ₹{value:.0f} — {vs_market}"
            )
        else:
            lines.append(f"  {method}: N/A")
    return "\n".join(lines) if lines else "No valuations computed"


class VerdictAgent:

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    async def synthesize(
        self,
        raw_data: dict,
        assumptions: dict,
        valuation_table: list[dict],
        business_analysis: dict,
    ) -> dict[str, Any]:
        """Generate final verdict."""
        current_price = raw_data.get("current_price") or 0
        company_name = raw_data.get("company_name") or raw_data.get("symbol", "")
        ticker = raw_data.get("symbol", "")

        norm_eps = assumptions.get("normalized_eps", {}).get("value", 0)
        norm_roce = assumptions.get("normalized_roce", {}).get("value", 0)
        gs = assumptions.get("growth_scenarios", {})
        g_bear = gs.get("bear", {}).get("g", 0)
        g_base = gs.get("base", {}).get("g", 0)
        g_bull = gs.get("bull", {}).get("g", 0)
        r = assumptions.get("required_return_r", {}).get("value", 12)
        y = assumptions.get("risk_free_rate_y", 7)

        moat_verdict = (
            business_analysis.get("moat_analysis", {}).get("overall_moat_verdict", "N/A")
        )
        analyst_summary = business_analysis.get("analyst_summary", "")[:300]
        business_type = assumptions.get("business_type", "services")

        val_table_str = _format_valuation_table(valuation_table, current_price)

        prompt = VERDICT_PROMPT.format(
            company_name=company_name,
            ticker=ticker,
            current_price=current_price,
            valuation_table=val_table_str,
            business_type=business_type,
            moat_verdict=moat_verdict,
            analyst_summary=analyst_summary,
            norm_eps=norm_eps,
            norm_roce=norm_roce,
            g_bear=g_bear,
            g_base=g_base,
            g_bull=g_bull,
            r=r,
            y=y,
        )

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
            logger.error("Verdict agent failed: %s", exc)
            result = _fallback_verdict(current_price, valuation_table)

        # Ensure defaults
        result.setdefault("valuation_zone", "Fair Value")
        result.setdefault("valuation_zone_rationale", "")
        result.setdefault("implied_growth_analysis", {})
        result.setdefault("buy_ranges", _default_buy_ranges(current_price))
        result.setdefault("key_monitorables", [])
        result.setdefault("probability_score", {"total": 50, "business_quality": 20,
                                                  "valuation_comfort": 20, "execution_track_record": 10})

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


def _default_buy_ranges(current_price: float) -> list[dict]:
    return [
        {"action": "Strong Buy", "price_from": None, "price_to": round(current_price * 0.6), "rationale": ">40% below current price"},
        {"action": "Buy", "price_from": round(current_price * 0.6), "price_to": round(current_price * 0.8), "rationale": "20-40% below current"},
        {"action": "Accumulate", "price_from": round(current_price * 0.8), "price_to": round(current_price * 0.9), "rationale": "10-20% below current"},
        {"action": "Hold/Watch", "price_from": round(current_price * 0.9), "price_to": round(current_price * 1.1), "rationale": "Near current price"},
        {"action": "Avoid", "price_from": round(current_price * 1.1), "price_to": None, "rationale": "Above fair value"},
    ]


def _fallback_verdict(current_price: float, valuation_table: list[dict]) -> dict:
    return {
        "valuation_zone": "Fair Value",
        "valuation_zone_rationale": "Could not compute — using fallback",
        "implied_growth_analysis": {
            "implied_growth_pct": 0,
            "formula_used": "N/A",
            "is_realistic": True,
            "commentary": "Could not compute implied growth",
        },
        "buy_ranges": _default_buy_ranges(current_price),
        "key_monitorables": [
            {"metric": "Revenue Growth", "what_to_watch": "Quarterly YoY growth", "threshold": "> 10%"},
            {"metric": "ROCE", "what_to_watch": "Annual ROCE", "threshold": "> 15%"},
            {"metric": "Debt", "what_to_watch": "Debt-to-equity", "threshold": "< 1x"},
        ],
        "probability_score": {
            "total": 50,
            "business_quality": 20,
            "valuation_comfort": 20,
            "execution_track_record": 10,
            "rationale": "Fallback score — verdict agent failed",
        },
    }
