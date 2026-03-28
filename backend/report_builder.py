"""
Report Builder — Phase 8
Compiles all analysis outputs into a structured Markdown report.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional


def build_report(
    raw_data: dict,
    assumptions: dict,
    valuations: dict,
    valuation_table: list[dict],
    business_analysis: dict,
    verdict: dict,
) -> str:
    """Build the complete Markdown investment research report."""

    company = raw_data.get("company_name") or raw_data.get("symbol", "Unknown")
    ticker = raw_data.get("symbol", "")
    price = raw_data.get("current_price")
    mcap = raw_data.get("market_cap")
    analysis_date = date.today().isoformat()

    lines = []

    # ── Header ─────────────────────────────────────────────────────────────────
    lines.append(f"# {company} ({ticker}) — Investment Research Report")
    lines.append(f"**Date**: {analysis_date} | **Price**: ₹{_f(price)} | **Market Cap**: ₹{_f(mcap)} Cr")
    lines.append("")
    lines.append("---")

    # ── 1. Executive Summary ────────────────────────────────────────────────────
    lines.append("## 1. Executive Summary")
    lines.append("")

    one_liner = business_analysis.get("one_line_verdict", "")
    if one_liner:
        lines.append(f"**Verdict**: {one_liner}")
        lines.append("")

    zone = verdict.get("valuation_zone", "")
    zone_rationale = verdict.get("valuation_zone_rationale", "")
    if zone:
        lines.append(f"**Valuation Zone**: {zone}")
        if zone_rationale:
            lines.append(f"> {zone_rationale}")
    lines.append("")

    prob = verdict.get("probability_score", {})
    total_score = prob.get("total", 0)
    bq = prob.get("business_quality", 0)
    vc = prob.get("valuation_comfort", 0)
    et = prob.get("execution_track_record", 0)
    lines.append(f"**Outperformance Probability Score**: {total_score}/100")
    lines.append(f"- Business Quality: {bq}/40")
    lines.append(f"- Valuation Comfort: {vc}/40")
    lines.append(f"- Execution Track Record: {et}/20")
    lines.append("")
    if prob.get("rationale"):
        lines.append(f"> {prob['rationale']}")
    lines.append("")

    # ── 2. Business Analysis ────────────────────────────────────────────────────
    lines.append("## 2. Business Analysis")
    lines.append("")

    # 2.1 Business Model
    lines.append("### 2.1 Business Model & Value Chain")
    bm = business_analysis.get("business_model", {})
    if bm.get("value_chain_summary"):
        lines.append(bm["value_chain_summary"])
    if bm.get("margin_creation_point"):
        lines.append(f"\n**Margin Creation Point**: {bm['margin_creation_point']}")
    if bm.get("primary_business_type"):
        lines.append(f"**Business Type**: {bm['primary_business_type']}")
    lines.append("")

    about = raw_data.get("about")
    if about:
        lines.append(f"**Company Description**: {about}")
        lines.append("")

    # 2.2 Key Business Factors
    lines.append("### 2.2 Key Business Factors")
    lines.append("")
    kbf = business_analysis.get("key_business_factors", [])
    if kbf:
        lines.append("| Factor | Why It Matters | Sensitivity | Management Control |")
        lines.append("|--------|---------------|-------------|-------------------|")
        for f in kbf:
            lines.append(
                f"| {f.get('factor', '')} | {f.get('why_it_matters', '')} | "
                f"{f.get('sensitivity', '')} | {f.get('management_control', '')} |"
            )
    lines.append("")

    # 2.3 Moat Analysis
    lines.append("### 2.3 Moat Analysis")
    moat = business_analysis.get("moat_analysis", {})
    overall = moat.get("overall_moat_verdict", "")
    if overall:
        lines.append(f"**Overall**: {overall}")
        lines.append("")
    advantages = moat.get("advantages", [])
    if advantages:
        lines.append("| Advantage | Strength | Durability (5yr) | Rationale |")
        lines.append("|-----------|----------|-----------------|-----------|")
        for a in advantages:
            lines.append(
                f"| {a.get('advantage', '')} | {a.get('strength', '')} | "
                f"{a.get('durability_5yr', '')} | {a.get('rationale', '')} |"
            )
    lines.append("")

    # Replication analysis
    rep = business_analysis.get("replication_analysis", {})
    if rep:
        lines.append("**Competitive Moat — Replication Difficulty**:")
        lines.append(f"- Time to replicate: ~{rep.get('total_time_years', '?')} years")
        lines.append(f"- Capital required: {rep.get('total_capital_indicative', '?')}")
        lines.append(f"- Binding constraint: {rep.get('binding_constraint', '?')}")
        lines.append(f"- Money can accelerate: {rep.get('money_can_accelerate', '?')}")
        if rep.get("notes"):
            lines.append(f"- Notes: {rep['notes']}")
    lines.append("")

    # 2.4 Risk Matrix
    lines.append("### 2.4 Risk Matrix")
    risks = business_analysis.get("risk_matrix", [])
    if risks:
        lines.append("| Risk | Category | Probability | Impact | Type | Mitigant |")
        lines.append("|------|----------|-------------|--------|------|----------|")
        for r in risks:
            lines.append(
                f"| {r.get('risk_name', '')} | {r.get('category', '')} | "
                f"{r.get('probability', '')} | {r.get('impact', '')} | "
                f"{r.get('risk_type', '')} | {r.get('mitigant', '')} |"
            )
    lines.append("")

    # 2.5 Strategic Opportunities
    lines.append("### 2.5 Strategic Opportunities")
    opps = business_analysis.get("strategic_opportunities", [])
    for opp in opps:
        lines.append(f"**{opp.get('opportunity', '')}**")
        lines.append(f"- Rationale: {opp.get('rationale', '')}")
        lines.append(f"- Timeline: {opp.get('timeline', '')}")
        lines.append(f"- Key risk: {opp.get('key_execution_risk', '')}")
        lines.append("")

    # Analyst summary
    analyst_summary = business_analysis.get("analyst_summary", "")
    if analyst_summary:
        lines.append("**Analyst Summary**:")
        lines.append(analyst_summary)
    lines.append("")

    # ── 3. Financial Summary ─────────────────────────────────────────────────
    lines.append("## 3. Financial Summary (Historical Trend)")
    lines.append("")

    # P&L Table
    pl_years = raw_data.get("pl_years", [])
    pl_sales = raw_data.get("pl_sales", [])
    pl_profit = raw_data.get("pl_net_profit", [])
    pl_eps = raw_data.get("pl_eps", [])
    pl_opm = raw_data.get("pl_opm_pct", [])

    if pl_years:
        lines.append("### Profit & Loss (Annual, ₹ Cr)")
        lines.append("")
        # Use last 10 years
        yrs = pl_years[-10:]
        sales_vals = [r.get("value") for r in pl_sales[-10:]] if pl_sales else [""] * len(yrs)
        profit_vals = [r.get("value") for r in pl_profit[-10:]] if pl_profit else [""] * len(yrs)
        eps_vals = [r.get("value") for r in pl_eps[-10:]] if pl_eps else [""] * len(yrs)
        opm_vals = [r.get("value") for r in pl_opm[-10:]] if pl_opm else [""] * len(yrs)

        header = "| " + " | ".join(yrs) + " |"
        sep = "|" + "|".join(["---"] * len(yrs)) + "|"
        lines.append(header)
        lines.append(sep)
        lines.append("| **Sales** | " + " | ".join(_f(v) for v in sales_vals[1:]) + " |" if len(yrs) > 1 else "")

        # Proper table
        rows = [
            ("Sales", sales_vals),
            ("Net Profit", profit_vals),
            ("EPS (₹)", eps_vals),
            ("OPM %", opm_vals),
        ]
        col_header = "| Metric | " + " | ".join(str(y) for y in yrs) + " |"
        col_sep = "|--------|" + "|".join(["---"] * len(yrs)) + "|"
        lines[-2] = col_header  # Replace
        lines[-1] = col_sep
        for rname, rvals in rows:
            lines.append(f"| **{rname}** | " + " | ".join(_f(v) for v in rvals) + " |")
        lines.append("")

    # CAGR tables
    sc = raw_data.get("sales_growth_cagr", {})
    pc = raw_data.get("profit_growth_cagr", {})
    if sc or pc:
        lines.append("### Compounded Growth Rates (%)")
        lines.append("")
        lines.append("| Period | Sales Growth | Profit Growth |")
        lines.append("|--------|-------------|--------------|")
        for period in ["10_years", "5_years", "3_years", "ttm"]:
            label = period.replace("_", " ").title()
            sg = sc.get(period) or sc.get(period.replace("_years", "yr"))
            pg = pc.get(period) or pc.get(period.replace("_years", "yr"))
            lines.append(f"| {label} | {_f(sg)}% | {_f(pg)}% |")
        lines.append("")

    # Key Ratios
    lines.append("### Key Ratios")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    metrics = [
        ("Market Cap (₹ Cr)", mcap),
        ("Current Price (₹)", price),
        ("Stock P/E", raw_data.get("pe")),
        ("P/B", raw_data.get("pb")),
        ("Book Value (₹)", raw_data.get("book_value")),
        ("EPS TTM (₹)", raw_data.get("eps_ttm")),
        ("ROCE %", raw_data.get("roce")),
        ("ROE %", raw_data.get("roe")),
        ("Dividend Yield %", raw_data.get("dividend_yield")),
        ("Face Value (₹)", raw_data.get("face_value")),
        ("52W High (₹)", raw_data.get("high_52w")),
        ("52W Low (₹)", raw_data.get("low_52w")),
    ]
    for label, val in metrics:
        if val is not None:
            lines.append(f"| {label} | {_f(val)} |")
    lines.append("")

    # Shareholding
    sh = raw_data.get("shareholding", {})
    if sh:
        lines.append("### Shareholding Pattern")
        lines.append(f"*(As of {sh.get('latest_quarter', 'latest')})*")
        lines.append("")
        lines.append("| Category | Holding % |")
        lines.append("|----------|-----------|")
        for cat, key in [("Promoters", "promoters"), ("FIIs", "fiis"), ("DIIs", "diis"), ("Public", "public")]:
            val = sh.get(key)
            if val is not None:
                lines.append(f"| {cat} | {_f(val)}% |")
        lines.append("")

    # Peers
    peers = raw_data.get("peers", [])
    if peers:
        lines.append("### Peer Comparison")
        lines.append("")
        lines.append("| Company | Market Cap | P/E | ROCE % | ROE % |")
        lines.append("|---------|-----------|-----|--------|-------|")
        for p in peers[:8]:
            lines.append(
                f"| {p.get('name', '')} | {_f(p.get('market_cap'))} | "
                f"{_f(p.get('pe'))} | {_f(p.get('roce'))} | {_f(p.get('roe'))} |"
            )
        lines.append("")

    # ── 4. Assumptions Used ─────────────────────────────────────────────────
    lines.append("## 4. Assumptions Used")
    lines.append("")

    ne = assumptions.get("normalized_eps", {})
    nr = assumptions.get("normalized_roce", {})
    gs = assumptions.get("growth_scenarios", {})
    r_val = assumptions.get("required_return_r", {})

    lines.append(f"**Business Type**: {assumptions.get('business_type', 'N/A')} | "
                 f"**Cyclical**: {'Yes' if assumptions.get('is_cyclical') else 'No'}")
    if assumptions.get("cyclicality_explanation"):
        lines.append(f"> {assumptions['cyclicality_explanation']}")
    lines.append("")
    lines.append(f"| Assumption | Value | Method / Rationale |")
    lines.append(f"|------------|-------|--------------------|")
    lines.append(f"| Normalized EPS (₹) | {_f(ne.get('value'))} | {ne.get('method', '')}: {ne.get('rationale', '')} |")
    lines.append(f"| Normalized ROCE % | {_f(nr.get('value'))} | {nr.get('rationale', '')} |")
    lines.append(f"| Growth — Bear | {_f(gs.get('bear', {}).get('g'))}% | {gs.get('bear', {}).get('rationale', '')} |")
    lines.append(f"| Growth — Base | {_f(gs.get('base', {}).get('g'))}% | {gs.get('base', {}).get('rationale', '')} |")
    lines.append(f"| Growth — Bull | {_f(gs.get('bull', {}).get('g'))}% | {gs.get('bull', {}).get('rationale', '')} |")
    lines.append(f"| Required Return R | {_f(r_val.get('value'))}% | {r_val.get('rationale', '')} |")
    lines.append(f"| Risk-Free Rate Y | {assumptions.get('risk_free_rate_y', 7)}% | India 10yr G-Sec |")
    lines.append(f"| Capital / Share (₹) | {_f(assumptions.get('capital_invested_per_share'))} | Book Value per share |")
    lines.append(f"| Shares Outstanding | {_f(assumptions.get('shares_outstanding_cr'))} Cr | |")
    lines.append("")

    warnings = assumptions.get("key_assumptions_warning", [])
    if warnings:
        lines.append("**Assumptions Warnings**:")
        for w in warnings:
            lines.append(f"- ⚠️ {w}")
    lines.append("")

    # ── 5. Valuation — All Methods ──────────────────────────────────────────
    lines.append("## 5. Valuation — All Methods")
    lines.append("")
    lines.append("| Method | Assumption | Value/Share (₹) | vs Market Price | MoS % |")
    lines.append("|--------|------------|-----------------|-----------------|-------|")

    for row in valuation_table:
        val = row.get("value_per_share")
        vs = row.get("vs_market", "—")
        mos = row.get("mos_pct")
        val_str = f"₹{val:.0f}" if val else "N/A"
        mos_str = f"{mos:.1f}%" if mos is not None else "—"
        lines.append(
            f"| {row.get('method', '')} | {row.get('assumption', '')} | "
            f"{val_str} | {vs or '—'} | {mos_str} |"
        )
    lines.append("")

    # ── 6. Valuation Deep-Dive ──────────────────────────────────────────────
    lines.append("## 6. Valuation Deep-Dive")
    lines.append("")

    # 6.1 Greenwald EPV
    lines.append("### 6.1 Greenwald Earnings Power Value (EPV)")
    epv = valuations.get("greenwald_epv", {})
    if epv.get("applicable") is not False:
        lines.append(f"**Formula**: `{epv.get('formula', 'EPV = Normalized Earnings / R')}`")
        lines.append(f"- Normalized Earnings (Total): ₹{_f(epv.get('norm_earnings_total_cr'))} Cr")
        lines.append(f"- EPV at R=10%: ₹{_f(epv.get('r10_value_per_share'))} per share")
        lines.append(f"- EPV at R=12%: ₹{_f(epv.get('r12_value_per_share'))} per share")
        lines.append(f"- **Interpretation**: EPV represents the value of the business assuming zero growth.")
        lines.append(f"  If current price < EPV, you are getting growth for FREE.")
    else:
        lines.append(f"*Not applicable: {epv.get('reason', 'N/A')}*")
    lines.append("")

    # 6.2 Greenwald Growth Value
    lines.append("### 6.2 Greenwald Growth Value")
    gg = valuations.get("greenwald_growth", {})
    if gg.get("applicable") is not False:
        lines.append(f"**Formula**: `{gg.get('formula', 'PV = Capital × (ROC - G) / (R - G)')}`")
        lines.append(f"- Total Capital: ₹{_f(gg.get('total_capital_cr'))} Cr")
        lines.append(f"- ROCE / ROC: {_f(gg.get('roc_pct'))}% | Required Return R: {_f(gg.get('r_pct'))}%")
        if not gg.get("growth_creates_value"):
            lines.append(f"- ⚠️ **{gg.get('warning', 'Growth may destroy value')}**")
        if gg.get("pv_epv_ratio"):
            lines.append(f"- PV/EPV Ratio (Base): {gg['pv_epv_ratio']}x (growth premium)")
        lines.append("")
        lines.append("| Scenario | R=12% | R=10% |")
        lines.append("|----------|-------|-------|")
        for s, k12, k10 in [("Bear", "bear_r12", "bear_r10"), ("Base", "base_r12", "base_r10"), ("Bull", "bull_r12", "bull_r10"), ("Stretch (G=10%)", "stretch_r12", None)]:
            r12v = f"₹{gg.get(k12):.0f}" if gg.get(k12) else "N/A"
            r10v = f"₹{gg.get(k10):.0f}" if k10 and gg.get(k10) else "—"
            lines.append(f"| {s} | {r12v} | {r10v} |")
    else:
        lines.append(f"*Not applicable: {gg.get('reason', 'N/A')}*")
    lines.append("")

    # 6.3 Graham Number & Formula
    lines.append("### 6.3 Graham Number & Formula")
    gn = valuations.get("graham_number", {})
    gf = valuations.get("graham_formula", {})
    if gn.get("applicable") is not False:
        lines.append(f"**Graham Number Formula**: `{gn.get('formula', '√(22.5 × EPS × BV)')}`")
        lines.append(f"- With Reported EPS: ₹{_f(gn.get('reported'))}")
        lines.append(f"- With Normalized EPS: ₹{_f(gn.get('normalized'))}")
    if gf.get("applicable") is not False:
        lines.append(f"\n**Graham Valuation Formula**: `{gf.get('formula', 'EPS × (8.5 + 2G) × (Y/R)')}`")
        lines.append(f"- Y (risk-free) = {gf.get('y')} | R (req. return) = {gf.get('r')} | EPS = ₹{_f(gf.get('norm_eps'))}")
        lines.append(f"- Bear case: ₹{_f(gf.get('bear'))}")
        lines.append(f"- Base case: ₹{_f(gf.get('base'))}")
        lines.append(f"- Bull case: ₹{_f(gf.get('bull'))}")
    lines.append("")

    # 6.4 DCF
    lines.append("### 6.4 DCF (Discounted Cash Flow)")
    dcf = valuations.get("dcf", {})
    if dcf.get("applicable") is not False:
        lines.append(f"**Formula**: Two-stage DCF | Projection: 10 years | Terminal Growth: {dcf.get('terminal_growth_rate_pct')}%")
        lines.append(f"- Avg FCF (3yr): ₹{_f(dcf.get('fcf_avg_3yr_cr'))} Cr")
        lines.append(f"- Discount Rate R: {_f(dcf.get('r_pct'))}%")
        lines.append("")
        lines.append("| Scenario | Total NPV (₹Cr) | TV % of NPV | Value/Share | TV Flag |")
        lines.append("|----------|----------------|-------------|-------------|---------|")
        for s_label, s_key in [("Bear", "bear"), ("Base", "base"), ("Bull", "bull")]:
            s = dcf.get(s_key, {})
            if s and not s.get("error"):
                flag = "⚠️ High" if s.get("flag_high_terminal_value") else "OK"
                lines.append(
                    f"| {s_label} | {_f(s.get('total_npv_cr'))} | "
                    f"{s.get('tv_pct_of_total', 0):.0f}% | "
                    f"₹{_f(s.get('value_per_share'))} | {flag} |"
                )
    else:
        lines.append(f"*Not applicable: {dcf.get('reason', 'FCF negative or zero')}*")
    lines.append("")

    # 6.5 PEG
    lines.append("### 6.5 PEG Ratio")
    pg = valuations.get("peg", {})
    if pg.get("applicable") is not False:
        lines.append(f"**Formula**: `{pg.get('formula', 'Fair Price = Normalized EPS × G%')}`")
        lines.append(f"- Fair P/E = {pg.get('fair_pe')}x | Fair Price = ₹{_f(pg.get('fair_price'))}")
        lines.append(f"- Current PEG: {_f(pg.get('current_peg'))}x → **{pg.get('interpretation', '')}**")
    lines.append("")

    # 6.6 DDM
    lines.append("### 6.6 DDM (Dividend Discount Model)")
    ddm = valuations.get("ddm", {})
    if ddm.get("applicable") is not False:
        lines.append(f"**Formula**: `P = D1 / (R - G)`")
        lines.append(f"- DPS: ₹{_f(ddm.get('dps'))}")
        lines.append(f"- Base case: ₹{_f(ddm.get('base'))}")
        lines.append(f"- Bull case: ₹{_f(ddm.get('bull'))}")
    else:
        lines.append(f"*Not applicable: {ddm.get('reason', 'Dividend payout < 20%')}*")
    lines.append("")

    # ── 7. What Growth Is Priced In? ────────────────────────────────────────
    lines.append("## 7. What Growth Is Priced In?")
    lines.append("")
    implied = verdict.get("implied_growth_analysis", {})
    lines.append(f"**Implied Growth at Current Price**: {_f(implied.get('implied_growth_pct'))}%")
    lines.append(f"**Formula Used**: {implied.get('formula_used', 'N/A')}")
    lines.append(f"**Is This Realistic?**: {'Yes ✓' if implied.get('is_realistic') else 'No ✗'}")
    if implied.get("commentary"):
        lines.append(f"\n{implied['commentary']}")
    lines.append("")

    # ── 8. Buy/Sell Ranges ──────────────────────────────────────────────────
    lines.append("## 8. Buy/Sell Ranges")
    lines.append("")
    lines.append("| Action | Price Range (₹) | Rationale |")
    lines.append("|--------|----------------|-----------|")
    for br in verdict.get("buy_ranges", []):
        p_from = br.get("price_from")
        p_to = br.get("price_to")
        if p_from is None:
            price_range = f"Below ₹{p_to}" if p_to else "—"
        elif p_to is None:
            price_range = f"Above ₹{p_from}"
        else:
            price_range = f"₹{p_from} – ₹{p_to}"
        lines.append(f"| **{br.get('action', '')}** | {price_range} | {br.get('rationale', '')} |")
    lines.append("")

    # ── 9. Key Monitorables ──────────────────────────────────────────────────
    lines.append("## 9. Key Monitorables (Watch Each Quarter)")
    lines.append("")
    monitors = verdict.get("key_monitorables", [])
    if monitors:
        lines.append("| Metric | What to Watch | Threshold |")
        lines.append("|--------|--------------|-----------|")
        for m in monitors:
            lines.append(
                f"| {m.get('metric', '')} | {m.get('what_to_watch', '')} | {m.get('threshold', '')} |"
            )
    lines.append("")

    # ── 10. Appendix — Raw Data ──────────────────────────────────────────────
    lines.append("## 10. Appendix — Raw Data")
    lines.append("")
    lines.append("### Quarterly Results (Last 8 Quarters, ₹ Cr)")
    lines.append("")
    qtrs = raw_data.get("quarterly_results", [])
    if qtrs:
        lines.append("| Quarter | Sales | Net Profit | OPM % | EPS |")
        lines.append("|---------|-------|-----------|-------|-----|")
        for q in qtrs[-8:]:
            lines.append(
                f"| {q.get('quarter', '')} | {_f(q.get('sales'))} | "
                f"{_f(q.get('net_profit'))} | {_f(q.get('opm_pct'))} | {_f(q.get('eps'))} |"
            )
    lines.append("")

    # Pros / Cons
    pros = raw_data.get("pros", [])
    cons = raw_data.get("cons", [])
    if pros or cons:
        lines.append("### Strengths & Concerns")
        if pros:
            lines.append("\n**Strengths (Screener):**")
            for p in pros:
                lines.append(f"- {p}")
        if cons:
            lines.append("\n**Concerns (Screener):**")
            for c in cons:
                lines.append(f"- {c}")
    lines.append("")

    lines.append("---")
    lines.append(
        "*This report is generated by an AI investment research agent. "
        "All data sourced from Screener.in. "
        "This is NOT financial advice. Please do your own due diligence.*"
    )

    return "\n".join(lines)


def _f(val, decimals: int = 2) -> str:
    """Format a number nicely, return '—' for None."""
    if val is None:
        return "—"
    if isinstance(val, float):
        if val == int(val):
            return f"{int(val):,}"
        return f"{val:,.{decimals}f}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)
