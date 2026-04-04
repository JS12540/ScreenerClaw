"""
ScreenerClaw — Screening Result Formatter
Formats a list of screening results into a clean text/markdown table
suitable for all channels (Telegram, Discord, Slack, WhatsApp, CLI).

All columns present in the data are displayed dynamically — including
query-specific extras like Intrinsic Value, Book Value, etc.
"""
from __future__ import annotations

from typing import Any, Optional


# ── Column metadata ────────────────────────────────────────────────────────────
# Maps field key -> (display header, decimal places)
COLUMN_META: dict[str, tuple[str, int]] = {
    "current_price":      ("CMP (Rs)",  2),
    "pe":                 ("P/E",       1),
    "market_cap":         ("MCap Cr",   0),
    "roce":               ("ROCE%",     1),
    "roe":                ("ROE%",      1),
    "debt_to_equity":     ("D/E",       2),
    "dividend_yield":     ("Div%",      2),
    "pb":                 ("P/B",       1),
    "roa":                ("ROA%",      1),
    "sales_qtr":          ("Sales Qtr", 0),
    "profit_qtr":         ("NP Qtr",    0),
    "sales_growth_qtr":   ("SalesVar%", 1),
    "profit_growth_qtr":  ("ProfVar%",  1),
    "sales_growth_5y":    ("Sales5Y%",  1),
    "profit_growth_5y":   ("Prof5Y%",   1),
    "sales_growth_3y":    ("Sales3Y%",  1),
    "profit_growth_3y":   ("Prof3Y%",   1),
    "sales_growth_10y":   ("Sales10Y%", 1),
    "return_1y":          ("Ret1Y%",    1),
    "return_3m":          ("Ret3M%",    1),
    "return_6m":          ("Ret6M%",    1),
    "return_3y":          ("Ret3Y%",    1),
    "return_5y":          ("Ret5Y%",    1),
    "eps":                ("EPS",       2),
    "book_value":         ("B.V. Rs",   2),
    "intrinsic_value":    ("IV Rs",     2),
    "piotroski":          ("Piotr",     0),
    "rsi":                ("RSI",       1),
    "dma_50":             ("DMA50",     1),
    "dma_200":            ("DMA200",    1),
    "current_ratio":      ("Curr Ratio",2),
    "interest_coverage":  ("Int Cov",   1),
    "promoter_holding":   ("Promo%",    1),
    "pledged_pct":        ("Pledge%",   1),
    "fii_holding":        ("FII%",      1),
    "dii_holding":        ("DII%",      1),
    "ev_ebitda":          ("EV/EBITDA", 1),
    "peg":                ("PEG",       2),
    "fcf":                ("FCF Cr",    0),
    "earnings_yield":     ("EarnYld%",  2),
    "enterprise_value":   ("EV Cr",     0),
}

# Display order — columns are shown in this priority order (unknown ones appended after)
PRIORITY_ORDER = [
    "current_price", "pe", "market_cap", "roce", "roe", "debt_to_equity",
    "dividend_yield", "pb", "intrinsic_value", "book_value",
    "sales_growth_5y", "profit_growth_5y", "return_1y",
    "promoter_holding", "pledged_pct",
    "sales_qtr", "profit_qtr", "piotroski",
]

# Internal / non-display keys to skip
_SKIP_KEYS = frozenset({
    "screener_company_id", "company_name", "ticker", "symbol", "bse_code",
    "score", "verdict", "verdict_emoji",
})


def _f(v: Any, dec: int = 1) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if dec == 0:
            return f"{f:,.0f}"
        return f"{f:,.{dec}f}"
    except (TypeError, ValueError):
        return str(v)


def _verdict_emoji(verdict: Optional[str]) -> str:
    v = (verdict or "").upper()
    if "STRONG BUY" in v:
        return "🟢"
    if "BUY" in v:
        return "🟢"
    if "WATCHLIST" in v or "WATCH" in v:
        return "🟡"
    if "HOLD" in v:
        return "🔵"
    if "AVOID" in v or "SELL" in v:
        return "🔴"
    return "⚪"


