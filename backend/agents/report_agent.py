"""
ScreenerClaw — Report & Outlook Agent (Step 3)
Generates two outputs:
  1. Business Intelligence Report (~1500 words)
  2. Brutally honest short/medium/long-term outlook
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from backend.llm_client import LLMClient
from backend.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a senior equity research analyst writing for a sophisticated long-term
Indian equity investor who is deeply focused on capital preservation and realistic returns.
You are BRUTALLY HONEST — not diplomatically balanced.
Rules you must follow:
1. If the stock looks expensive, say it's expensive and NOT a good entry now.
2. If growth is slowing, say the growth story is maturing or over.
3. If management has destroyed capital before, flag it as a RED FLAG.
4. Your 'honest_assessment' must directly answer: "Should I buy this now? Why / Why not?"
5. Do not write promotional language. Write like you have your own money at stake.
6. For Indian IT/FMCG at 40-50x PE — be clear this is rich pricing and requires perfect execution.
You understand Indian businesses, regulations, and market dynamics deeply.
Respond ONLY with valid JSON. No markdown, no preamble."""


REPORT_PROMPT = """## Company: {company_name} ({symbol}) — {sector}
Current Price: ₹{price} | Market Cap: ₹{market_cap} Cr | P/E: {pe}

## Business Understanding (Step 1 Output)
{business_summary}

## Macro Impact (Step 2 Output)
Net Macro Verdict: {macro_verdict}
Tailwinds: {tailwinds}
Headwinds: {headwinds}
Key Macro Risks: {macro_risks}

## Financial Highlights
{financial_highlights}

## Task
Generate a comprehensive investment intelligence report in this exact JSON structure:

{{
  "business_intelligence_report": {{
    "overview": "string — plain English business overview, no jargon (150 words)",
    "what_makes_it_tick": "string — core drivers of this business's success (100 words)",
    "moat_assessment": "string — how wide, how durable, what is eroding it (100 words)",
    "revenue_model_and_growth": "string — how revenue grows and what drives it (100 words)",
    "cost_structure_and_margins": "string — cost dynamics and margin trajectory (75 words)",
    "management_assessment": "string — track record, capital allocation, governance (75 words)",
    "macro_impact_summary": "string — most important macro impacts on earnings (75 words)",
    "key_risks": [
      {{
        "risk": "string",
        "severity": "low|medium|high|critical",
        "management_response": "string"
      }}
    ],
    "what_needs_to_go_right": ["string — 3-5 factors for outperformance"],
    "full_report_text": "string — complete 1500-word investment intelligence report integrating all sections above"
  }},

  "outlook": {{
    "short_term": {{
      "horizon": "0-12 months",
      "key_catalysts": ["string — 2-3 specific events that move the stock"],
      "key_risks": ["string — 2-3 near-term risks"],
      "management_guidance_credibility": "high|medium|low|no_guidance",
      "eps_estimate_base": number or null,
      "eps_estimate_bear": number or null,
      "eps_estimate_bull": number or null,
      "honest_assessment": "string — is this a good entry point right now? (75 words)"
    }},
    "medium_term": {{
      "horizon": "1-3 years",
      "earnings_trajectory": "string — most likely earnings path (75 words)",
      "moat_trajectory": "strengthening|stable|eroding|unclear",
      "key_derailers": ["string — 2-3 things that could derail the thesis"],
      "eps_range_year2": "string — e.g. Rs 80-100",
      "eps_range_year3": "string — e.g. Rs 90-120",
      "what_would_make_you_sell": "string"
    }},
    "long_term": {{
      "horizon": "3-10 years",
      "is_bigger_in_10_years": true or false,
      "structural_tailwinds": ["string — 2-3 secular tailwinds"],
      "structural_threats": ["string — 2-3 structural risks"],
      "plausible_earnings_cagr": "string — e.g. 12-15%",
      "management_time_horizon": "decades|years|quarters",
      "thesis_change_conditions": "string — what would change your long-term view"
    }},

    "investment_thesis": "string — 150-word concise investment thesis",
    "key_monitorables": [
      {{
        "metric": "string — specific KPI to track",
        "current_value": "string",
        "red_flag_level": "string — value that would trigger thesis review",
        "why_it_matters": "string"
      }}
    ]
  }}
}}"""


