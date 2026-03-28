"""
Business Analysis Agent — Phase 6
Generates a comprehensive business analysis using the structured prompt from spec.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.llm_client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert business and investment analyst with deep experience across
manufacturing, FMCG, commodities, pharmaceuticals, technology, and services industries.
Respond ONLY with valid JSON. No markdown, no preamble."""

BUSINESS_PROMPT = """## Company Financial & Business Data
{data_summary}

## Task
Produce a complete business analysis in the following JSON structure:

{{
  "company_name": "string",
  "industry": "string",
  "one_line_verdict": "string (20 words max)",

  "business_model": {{
    "value_chain_summary": "string",
    "primary_business_type": "commodity_processor|brand_play|specialty_niche|hybrid|services|technology",
    "margin_creation_point": "string — where in value chain does company earn its margin"
  }},

  "raw_materials": [
    {{
      "input_name": "string",
      "category": "primary_rm|energy|packaging|logistics|technology|labour",
      "cost_pct_of_total": number or null,
      "key_price_drivers": ["string"],
      "availability_risk": "low|medium|high",
      "passthrough_ability": "full|partial|none"
    }}
  ],

  "key_business_factors": [
    {{
      "factor": "string",
      "why_it_matters": "string",
      "sensitivity": "low|medium|high|critical",
      "management_control": "controllable|partially_controllable|external",
      "current_status": "string"
    }}
  ],

  "moat_analysis": {{
    "advantages": [
      {{
        "advantage": "string",
        "strength": "strong|moderate|weak|none",
        "durability_5yr": "durable|eroding|vulnerable",
        "rationale": "string"
      }}
    ],
    "overall_moat_verdict": "string"
  }},

  "replication_analysis": {{
    "total_time_years": number,
    "total_capital_indicative": "string (e.g. Rs 5,000-10,000 Cr)",
    "binding_constraint": "capital|time|relationships|regulatory|brand",
    "money_can_accelerate": true or false,
    "notes": "string"
  }},

  "risk_matrix": [
    {{
      "risk_name": "string",
      "description": "string",
      "category": "input_cost|demand|regulatory|competitive|operational|financial|governance",
      "probability": "low|medium|high",
      "impact": "low|medium|high|severe",
      "risk_type": "structural|cyclical",
      "mitigant": "string"
    }}
  ],

  "strategic_opportunities": [
    {{
      "opportunity": "string",
      "rationale": "string",
      "timeline": "string",
      "key_execution_risk": "string"
    }}
  ],

  "analyst_summary": "string — 150-200 word plain English paragraph for investment committee"
}}

Provide 3-5 items for key_business_factors, 3-5 for risk_matrix, 2-3 for strategic_opportunities.
Keep raw_materials realistic (skip if service company with no physical inputs)."""


def _make_business_summary(data: dict) -> str:
    """Build a concise business summary for the prompt."""
    lines = []
    name = data.get("company_name") or data.get("symbol", "")
    lines.append(f"Company: {name} ({data.get('symbol', '')})")
    lines.append(f"Sector: {data.get('sector')} | Industry: {data.get('industry')}")
    lines.append(f"Current Price: ₹{data.get('current_price')} | Market Cap: ₹{data.get('market_cap')} Cr")
    lines.append(f"P/E: {data.get('pe')} | ROCE: {data.get('roce')}% | ROE: {data.get('roe')}%")
    lines.append("")

    about = data.get("about")
    if about:
        lines.append(f"Business Description: {about[:500]}")
        lines.append("")

    pros = data.get("pros", [])
    cons = data.get("cons", [])
    if pros:
        lines.append("Strengths: " + " | ".join(pros[:5]))
    if cons:
        lines.append("Concerns: " + " | ".join(cons[:5]))
    lines.append("")

    # P&L summary
    sales = data.get("pl_sales", [])
    profits = data.get("pl_net_profit", [])
    if sales and profits:
        lines.append("Revenue & Profit trend (last 5 years, Rs Cr):")
        for s, p in zip(sales[-5:], profits[-5:]):
            lines.append(f"  {s.get('year')}: Revenue={s.get('value')}, Profit={p.get('value')}")
    lines.append("")

    sc = data.get("sales_growth_cagr", {})
    pc = data.get("profit_growth_cagr", {})
    if sc:
        lines.append(
            f"Growth CAGR — Sales: 5yr={sc.get('5_years') or sc.get('5yr')}% | "
            f"Profit: 5yr={pc.get('5_years') or pc.get('5yr')}%"
        )

    # Balance sheet
    bs = data.get("balance_sheet", {})
    borrowings = bs.get("borrowings", [])
    if borrowings:
        latest_debt = borrowings[-1].get("value") if borrowings else None
        lines.append(f"Latest Borrowings: ₹{latest_debt} Cr")
    lines.append("")

    # Cash flow
    cf = data.get("cash_flow", {})
    ops = cf.get("operating", [])
    if ops:
        avg_ops = sum(
            r.get("value") or 0 for r in ops[-3:]
        ) / max(len(ops[-3:]), 1)
        lines.append(f"Avg Operating CF (3yr): ₹{avg_ops:.0f} Cr")

    # Peers
    peers = data.get("peers", [])
    if peers:
        lines.append("\nPeer Comparison:")
        for p in peers[:5]:
            lines.append(
                f"  {p.get('name')}: MCap={p.get('market_cap')} P/E={p.get('pe')} ROCE={p.get('roce')}%"
            )

    return "\n".join(lines)


class BusinessAgent:

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    async def analyze(self, raw_data: dict) -> dict[str, Any]:
        """Generate business analysis."""
        summary = _make_business_summary(raw_data)
        prompt = BUSINESS_PROMPT.format(data_summary=summary)

        try:
            raw = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=3000,
                temperature=0.2,
                json_mode=True,
            )
            result = _parse_json(raw)
        except Exception as exc:
            logger.error("Business agent failed: %s", exc)
            result = _fallback_analysis(raw_data)

        # Ensure required keys
        result.setdefault("company_name", raw_data.get("company_name"))
        result.setdefault("industry", raw_data.get("industry") or raw_data.get("sector"))
        result.setdefault("one_line_verdict", "Analysis pending")
        result.setdefault("business_model", {})
        result.setdefault("raw_materials", [])
        result.setdefault("key_business_factors", [])
        result.setdefault("moat_analysis", {})
        result.setdefault("replication_analysis", {})
        result.setdefault("risk_matrix", [])
        result.setdefault("strategic_opportunities", [])
        result.setdefault("analyst_summary", "")

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


def _fallback_analysis(data: dict) -> dict:
    name = data.get("company_name") or data.get("symbol", "")
    return {
        "company_name": name,
        "industry": data.get("industry") or data.get("sector"),
        "one_line_verdict": f"{name} — analysis pending",
        "business_model": {"value_chain_summary": "Not available", "primary_business_type": "services"},
        "raw_materials": [],
        "key_business_factors": [],
        "moat_analysis": {"advantages": [], "overall_moat_verdict": "Unable to assess"},
        "replication_analysis": {"total_time_years": 0, "binding_constraint": "capital"},
        "risk_matrix": [],
        "strategic_opportunities": [],
        "analyst_summary": "Business analysis could not be generated due to an error.",
    }