def _collect_data_cols(results: list[dict]) -> list[str]:
    """
    Discover all data columns present in the results, in priority order.
    Unknown columns are appended alphabetically after known ones.
    """
    present: set[str] = set()
    for r in results:
        for k, v in r.items():
            if k not in _SKIP_KEYS and v is not None:
                present.add(k)

    ordered: list[str] = []
    for col in PRIORITY_ORDER:
        if col in present:
            ordered.append(col)
            present.discard(col)

    # Append any remaining unknown columns alphabetically
    for col in sorted(present):
        ordered.append(col)

    return ordered


def _col_header(key: str) -> str:
    if key in COLUMN_META:
        return COLUMN_META[key][0]
    return key.replace("_", " ").title()


def _col_dec(key: str) -> int:
    if key in COLUMN_META:
        return COLUMN_META[key][1]
    return 1


def format_screening_results(
    results: list[dict],
    query: str,
    total_count: int = 0,
    channel: str = "text",
) -> str:
    """
    Format screening results for a given channel.
    Shows top 20 results with ALL dynamic columns present in the data.
    Ends with a prompt for the user to pick a stock.
    """
    if not results:
        return (
            f"*Screening: {query}*\n\n"
            "No results found. Try relaxing your criteria — for example:\n"
            "- Lower the ROCE threshold\n"
            "- Increase the market cap range\n"
            "- Remove one filter condition"
        )

    shown = results[:20]
    total_str = f"{total_count} results on Screener" if total_count else f"{len(results)} results"

    lines: list[str] = []

    # Header
    lines.append(f"*Screening Results* — {total_str}")
    lines.append(f"Query: `{query}`")
    lines.append("")

    # Discover data columns
    data_cols = _collect_data_cols(shown)
    has_score = any(r.get("score") is not None for r in shown)

    # Build header row
    header_parts = ["#", "Company"] + [_col_header(c) for c in data_cols]
    if has_score:
        header_parts.append("Score")

    # Build data rows
    rows: list[list[str]] = []
    for i, r in enumerate(shown, 1):
        name = (r.get("company_name") or r.get("ticker") or "?")[:18]
        ticker = r.get("ticker") or r.get("symbol") or ""
        row = [str(i), f"{name} ({ticker})"]

        for col in data_cols:
            val = r.get(col)
            row.append(_f(val, _col_dec(col)) if val is not None else "—")

        if has_score:
            score = r.get("score")
            verdict = r.get("verdict", "")
            emoji = _verdict_emoji(verdict)
            row.append(f"{emoji} {_f(score, 0)}" if score is not None else "—")

        rows.append(row)

    # Compute column widths
    all_rows = [header_parts] + rows
    widths = [max(len(r[i]) for r in all_rows if i < len(r)) for i in range(len(header_parts))]

    def _pad_row(r: list[str]) -> str:
        parts = []
        for i, cell in enumerate(r):
            w = widths[i] if i < len(widths) else 0
            # Right-align numeric columns (all except first two)
            if i >= 2:
                parts.append(cell.rjust(w))
            else:
                parts.append(cell.ljust(w))
        return "  ".join(parts)

    separator = "  ".join("-" * w for w in widths)

    use_code = channel not in ("slack",)
    table_lines = [_pad_row(header_parts), separator]
    for row in rows:
        table_lines.append(_pad_row(row))

    if use_code:
        lines.append("```")
        lines.extend(table_lines)
        lines.append("```")
    else:
        lines.extend(table_lines)

    lines.append("")

    # Pagination note
    if total_count > len(shown):
        lines.append(f"_Showing top {len(shown)} of {total_count} matching stocks — full list in PDF_")
        lines.append("")

    # Call to action
    lines.append("💡 *Reply with a number (1–{}) or company name to run full deep analysis*".format(len(shown)))
    lines.append("   _Example: `3` or `Coal India` or `COALINDIA`_")

    return "\n".join(lines)


def format_stock_selected_message(result: dict) -> str:
    """Short confirmation when user picks a stock from screening results."""
    name = result.get("company_name") or result.get("ticker", "?")
    ticker = result.get("ticker") or result.get("symbol", "")
    return (
        f"*Running deep analysis on {name} ({ticker})...*\n"
        "This may take 30–60 seconds."
    )
