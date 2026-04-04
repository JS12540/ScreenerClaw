"""
ScreenerClaw — Report Builder
Compiles all 5-step analysis outputs into a comprehensive Markdown report.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional


def _f(v: Any, decimals: int = 0) -> str:
    if v is None:
        return "N/A"
    try:
        if decimals == 0:
            return f"{float(v):,.0f}"
        return f"{float(v):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def build_report(
    raw_data: dict,
    assumptions: dict,
    valuations: dict,
    valuation_table: list[dict],
    business_analysis: dict,
    verdict: dict,
    macro_analysis: Optional[dict] = None,
    report_outlook: Optional[dict] = None,
    scoring: Optional[dict] = None,
    stock_type: Optional[str] = None,
    mos_prices: Optional[dict] = None,
) -> str:
    """Build the complete Markdown investment research report."""

    company = raw_data.get("company_name") or raw_data.get("symbol", "Unknown")
    ticker = raw_data.get("symbol", "")
    sector = raw_data.get("sector", "")
    price = raw_data.get("current_price")
    mcap = raw_data.get("market_cap")
    analysis_date = date.today().isoformat()

    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append(f"# {company} ({ticker}) — ScreenerClaw Intelligence Report")
    lines.append(
        f"**Date**: {analysis_date} | **Price**: ₹{_f(price)} | "
        f"**MCap**: ₹{_f(mcap)} Cr | **Sector**: {sector}"
    )
    if stock_type:
        lines.append(f"**Stock Type**: {stock_type.replace('_', ' ').title()}")
    lines.append("")
    lines.append("---")

    # ── 1. Verdict & Score ─────────────────────────────────────────────────────
    lines.append("## 1. Investment Verdict")
    lines.append("")

    if scoring:
        score = scoring.get("composite_score", "N/A")
        verdict_str = scoring.get("verdict", "")
        emoji = scoring.get("verdict_emoji", "")
        lines.append(f"**Score**: {score}/100 | **Verdict**: {emoji} {verdict_str}")
        lines.append("")

    biz = business_analysis or {}
    one_liner = biz.get("one_line_verdict", "")
    if one_liner:
        lines.append(f"**One-Line Assessment**: {one_liner}")
        lines.append("")

    zone = (verdict or {}).get("valuation_zone", "")
    if zone:
        lines.append(f"**Valuation Zone**: {zone}")

    if mos_prices:
        mos_buy = mos_prices.get("mos_buy_price")
        base_iv = mos_prices.get("base_intrinsic")
        mos_pct = mos_prices.get("mos_pct_applied")
        if mos_buy and base_iv:
            lines.append(
                f"**Base Intrinsic Value**: ₹{_f(base_iv)} | "
                f"**MOS Buy Price** ({mos_pct:.0f}% discount): ₹{_f(mos_buy)}"
            )
            if price:
                gap = ((float(base_iv) - float(price)) / float(base_iv)) * 100
                lines.append(f"**Current Price vs Base IV**: {gap:+.1f}% (MOS gap)")

    lines.append("")
    lines.append("---")

    # ── 2. Business Intelligence ───────────────────────────────────────────────
    lines.append("## 2. Business Understanding (Step 1)")
    lines.append("")

    biz_report = (report_outlook or {}).get("business_intelligence_report", {})
    full_text = biz_report.get("full_report_text", "")
    if full_text:
        lines.append(full_text[:3000])
        lines.append("")
    else:
        # Fallback to analyst summary
        summary = biz.get("analyst_summary", "")
        if summary:
            lines.append(summary)
            lines.append("")

    # Moat
    moat = biz.get("moat_analysis", {})
    if moat:
        lines.append("### Moat Assessment")
        lines.append("")
        overall = moat.get("overall_moat_verdict", "")
        if overall:
            lines.append(f"> {overall}")
            lines.append("")

        advantages = moat.get("advantages", [])
        if advantages:
            lines.append("| Moat Type | Strength | Durability | Evidence |")
            lines.append("|-----------|----------|-----------|---------|")
            for a in advantages:
                moat_type = a.get("moat_type", a.get("advantage", ""))
                lines.append(
                    f"| {moat_type} | {a.get('strength','?')} | "
                    f"{a.get('durability_5yr','?')} | {a.get('evidence', a.get('rationale',''))[:80]} |"
                )
            lines.append("")

        replacement = moat.get("replacement_cost_estimate", "")
        if replacement:
            lines.append(f"**Replacement Cost**: {replacement}")
            lines.append(f"**MCap vs Replacement**: {moat.get('replacement_cost_vs_mcap', 'N/A')}")
            lines.append("")

    lines.append("---")

    # ── 3. Macro & Geopolitical Analysis (Step 2) ─────────────────────────────
    lines.append("## 3. Macro & Geopolitical Impact (Step 2)")
    lines.append("")

    mac = macro_analysis or {}
    macro_verdict = mac.get("net_macro_verdict", "NEUTRAL")
    macro_explanation = mac.get("net_macro_explanation", "")
    macro_score = mac.get("macro_score", 50)

    lines.append(f"**Macro Verdict**: {macro_verdict} (Score: {macro_score}/100)")
    if macro_explanation:
        lines.append(f"> {macro_explanation}")
    lines.append("")

    tailwinds = mac.get("tailwinds_summary", [])
    headwinds = mac.get("headwinds_summary", [])
    if tailwinds or headwinds:
        if tailwinds:
            lines.append("**Tailwinds:**")
            for t in tailwinds:
                lines.append(f"- {t}")
        if headwinds:
            lines.append("**Headwinds:**")
            for h in headwinds:
                lines.append(f"- {h}")
        lines.append("")

    lines.append("---")

    # ── 4. Outlook — Short / Medium / Long Term (Step 3) ─────────────────────
    lines.append("## 4. Business Outlook (Step 3)")
    lines.append("")

    outlook = (report_outlook or {}).get("outlook", {})
    if outlook:
        short = outlook.get("short_term", {})
        med = outlook.get("medium_term", {})
        long_ = outlook.get("long_term", {})

        lines.append("### Short Term (0-12 Months)")
        assessment = short.get("honest_assessment", "")
        if assessment:
            lines.append(f"> {assessment}")
        catalysts = short.get("key_catalysts", [])
        if catalysts:
            lines.append("**Catalysts:** " + " | ".join(catalysts[:3]))
        lines.append("")

        lines.append("### Medium Term (1-3 Years)")
        traj = med.get("earnings_trajectory", "")
        if traj:
            lines.append(f"> {traj}")
        moat_traj = med.get("moat_trajectory", "")
        if moat_traj:
            lines.append(f"**Moat trajectory**: {moat_traj}")
        lines.append("")

        lines.append("### Long Term (3-10 Years)")
        bigger = long_.get("is_bigger_in_10_years")
        if bigger is not None:
            lines.append(f"**Will be meaningfully larger in 10 years?**: {'Yes' if bigger else 'Unlikely'}")
        plausible_cagr = long_.get("plausible_earnings_cagr", "")
        if plausible_cagr:
            lines.append(f"**Plausible earnings CAGR**: {plausible_cagr}")
        lines.append("")

        thesis = outlook.get("investment_thesis", "")
        if thesis:
            lines.append("### Investment Thesis")
            lines.append(f"> {thesis}")
            lines.append("")

        monitorables = outlook.get("key_monitorables", [])
        if monitorables:
            lines.append("### Key Metrics to Monitor")
            lines.append("")
            lines.append("| Metric | Current | Red Flag Level | Why It Matters |")
            lines.append("|--------|---------|---------------|----------------|")
            for m in monitorables[:5]:
                lines.append(
                    f"| {m.get('metric','?')} | {m.get('current_value','?')} | "
                    f"{m.get('red_flag_level','?')} | {m.get('why_it_matters','?')[:60]} |"
                )
            lines.append("")

    lines.append("---")

    # ── 5. Valuation (Step 4) ────────────────────────────────────────────────
    lines.append("## 5. Valuation Analysis (Step 4)")
    lines.append("")

    if stock_type:
        lines.append(f"*Stock classified as **{stock_type.replace('_', ' ').title()}** — using adaptive valuation methods.*")
        lines.append("")

    _write_key_assumptions(lines, assumptions)

    if valuation_table:
        lines.append("### Valuation Summary Table")
        lines.append("")
        lines.append("| Method | Scenario | Value/Share (₹) | vs Current | MOS% |")
        lines.append("|--------|----------|-----------------|------------|------|")
        for r in valuation_table[:15]:
            val = r.get("value_per_share")
            lines.append(
                f"| {r.get('method', '-')} | {r.get('scenario', '-')} | "
                f"{_f(val) if val else 'N/A'} | "
                f"{r.get('vs_market', '-')} | {r.get('mos_pct', '-')} |"
            )
        lines.append("")

    if mos_prices:
        lines.append("### Margin of Safety Summary")
        lines.append("")
        lines.append(f"| Scenario | Intrinsic Value | MOS Price ({mos_prices.get('mos_pct_applied', '')}% discount) |")
        lines.append("|----------|----------------|------------------------------------------------------|")
        lines.append(f"| Bear | ₹{_f(mos_prices.get('bear_intrinsic'))} | - |")
        lines.append(f"| Base | ₹{_f(mos_prices.get('base_intrinsic'))} | ₹{_f(mos_prices.get('mos_buy_price'))} |")
        lines.append(f"| Bull | ₹{_f(mos_prices.get('bull_intrinsic'))} | - |")
        lines.append("")

    # SOTP breakdown (conglomerates only)
    sotp = valuations.get("sotp", {})
    if sotp and not sotp.get("error") and sotp.get("segments"):
        lines.append("### Sum-of-Parts (SOTP) Breakdown")
        lines.append("")
        lines.append(f"*{sotp.get('formula', 'Sigma(Segment EV × Stake%) × (1 − HoldCo Discount%) − Net Debt')}*")
        lines.append("")
        lines.append("| Segment | Type | Stake% | EBITDA (₹Cr) | Multiple | EV (₹Cr) | Per Share (₹) |")
        lines.append("|---------|------|--------|-------------|----------|----------|--------------|")
        for s in sotp["segments"]:
            ebitda = _f(s.get("ebitda_cr")) if s.get("ebitda_cr") else "—"
            mult = f"{_f(s.get('multiple'), 1)}×" if s.get("multiple") else "—"
            lines.append(
                f"| {s.get('segment','—')} | {s.get('type','—')} | {_f(s.get('stake_pct'),1)}% | "
                f"{ebitda} | {mult} | {_f(s.get('attributable_ev_cr'))} | **₹{_f(s.get('per_share'))}** |"
            )
        lines.append("")
        disc = sotp.get("holdco_discount_pct", 15)
        lines.append(
            f"- Total EV (pre-discount): ₹{_f(sotp.get('total_ev_pre_discount_cr'))} Cr  "
            f"| HoldCo discount ({disc:.0f}%): −₹{_f((sotp.get('total_ev_pre_discount_cr',0) - sotp.get('total_ev_post_discount_cr',0)))} Cr"
        )
        lines.append(f"- Net Debt: ₹{_f(sotp.get('net_debt_cr'))} Cr  |  Equity Value: ₹{_f(sotp.get('equity_value_cr'))} Cr")
        up = sotp.get("upside_pct")
        lines.append(
            f"- **SOTP Bear: ₹{_f(sotp.get('bear'))} | Base: ₹{_f(sotp.get('base'))} | Bull: ₹{_f(sotp.get('bull'))}**"
            + (f"  (Upside vs CMP: {up:+.1f}%)" if up is not None else "")
        )
        warnings = sotp.get("warnings", [])
        for w in warnings:
            lines.append(f"  > ⚠ {w}")
        lines.append("")

    # Reverse DCF insight
    rdcf = valuations.get("reverse_dcf", {})
    if rdcf.get("applicable") is not False:
        lines.append(f"**Reverse DCF**: Market implies {rdcf.get('implied_eps_cagr_pct', 'N/A')}% EPS CAGR "
                     f"(actual 5yr: {rdcf.get('actual_5yr_eps_cagr_pct', 'N/A')}%)")
        lines.append(f"> {rdcf.get('verdict', '')}")
        lines.append("")

    lines.append("---")

    # ── 6. Composite Score (Step 5) ───────────────────────────────────────────
    lines.append("## 6. Composite Score (Step 5)")
    lines.append("")

    if scoring:
        components = scoring.get("component_scores", {})
        breakdown = scoring.get("score_breakdown", [])
        if breakdown:
            lines.append("| Component | Score | Weight | Contribution |")
            lines.append("|-----------|-------|--------|-------------|")
            for row in breakdown:
                lines.append(
                    f"| {row.get('component')} | {row.get('score')}/100 | "
                    f"{row.get('weight_pct'):.0f}% | {row.get('contribution'):.1f} |"
                )
            lines.append("")

        lines.append(f"**Composite Score**: **{scoring.get('composite_score')}/100**")
        lines.append(f"**Verdict**: {scoring.get('verdict_emoji')} **{scoring.get('verdict')}**")
        lines.append("")

    lines.append("---")

    # ── 7. Risk Matrix ────────────────────────────────────────────────────────
    lines.append("## 7. Risk Matrix")
    lines.append("")

    risks = biz.get("risk_matrix", [])
    if risks:
        lines.append("| Risk | Category | Probability | Impact | Mitigant |")
        lines.append("|------|----------|-------------|--------|---------|")
        for r in risks[:7]:
            lines.append(
                f"| {r.get('risk_name', r.get('risk','?'))} | {r.get('category','?')} | "
                f"{r.get('probability','?')} | {r.get('impact','?')} | "
                f"{r.get('mitigant','?')[:60]} |"
            )
        lines.append("")

    macro_risks = mac.get("key_macro_risks", []) if mac else []
    if macro_risks:
        lines.append("### Macro Risks")
        for r in macro_risks[:3]:
            lines.append(f"- **{r.get('risk','?')}** (prob: {r.get('probability','?')}): "
                         f"{r.get('trigger','?')} → EPS impact: {r.get('eps_impact','?')}")
        lines.append("")

    lines.append("---")

    # ── 8. Financial Highlights ───────────────────────────────────────────────
    lines.append("## 8. Financial Highlights")
    lines.append("")
    _write_financial_highlights(lines, raw_data)

    # ── 9. Buy Ranges (from VerdictAgent) ─────────────────────────────────────
    buy_ranges = (verdict or {}).get("buy_ranges", [])
    if buy_ranges:
        lines.append("---")
        lines.append("## 9. Buy Range Tiers")
        lines.append("")
        lines.append("| Action | Price Range | Rationale |")
        lines.append("|--------|------------|-----------|")
        for br in buy_ranges[:5]:
            price_from = br.get("price_from") or br.get("lower")
            price_to   = br.get("price_to")   or br.get("upper")
            price_str  = f"₹{price_from} – ₹{price_to}" if (price_from and price_to) else (
                f"< ₹{price_to}" if price_to else (f"> ₹{price_from}" if price_from else "—")
            )
            lines.append(
                f"| {br.get('action','?')} | {price_str} | "
                f"{br.get('rationale', '')[:60]} |"
            )
        lines.append("")

    # ── 10. Management ────────────────────────────────────────────────────────
    mgmt = biz.get("management_quality", {})
    if mgmt:
        lines.append("---")
        lines.append("## 10. Management Quality")
        lines.append("")
        lines.append(f"| Factor | Assessment |")
        lines.append(f"|--------|-----------|")
        for key, val in [
            ("Promoter Holding", f"{mgmt.get('promoter_holding_pct', 'N/A')}% ({mgmt.get('promoter_holding_trend', 'N/A')})"),
            ("Promoter Pledge", f"{mgmt.get('promoter_pledge_pct', '0')}%"),
            ("Capital Allocation", mgmt.get("capital_allocation_track_record", "N/A")),
            ("Track Record vs Guidance", mgmt.get("track_record_vs_guidance", "N/A")),
            ("Remuneration", mgmt.get("management_remuneration_fairness", "N/A")),
            ("Overall Score", f"{mgmt.get('overall_management_score', 'N/A')}/100"),
        ]:
            lines.append(f"| {key} | {val} |")
        lines.append("")

    # ── Footer ─────────────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by ScreenerClaw — AI-native Indian equity intelligence.*")
    lines.append("*Data sources: Screener.in · NSE · BSE · Web research*")
    lines.append("*This is not financial advice. Conduct your own due diligence.*")

    return "\n".join(lines)


# ── Section Writers ───────────────────────────────────────────────────────────

def _write_key_assumptions(lines: list[str], assumptions: dict) -> None:
    if not assumptions:
        return
    lines.append("### Key Valuation Assumptions")
    lines.append("")
    ne = assumptions.get("normalized_eps", {})
    gs = assumptions.get("growth_scenarios", {})
    r = assumptions.get("required_return_r", {})

    if ne.get("value"):
        lines.append(f"- Normalized EPS: ₹{_f(ne['value'], 2)} ({ne.get('method', 'N/A')})")
    if gs:
        b, m, u = gs.get("bear", {}), gs.get("base", {}), gs.get("bull", {})
        lines.append(f"- Growth scenarios: Bear {b.get('g')}% | Base {m.get('g')}% | Bull {u.get('g')}%")
    if r.get("value"):
        lines.append(f"- Required return: {r['value']}%")

    warnings = assumptions.get("key_assumptions_warning", [])
    for w in warnings:
        lines.append(f"  ⚠️ {w}")
    lines.append("")


def _write_financial_highlights(lines: list[str], raw_data: dict) -> None:
    # Key ratios table
    cols = [
        ("P/E", "pe"), ("P/B", "pb"), ("ROCE %", "roce"), ("ROE %", "roe"),
        ("OPM %", "opm"), ("D/E", "debt_to_equity"), ("Div Yield %", "dividend_yield"),
        ("EPS TTM", "eps_ttm"),
    ]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    for label, key in cols:
        val = raw_data.get(key)
        lines.append(f"| {label} | {_f(val, 2) if val is not None else 'N/A'} |")
    lines.append("")

    # P&L trend
    sales = [x for x in raw_data.get("pl_sales", []) if isinstance(x, dict)]
    profits = [x for x in raw_data.get("pl_net_profit", []) if isinstance(x, dict)]
    if sales and profits:
        lines.append("**Revenue & Profit Trend (₹ Cr)**")
        lines.append("")
        lines.append("| Year | Revenue | PAT |")
        lines.append("|------|---------|-----|")
        for s, p in list(zip(sales, profits))[-7:]:
            lines.append(f"| {s.get('year','?')} | {_f(s.get('value'))} | {_f(p.get('value'))} |")
        lines.append("")

    # CAGR
    sc = raw_data.get("sales_growth_cagr", {})
    pc = raw_data.get("profit_growth_cagr", {})
    if sc or pc:
        lines.append("**Growth CAGRs (%)**")
        lines.append("")
        lines.append("| Period | Revenue | Profit |")
        lines.append("|--------|---------|--------|")
        for period in ("3_years", "5_years", "10_years"):
            label = period.replace("_years", "yr").replace("_", " ")
            lines.append(
                f"| {label} | {sc.get(period, sc.get(period.replace('_years','yr'), 'N/A'))}% | "
                f"{pc.get(period, pc.get(period.replace('_years','yr'), 'N/A'))}% |"
            )
        lines.append("")

    # Peers
    peers = [x for x in raw_data.get("peers", []) if isinstance(x, dict)]
    if peers:
        lines.append("**Peer Comparison**")
        lines.append("")
        lines.append("| Company | P/E | ROCE% | MCap (Cr) |")
        lines.append("|---------|-----|-------|-----------|")
        for p in peers[:6]:
            lines.append(
                f"| {p.get('name','?')} | {p.get('pe','?')} | "
                f"{p.get('roce','?')} | {_f(p.get('market_cap'))} |"
            )
        lines.append("")