def _load_system_prompt() -> str:
    """Load system prompt from SKILL.md if available, else use hardcoded default."""
    from pathlib import Path
    skill_file = Path(__file__).parent.parent.parent / "agent_skills" / "report_agent" / "SKILL.md"
    if skill_file.exists():
        content = skill_file.read_text(encoding="utf-8")
        match = re.search(r"^# System Prompt\s*\n(.*?)(?=^# |\Z)", content, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return SYSTEM_PROMPT  # fallback to hardcoded


def _build_prompt(raw_data: dict, business_analysis: dict, macro_analysis: dict) -> str:
    name = raw_data.get("company_name", "Company")
    symbol = raw_data.get("symbol", "")
    sector = raw_data.get("sector", "")
    price = raw_data.get("current_price", 0)
    mcap = raw_data.get("market_cap", 0)
    pe = raw_data.get("pe", "N/A")

    # Business summary from step 1
    biz = business_analysis or {}
    biz_parts = []
    biz_parts.append(f"One-line: {biz.get('one_line_verdict', 'N/A')}")
    biz_parts.append(f"Analyst summary: {biz.get('analyst_summary', 'N/A')}")
    moat = biz.get("moat_analysis", {})
    if moat:
        biz_parts.append(f"Moat: {moat.get('overall_moat_verdict', 'N/A')}")
    business_summary = "\n".join(biz_parts)

    # Macro summary from step 2
    mac = macro_analysis or {}
    tailwinds = "; ".join(mac.get("tailwinds_summary", [])[:3]) or "None identified"
    headwinds = "; ".join(mac.get("headwinds_summary", [])[:3]) or "None identified"
    risks = "; ".join(
        r.get("risk", "") for r in mac.get("key_macro_risks", [])[:3]
    ) or "None identified"

    # Financial highlights
    fin_lines = []
    sales = raw_data.get("pl_sales", [])
    profits = raw_data.get("pl_net_profit", [])
    if sales and profits:
        fin_lines.append("Revenue & Profit trend:")
        for s, p in list(zip(sales, profits))[-5:]:
            fin_lines.append(f"  FY{s.get('year','?')}: Rev ₹{s.get('value','?')}Cr, PAT ₹{p.get('value','?')}Cr")
    sc = raw_data.get("sales_growth_cagr", {})
    pc = raw_data.get("profit_growth_cagr", {})
    if sc:
        fin_lines.append(f"Sales CAGR: 3yr={sc.get('3_years','?')}% 5yr={sc.get('5_years','?')}%")
    if pc:
        fin_lines.append(f"Profit CAGR: 3yr={pc.get('3_years','?')}% 5yr={pc.get('5_years','?')}%")
    fin_lines.append(f"ROCE: {raw_data.get('roce','?')}% | ROE: {raw_data.get('roe','?')}%")

    return REPORT_PROMPT.format(
        company_name=name,
        symbol=symbol,
        sector=sector,
        price=price,
        market_cap=mcap,
        pe=pe,
        business_summary=business_summary,
        macro_verdict=mac.get("net_macro_verdict", "NEUTRAL"),
        tailwinds=tailwinds,
        headwinds=headwinds,
        macro_risks=risks,
        financial_highlights="\n".join(fin_lines),
    )


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


class ReportAgent:
    """
    Step 3 of the 5-step pipeline.
    Generates business intelligence report and honest short/medium/long-term outlook.
    """

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def generate(
        self,
        raw_data: dict,
        business_analysis: dict,
        macro_analysis: dict,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        company = raw_data.get("company_name", raw_data.get("symbol", "Company"))
        sector = raw_data.get("sector", "")

        logger.info(
            "ReportAgent starting",
            extra={"company": company, "sector": sector},
        )

        prompt = _build_prompt(raw_data, business_analysis, macro_analysis)

        try:
            raw = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=_load_system_prompt(),
                max_tokens=6000,
                temperature=0.15,
                json_mode=True,
            )
            result = _parse_json(raw)
            logger.info(
                "ReportAgent LLM done",
                extra={"company": company, "elapsed_s": round(time.monotonic() - t0, 1)},
            )
        except Exception as exc:
            logger.error(
                "ReportAgent failed",
                extra={"company": company, "error": str(exc)},
            )
            result = _fallback_report(raw_data)

        result.setdefault("business_intelligence_report", {})
        result.setdefault("outlook", {})

        return result


def _fallback_report(raw_data: dict) -> dict:
    name = raw_data.get("company_name", "Company")
    return {
        "business_intelligence_report": {
            "overview": f"{name} — report generation failed.",
            "full_report_text": "Report generation failed. Please retry.",
            "key_risks": [],
            "what_needs_to_go_right": [],
        },
        "outlook": {
            "short_term": {"horizon": "0-12 months", "honest_assessment": "N/A"},
            "medium_term": {"horizon": "1-3 years"},
            "long_term": {"horizon": "3-10 years"},
            "investment_thesis": "Thesis generation failed.",
            "key_monitorables": [],
        },
    }
