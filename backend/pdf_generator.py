"""
ScreenerClaw — Professional PDF Report Generator
Generates beautiful A4 PDF investment reports using reportlab.
"""
from __future__ import annotations

import base64
from datetime import date
from io import BytesIO
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph as _RLParagraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

# ── Palette ───────────────────────────────────────────────────────────────────

NAVY       = colors.HexColor("#1a2744")
NAVY_LIGHT = colors.HexColor("#253460")
ORANGE     = colors.HexColor("#e8830a")
SKY        = colors.HexColor("#e8edf8")
LIGHT_GRAY = colors.HexColor("#f5f7fa")
MID_GRAY   = colors.HexColor("#95a5a6")
DARK_TEXT  = colors.HexColor("#1c2833")
GREEN      = colors.HexColor("#1e8449")
YELLOW     = colors.HexColor("#b7770d")
RED        = colors.HexColor("#922b21")
WHITE      = colors.white
BLACK      = colors.black

VERDICT_COLORS = {
    "STRONG BUY": GREEN,
    "BUY":        GREEN,
    "WATCHLIST":  YELLOW,
    "HOLD":       colors.HexColor("#1a5276"),
    "AVOID":      RED,
    "SELL":       RED,
}


def _verdict_color(verdict: str) -> Any:
    v = (verdict or "").upper()
    for key, col in VERDICT_COLORS.items():
        if key in v:
            return col
    return NAVY


def _score_color(score: float) -> Any:
    if score >= 70:
        return GREEN
    if score >= 50:
        return YELLOW
    return RED


# ── Styles ────────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = ParagraphStyle

    styles = {
        "company_name": base(
            "company_name",
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=WHITE,
            spaceAfter=2,
            leading=26,
        ),
        "header_sub": base(
            "header_sub",
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#c8d4e8"),
            spaceAfter=0,
            leading=14,
        ),
        "section_title": base(
            "section_title",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=4,
            leading=14,
        ),
        "body": base(
            "body",
            fontName="Helvetica",
            fontSize=9,
            textColor=DARK_TEXT,
            spaceAfter=4,
            leading=13,
        ),
        "body_justify": base(
            "body_justify",
            fontName="Helvetica",
            fontSize=9,
            textColor=DARK_TEXT,
            spaceAfter=4,
            leading=13,
            alignment=TA_JUSTIFY,
        ),
        "small": base(
            "small",
            fontName="Helvetica",
            fontSize=8,
            textColor=MID_GRAY,
            spaceAfter=2,
            leading=11,
        ),
        "verdict_text": base(
            "verdict_text",
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=WHITE,
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "score_text": base(
            "score_text",
            fontName="Helvetica-Bold",
            fontSize=28,
            textColor=WHITE,
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "label": base(
            "label",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=MID_GRAY,
            spaceAfter=1,
        ),
        "value": base(
            "value",
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=DARK_TEXT,
            spaceAfter=4,
        ),
        "disclaimer": base(
            "disclaimer",
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            textColor=MID_GRAY,
            alignment=TA_CENTER,
            leading=11,
        ),
        "th": base(
            "th",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=WHITE,
            alignment=TA_CENTER,
        ),
        "td": base(
            "td",
            fontName="Helvetica",
            fontSize=8,
            textColor=DARK_TEXT,
            alignment=TA_LEFT,
        ),
        "td_center": base(
            "td_center",
            fontName="Helvetica",
            fontSize=8,
            textColor=DARK_TEXT,
            alignment=TA_CENTER,
        ),
    }
    return styles


# ── Text sanitizer ────────────────────────────────────────────────────────────
# Helvetica only covers Latin-1. Replace common Unicode chars that the LLM
# outputs so they never render as ■ (missing-glyph box) in the PDF.

_UNICODE_MAP = str.maketrans({
    "\u2014": "--",   # em dash  —
    "\u2013": "-",    # en dash  –
    "\u2012": "-",    # figure dash
    "\u2010": "-",    # hyphen
    "\u2011": "-",    # non-breaking hyphen
    "\u2018": "'",    # left single quote  '
    "\u2019": "'",    # right single quote '
    "\u201a": ",",    # single low-9 quote ‚
    "\u201c": '"',    # left double quote  "
    "\u201d": '"',    # right double quote "
    "\u201e": '"',    # double low-9 quote „
    "\u2022": "-",    # bullet  •
    "\u2023": "-",    # triangular bullet ‣
    "\u25aa": "-",    # small black square ▪
    "\u25cf": "-",    # black circle ●
    "\u2026": "...",  # ellipsis …
    "\u00b7": "-",    # middle dot ·
    "\u2212": "-",    # minus sign −
    "\u00d7": "x",    # multiplication sign ×
    "\u00f7": "/",    # division sign ÷
    "\u00a0": " ",    # non-breaking space
    "\u2009": " ",    # thin space
    "\u200b": "",     # zero-width space
    "\u2032": "'",    # prime ′
    "\u2033": '"',    # double prime ″
    "\u20b9": "Rs",   # Indian rupee sign Rs  (Helvetica lacks it — use Rs)
    "\u00ae": "(R)",  # registered trademark ®
    "\u00a9": "(C)",  # copyright ©
    "\u2122": "(TM)", # trademark ™
})


def _clean(text: str) -> str:
    """Sanitize text so it renders safely in Helvetica-based PDF."""
    if not text:
        return text
    return text.translate(_UNICODE_MAP)


def Paragraph(text, style, *args, **kwargs):
    """Drop-in wrapper that sanitizes text before passing to ReportLab."""
    cleaned = _clean(str(text)) if text is not None else ""
    return _RLParagraph(cleaned, style, *args, **kwargs)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(v: Any, dec: int = 0) -> str:
    if v is None:
        return "N/A"
    try:
        if dec == 0:
            return f"{float(v):,.0f}"
        return f"{float(v):,.{dec}f}"
    except (TypeError, ValueError):
        return str(v)


def _section_header(text: str, styles: dict) -> list:
    """Colored left-bordered section header."""
    return [
        Spacer(1, 8),
        Table(
            [[Paragraph(text.upper(), styles["section_title"])]],
            colWidths=["100%"],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), SKY),
                ("LEFTPADDING",  (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING",   (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
                ("LINEAFTER",  (0, 0), (0, -1), 3, ORANGE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]),
        ),
        Spacer(1, 4),
    ]


def _kv_row(label: str, value: str, styles: dict) -> list:
    return [
        Paragraph(label, styles["label"]),
        Paragraph(str(value), styles["value"]),
    ]


def _hr() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dee4ed"), spaceAfter=6, spaceBefore=6)


def _table_style(header_rows: int = 1) -> TableStyle:
    cmds = [
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), NAVY),
        ("TEXTCOLOR",  (0, 0), (-1, header_rows - 1), WHITE),
        ("FONTNAME",   (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("ALIGN",      (0, 0), (-1, header_rows - 1), "CENTER"),
        ("ALIGN",      (0, header_rows), (0, -1), "LEFT"),
        ("ALIGN",      (1, header_rows), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#cdd5e0")),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("WORDWRAP",   (0, 0), (-1, -1), True),
    ]
    return TableStyle(cmds)


# ── Page Header / Footer ──────────────────────────────────────────────────────

def _on_page(canvas, doc, company: str, ticker: str, report_date: str) -> None:
    W, H = A4
    canvas.saveState()

    # Top header band
    canvas.setFillColor(NAVY)
    canvas.rect(0, H - 22*mm, W, 22*mm, fill=1, stroke=0)

    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(15*mm, H - 12*mm, f"{company}  ({ticker})")

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#c8d4e8"))
    canvas.drawRightString(W - 15*mm, H - 12*mm, f"ScreenerClaw Intelligence Report  |  {report_date}")

    # Orange accent line under header
    canvas.setFillColor(ORANGE)
    canvas.rect(0, H - 23*mm, W, 1.5*mm, fill=1, stroke=0)

    # Bottom footer
    canvas.setFillColor(colors.HexColor("#f0f3f8"))
    canvas.rect(0, 0, W, 10*mm, fill=1, stroke=0)
    canvas.setFillColor(MID_GRAY)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(15*mm, 3.5*mm, "Data sources: Screener.in · NSE · BSE · Web research")
    canvas.drawRightString(W - 15*mm, 3.5*mm, f"Page {doc.page}")

    canvas.restoreState()


# ── Score Gauge ───────────────────────────────────────────────────────────────

def _score_block(score: float, verdict: str, styles: dict, page_width: float) -> list:
    """A coloured score / verdict panel."""
    score_col = _score_color(score)
    v_col = _verdict_color(verdict)

    # Score on the left, verdict details on the right
    score_cell = Table(
        [[Paragraph(f"{score:.1f}", styles["score_text"])],
         [Paragraph("/100", styles["header_sub"])]],
        colWidths=[35*mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), score_col),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]),
    )
    verdict_cell = Table(
        [[Paragraph(verdict or "—", styles["verdict_text"])]],
        colWidths=[page_width - 35*mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), v_col),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]),
    )
    combined = Table(
        [[score_cell, verdict_cell]],
        colWidths=[35*mm, page_width - 35*mm],
        style=TableStyle([
            ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]),
    )
    return [combined, Spacer(1, 6)]


# ── Section Builders ──────────────────────────────────────────────────────────

def _build_key_metrics(raw_data: dict, stock_type: str, mos_prices: dict, verdict: dict,
                       scoring: dict, styles: dict, page_width: float) -> list:
    story = []

    price = raw_data.get("current_price")
    mcap  = raw_data.get("market_cap")
    sector = raw_data.get("sector", "-")
    # Use Screener.in industry label (more specific) for Stock Type; fall back to sector
    screener_industry = (raw_data.get("industry") or raw_data.get("sector") or "-").strip()

    # Metrics strip
    cols = [
        ("Price", f"Rs{_f(price)}"),
        ("Market Cap", f"Rs{_f(mcap)} Cr"),
        ("Sector", sector[:22]),
        ("Stock Type", screener_industry[:22]),
    ]
    n = len(cols)
    col_w = page_width / n
    header_row = [Paragraph(c[0], styles["label"]) for c in cols]
    value_row  = [Paragraph(c[1], styles["value"]) for c in cols]

    metrics_tbl = Table(
        [header_row, value_row],
        colWidths=[col_w] * n,
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), SKY),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, 0), 0.3, colors.HexColor("#c8d4e8")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8d4e8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d8e0ec")),
        ]),
    )
    story.append(metrics_tbl)
    story.append(Spacer(1, 8))

    # Score block
    score   = (scoring or {}).get("composite_score", 0)
    v_str   = (scoring or {}).get("verdict", "—")
    emoji   = (scoring or {}).get("verdict_emoji", "")
    story += _score_block(float(score or 0), f"{emoji}  {v_str}".strip(), styles, page_width)

    # IV / MOS row
    if mos_prices:
        zone     = (verdict or {}).get("valuation_zone", "")
        base_iv  = mos_prices.get("base_intrinsic")
        mos_buy  = mos_prices.get("mos_buy_price")
        mos_pct  = mos_prices.get("mos_pct_applied", 0)

        zone_color = GREEN if "under" in (zone or "").lower() else (RED if "over" in (zone or "").lower() else YELLOW)

        iv_data = [
            [
                Paragraph("VALUATION ZONE", styles["label"]),
                Paragraph("BASE INTRINSIC VALUE", styles["label"]),
                Paragraph(f"MOS BUY PRICE ({mos_pct:.0f}% disc.)", styles["label"]),
            ],
            [
                Paragraph(zone or "—", ParagraphStyle("zv", fontName="Helvetica-Bold",
                                                       fontSize=10, textColor=zone_color,
                                                       alignment=TA_CENTER)),
                Paragraph(f"Rs{_f(base_iv)}", styles["value"]),
                Paragraph(f"Rs{_f(mos_buy)}", ParagraphStyle("mosv", fontName="Helvetica-Bold",
                                                              fontSize=10, textColor=GREEN,
                                                              alignment=TA_CENTER)),
            ],
        ]
        iv_tbl = Table(iv_data, colWidths=[page_width / 3] * 3,
                       style=TableStyle([
                           ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
                           ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING",    (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                           ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                           ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8d4e8")),
                           ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d8e0ec")),
                       ]))
        story.append(iv_tbl)
        story.append(Spacer(1, 6))

    return story


def _build_business_section(business_analysis: dict, report_outlook: dict, styles: dict, page_width: float) -> list:
    story = []
    biz = business_analysis or {}

    # Analyst summary
    summary = biz.get("analyst_summary", "")
    biz_intel = (report_outlook or {}).get("business_intelligence_report", {})
    full_text = biz_intel.get("full_report_text", "")

    story += _section_header("Business Profile", styles)

    one_liner = biz.get("one_line_verdict", "")
    if one_liner:
        story.append(Paragraph(f"<b>Assessment:</b> {one_liner}", styles["body"]))
        story.append(Spacer(1, 4))

    text_to_show = full_text[:2000] if full_text else summary[:2000]
    if text_to_show:
        # Split into paragraphs
        for para in text_to_show.split("\n\n")[:6]:
            para = para.strip()
            if para:
                story.append(Paragraph(para, styles["body_justify"]))
    else:
        story.append(Paragraph("Business analysis not available.", styles["small"]))

    # Moat table
    moat = biz.get("moat_analysis", {})
    advantages = moat.get("advantages", [])
    if advantages:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Competitive Moat", styles["section_title"]))
        overall = moat.get("overall_moat_verdict", "")
        if overall:
            story.append(Paragraph(f"<i>{overall}</i>", styles["small"]))
            story.append(Spacer(1, 3))

        moat_data = [["Moat Type", "Strength", "Durability", "Evidence"]]
        for a in advantages[:5]:
            moat_data.append([
                str(a.get("moat_type", "—")).replace("_", " ").title(),
                str(a.get("strength", "—")),
                str(a.get("durability_5yr", "—")),
                str(a.get("evidence", a.get("rationale", "—")))[:70],
            ])
        tbl = Table(moat_data, colWidths=[30*mm, 20*mm, 20*mm, page_width - 70*mm],
                    style=_table_style())
        story.append(tbl)

    return story


def _build_macro_section(macro_analysis: dict, styles: dict, page_width: float) -> list:
    story = []
    mac = macro_analysis or {}

    story += _section_header("Macro & Geopolitical Impact", styles)

    mv = mac.get("net_macro_verdict", "NEUTRAL")
    ms = mac.get("macro_score", 50)
    me = mac.get("net_macro_explanation", "")

    mv_col = GREEN if mv == "POSITIVE" else (RED if mv == "NEGATIVE" else YELLOW)

    verdict_tbl = Table(
        [[Paragraph("MACRO VERDICT", styles["label"]),
          Paragraph("MACRO SCORE", styles["label"])],
         [Paragraph(mv, ParagraphStyle("mv", fontName="Helvetica-Bold", fontSize=11,
                                        textColor=mv_col, alignment=TA_CENTER)),
          Paragraph(f"{ms}/100", ParagraphStyle("ms", fontName="Helvetica-Bold", fontSize=11,
                                                  textColor=NAVY, alignment=TA_CENTER))]],
        colWidths=[page_width / 2, page_width / 2],
        style=TableStyle([
            ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8d4e8")),
        ]),
    )
    story.append(verdict_tbl)
    story.append(Spacer(1, 5))

    if me:
        story.append(Paragraph(me, styles["body"]))
        story.append(Spacer(1, 4))

    tailwinds = mac.get("tailwinds_summary", [])
    headwinds = mac.get("headwinds_summary", [])
    tw_hw_data = [["TAILWINDS", "HEADWINDS"]]
    max_len = max(len(tailwinds), len(headwinds), 1)
    for i in range(max_len):
        tw = tailwinds[i] if i < len(tailwinds) else ""
        hw = headwinds[i] if i < len(headwinds) else ""
        tw_hw_data.append([
            Paragraph(f"• {tw}" if tw else "", styles["body"]),
            Paragraph(f"• {hw}" if hw else "", styles["body"]),
        ])

    tw_hw_tbl = Table(tw_hw_data, colWidths=[page_width / 2, page_width / 2],
                      style=TableStyle([
                          ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                          ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
                          ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                          ("FONTSIZE",   (0, 0), (-1, -1), 8),
                          ("ALIGN",      (0, 0), (-1, 0), "CENTER"),
                          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
                          ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#cdd5e0")),
                          ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                          ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                          ("TOPPADDING",   (0, 0), (-1, -1), 4),
                          ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                          ("VALIGN",     (0, 0), (-1, -1), "TOP"),
                      ]))
    story.append(tw_hw_tbl)

    return story


def _build_valuation_section(assumptions: dict, valuation_table: list, mos_prices: dict,
                              valuations: dict, styles: dict, page_width: float) -> list:
    story = []
    story += _section_header("Valuation Analysis", styles)

    # Assumptions
    ne = (assumptions or {}).get("normalized_eps", {})
    gs = (assumptions or {}).get("growth_scenarios", {})
    r  = (assumptions or {}).get("required_return_r", {})

    if ne or gs:
        asmps = []
        if ne.get("value"):
            asmps.append(f"Normalised EPS: Rs{_f(ne['value'], 2)}  ({ne.get('method', '')})")
        if gs:
            bear = gs.get("bear", {})
            base = gs.get("base", {})
            bull = gs.get("bull", {})
            asmps.append(f"Growth:  Bear {bear.get('g')}%  |  Base {base.get('g')}%  |  Bull {bull.get('g')}%")
        if r.get("value"):
            asmps.append(f"Required return: {r['value']}%")
        warnings = (assumptions or {}).get("key_assumptions_warning", [])
        for w in warnings[:3]:
            asmps.append(f"⚠  {w}")

        for line in asmps:
            story.append(Paragraph(line, styles["small"]))
        story.append(Spacer(1, 5))

    # Valuation table
    if valuation_table:
        tbl_data = [["Method", "Scenario", "Value/Share (Rs)", "vs Current", "MOS%"]]
        for row in valuation_table[:12]:
            val = row.get("value_per_share")
            mos = row.get("mos_pct")
            mos_col = GREEN if (mos or 0) > 20 else (RED if (mos or 0) < -10 else YELLOW)
            tbl_data.append([
                str(row.get("method", "—"))[:30],
                str(row.get("scenario", "—")),
                _f(val) if val else "N/A",
                str(row.get("vs_market", "—")),
                Paragraph(f"{mos}" if mos is not None else "—",
                          ParagraphStyle("mc", fontName="Helvetica-Bold", fontSize=8,
                                          textColor=mos_col, alignment=TA_CENTER)),
            ])

        vt = Table(tbl_data,
                   colWidths=[45*mm, 28*mm, 30*mm, 25*mm, page_width - 128*mm],
                   style=_table_style())
        story.append(vt)
        story.append(Spacer(1, 5))

    # Reverse DCF
    rdcf = (valuations or {}).get("reverse_dcf", {})
    if rdcf.get("implied_eps_cagr_pct") is not None:
        story.append(Paragraph(
            f"<b>Reverse DCF:</b> Market implies <b>{rdcf.get('implied_eps_cagr_pct')}%</b> EPS CAGR "
            f"(actual 5yr: {rdcf.get('actual_5yr_eps_cagr_pct', 'N/A')}%)",
            styles["body"],
        ))
        verdict_txt = rdcf.get("verdict", "")
        if verdict_txt:
            story.append(Paragraph(f"<i>{verdict_txt}</i>", styles["small"]))

    return story


def _build_score_section(scoring: dict, styles: dict, page_width: float) -> list:
    story = []
    story += _section_header("Composite Score Breakdown", styles)

    breakdown = (scoring or {}).get("score_breakdown", [])
    if breakdown:
        tbl_data = [["Component", "Score", "Weight", "Contribution"]]
        for row in breakdown:
            sc = row.get("score", 0)
            sc_col = _score_color(float(sc or 0))
            tbl_data.append([
                str(row.get("component", "—")),
                Paragraph(f"{sc}/100", ParagraphStyle("sc", fontName="Helvetica-Bold",
                                                        fontSize=8, textColor=sc_col,
                                                        alignment=TA_CENTER)),
                f"{row.get('weight_pct', 0):.0f}%",
                f"{row.get('contribution', 0):.1f}",
            ])
        tbl = Table(tbl_data,
                    colWidths=[50*mm, 30*mm, 25*mm, page_width - 105*mm],
                    style=_table_style())
        story.append(tbl)

    return story


def _build_financial_section(raw_data: dict, styles: dict, page_width: float) -> list:
    story = []
    story += _section_header("Financial Highlights", styles)

    # Key ratios — 2-column key-value layout
    ratio_cols = [
        ("P/E Ratio",    raw_data.get("pe")),
        ("P/B Ratio",    raw_data.get("pb")),
        ("ROCE %",       raw_data.get("roce")),
        ("ROE %",        raw_data.get("roe")),
        ("OPM %",        raw_data.get("opm")),
        ("D/E Ratio",    raw_data.get("debt_to_equity")),
        ("Div Yield %",  raw_data.get("dividend_yield")),
        ("Book Value",   raw_data.get("book_value")),
    ]
    # Build 4-column metrics table (label/val pairs across 4 columns)
    rows = []
    for i in range(0, len(ratio_cols), 4):
        label_row = []
        val_row   = []
        for j in range(4):
            if i + j < len(ratio_cols):
                lbl, val = ratio_cols[i + j]
                label_row.append(Paragraph(lbl, styles["label"]))
                val_row.append(Paragraph(_f(val, 2) if val is not None else "N/A", styles["value"]))
            else:
                label_row.append(Paragraph("", styles["label"]))
                val_row.append(Paragraph("", styles["value"]))
        rows.append(label_row)
        rows.append(val_row)

    ratio_tbl = Table(rows, colWidths=[page_width / 4] * 4,
                      style=TableStyle([
                          ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
                          ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                          ("TOPPADDING",    (0, 0), (-1, -1), 4),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                          ("BACKGROUND", (0, 0), (-1, -1), SKY),
                          ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8d4e8")),
                          ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d8e0ec")),
                      ]))
    story.append(ratio_tbl)
    story.append(Spacer(1, 8))

    # P&L trend
    sales   = [x for x in raw_data.get("pl_sales",       []) if isinstance(x, dict)]
    profits = [x for x in raw_data.get("pl_net_profit",  []) if isinstance(x, dict)]
    if sales and profits:
        story.append(Paragraph("Revenue & Profit Trend (Rs Cr)", styles["section_title"]))
        pl_data = [["Year", "Revenue (Rs Cr)", "PAT (Rs Cr)"]]
        for s, p in list(zip(sales, profits))[-8:]:
            pl_data.append([
                str(s.get("year", "?")),
                _f(s.get("value")),
                _f(p.get("value")),
            ])
        pl_tbl = Table(pl_data, colWidths=[30*mm, 50*mm, 50*mm],
                       style=_table_style())
        story.append(pl_tbl)
        story.append(Spacer(1, 5))

    # CAGR
    sc = raw_data.get("sales_growth_cagr", {})
    pc = raw_data.get("profit_growth_cagr", {})
    if sc or pc:
        story.append(Paragraph("Growth CAGRs", styles["section_title"]))
        cagr_data = [["Period", "Revenue CAGR", "Profit CAGR"]]
        for period, label in [("3_years", "3 Year"), ("5_years", "5 Year"), ("10_years", "10 Year")]:
            alt = period.replace("_years", "yr")
            sv = sc.get(period) or sc.get(alt)
            pv = pc.get(period) or pc.get(alt)
            cagr_data.append([
                label,
                f"{_f(sv, 1)}%" if sv is not None else "N/A",
                f"{_f(pv, 1)}%" if pv is not None else "N/A",
            ])
        cagr_tbl = Table(cagr_data, colWidths=[35*mm, 45*mm, 45*mm],
                         style=_table_style())
        story.append(cagr_tbl)

    # Peers
    peers = [x for x in raw_data.get("peers", []) if isinstance(x, dict)]
    if peers:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Peer Comparison", styles["section_title"]))
        peer_data = [["Company", "P/E", "ROCE %", "MCap (Rs Cr)"]]
        for p in peers[:6]:
            peer_data.append([
                str(p.get("name", "—"))[:28],
                _f(p.get("pe"), 1) if p.get("pe") is not None else "N/A",
                f"{_f(p.get('roce'), 1)}%" if p.get("roce") is not None else "N/A",
                _f(p.get("market_cap")),
            ])
        peer_tbl = Table(peer_data, colWidths=[55*mm, 25*mm, 25*mm, page_width - 105*mm],
                         style=_table_style())
        story.append(peer_tbl)

    return story


def _build_risk_section(business_analysis: dict, macro_analysis: dict,
                         styles: dict, page_width: float) -> list:
    story = []
    biz = business_analysis or {}
    mac = macro_analysis or {}

    risks = biz.get("risk_matrix", [])
    macro_risks = mac.get("key_macro_risks", [])

    if not risks and not macro_risks:
        return story

    story += _section_header("Risk Matrix", styles)

    if risks:
        risk_data = [["Risk", "Category", "Prob.", "Impact", "Mitigant"]]
        for r in risks[:6]:
            risk_data.append([
                str(r.get("risk_name", r.get("risk", "—")))[:28],
                str(r.get("category", "—")).replace("_", " ").title(),
                str(r.get("probability", "—")),
                str(r.get("impact", "—")),
                str(r.get("mitigant", "—"))[:50],
            ])
        risk_tbl = Table(risk_data,
                         colWidths=[35*mm, 25*mm, 15*mm, 15*mm, page_width - 90*mm],
                         style=_table_style())
        story.append(risk_tbl)
        story.append(Spacer(1, 5))

    if macro_risks:
        story.append(Paragraph("Macro Risks", styles["section_title"]))
        mr_data = [["Risk", "Probability", "EPS Impact"]]
        for r in macro_risks[:3]:
            mr_data.append([
                str(r.get("risk", "—"))[:40],
                str(r.get("probability", "—")),
                str(r.get("eps_impact", "—"))[:30],
            ])
        mr_tbl = Table(mr_data,
                       colWidths=[70*mm, 25*mm, page_width - 95*mm],
                       style=_table_style())
        story.append(mr_tbl)

    return story


def _build_outlook_section(report_outlook: dict, styles: dict) -> list:
    story = []
    outlook = (report_outlook or {}).get("outlook", {})
    if not outlook:
        return story

    story += _section_header("Business Outlook", styles)

    short = outlook.get("short_term", {})
    med   = outlook.get("medium_term", {})
    long_ = outlook.get("long_term", {})

    if short.get("honest_assessment"):
        story.append(Paragraph("<b>Short Term (0-12 months):</b>", styles["body"]))
        story.append(Paragraph(short["honest_assessment"], styles["body_justify"]))
        cats = short.get("key_catalysts", [])
        if cats:
            story.append(Paragraph(f"<b>Catalysts:</b> {' | '.join(cats[:3])}", styles["small"]))
        story.append(Spacer(1, 4))

    if med.get("earnings_trajectory"):
        story.append(Paragraph("<b>Medium Term (1-3 years):</b>", styles["body"]))
        story.append(Paragraph(med["earnings_trajectory"], styles["body_justify"]))
        if med.get("moat_trajectory"):
            story.append(Paragraph(f"<b>Moat trajectory:</b> {med['moat_trajectory']}", styles["small"]))
        story.append(Spacer(1, 4))

    thesis = outlook.get("investment_thesis", "")
    if thesis:
        story.append(Paragraph("<b>Investment Thesis:</b>", styles["body"]))
        story.append(Paragraph(thesis, styles["body_justify"]))

    return story


def _build_buy_ranges(verdict: dict, current_price: float, styles: dict, page_width: float) -> list:
    story = []
    buy_ranges = (verdict or {}).get("buy_ranges", [])
    if not buy_ranges:
        return story

    story += _section_header("Buy Range Tiers", styles)
    br_data = [["Action", "Price Range", "Rationale"]]
    for br in buy_ranges[:5]:
        action = str(br.get("action", "—"))
        price_from = br.get("price_from") or br.get("lower")
        price_to   = br.get("price_to")   or br.get("upper")

        if price_from and price_to:
            price_str = f"Rs{_f(price_from)} – Rs{_f(price_to)}"
        elif price_to:
            price_str = f"< Rs{_f(price_to)}"
        elif price_from:
            price_str = f"> Rs{_f(price_from)}"
        else:
            price_str = "—"

        if current_price and price_to:
            pct = ((float(price_to) - current_price) / current_price) * 100
            price_str += f"  ({pct:+.0f}%)"

        a_col = (GREEN if any(x in action.lower() for x in ("strong", "buy", "accumulate"))
                 else (YELLOW if "watch" in action.lower()
                 else RED))

        br_data.append([
            Paragraph(action, ParagraphStyle("ba", fontName="Helvetica-Bold", fontSize=8,
                                              textColor=a_col, alignment=TA_CENTER)),
            price_str,
            str(br.get("rationale", "—"))[:60],
        ])
    br_tbl = Table(br_data, colWidths=[35*mm, 50*mm, page_width - 85*mm],
                   style=_table_style())
    story.append(br_tbl)
    return story


def _build_greenwald_section(valuations: dict, raw_data: dict, styles: dict, page_width: float) -> list:
    story = []
    gw = (valuations or {}).get("greenwald_growth", {})
    if not gw or not gw.get("applicable"):
        return story

    story += _section_header("Greenwald Valuation — EPV & Growth Analysis", styles)

    # Step 1: Capital inputs
    eps_source = gw.get("eps_source", "Latest TTM EPS")
    story.append(Paragraph("<b>Step 1 — Capital Invested</b>", styles["body"]))
    cap_data = [
        ["Item", "Value"],
        ["Book Value / Share (Capital per Share)", f"Rs{_f(gw.get('capital_per_share'), 2)}"],
        ["Shares Outstanding", f"{_f(gw.get('shares_cr'), 2)} Cr"],
        ["Total Capital Invested", f"Rs{_f(gw.get('total_capital_cr'))} Cr"],
        [f"EPS — {eps_source}", f"Rs{_f(gw.get('latest_eps'), 2)}"],
        ["Total Earnings", f"Rs{_f(gw.get('total_earnings_cr'))} Cr"],
        ["ROCE (used for growth scenarios)", f"{_f(gw.get('norm_roce_pct'), 1)}%"],
    ]
    cap_tbl = Table(cap_data, colWidths=[80*mm, page_width - 80*mm], style=_table_style())
    story.append(cap_tbl)
    story.append(Spacer(1, 6))

    # Step 2: EPV
    story.append(Paragraph("<b>Step 2 — Earnings Power Value (No-Growth Floor)</b>", styles["body"]))
    story.append(Paragraph(f"EPV = Latest Earnings (TTM) / Required Return  |  Source: {eps_source}  |  Assumes zero reinvestment, zero growth", styles["small"]))
    epv_r10 = gw.get("epv_r10", {})
    epv_r12 = gw.get("epv_r12", {})
    epv_data = [
        ["Required Return (R)", "Total EPV (Rs Cr)", "Per Share EPV (Rs)"],
        ["R = 10%", _f(epv_r10.get("total_cr")), _f(epv_r10.get("per_share"))],
        ["R = 12%", _f(epv_r12.get("total_cr")), _f(epv_r12.get("per_share"))],
    ]
    epv_tbl = Table(epv_data, colWidths=[40*mm, 55*mm, page_width - 95*mm], style=_table_style())
    story.append(epv_tbl)
    story.append(Spacer(1, 6))

    # Step 3: Growth scenarios
    story.append(Paragraph("<b>Step 3 — Greenwald Growth Valuation  (R = 12%)</b>", styles["body"]))
    story.append(Paragraph("Formula: PV = Capital × (ROCE − G) / (R − G)  |  PV/EPV = Growth Premium Multiple", styles["small"]))
    gs = gw.get("growth_scenarios", {})
    gw_data = [["Growth Rate (G)", "Total Intrinsic Value (Rs Cr)", "Per Share Value (Rs)", "PV / EPV Ratio"]]
    for g_key in ("g4", "g6", "g8", "g10"):
        entry = gs.get(g_key, {})
        if entry.get("error"):
            gw_data.append([f"G = {entry.get('g_pct', '?')}%", "N/A (G ≥ R)", "—", "—"])
        else:
            ratio = entry.get("pv_epv_ratio")
            ratio_str = f"{ratio:.2f}×" if ratio else "—"
            gw_data.append([
                f"G = {entry.get('g_pct', '?')}%",
                _f(entry.get("pv_total_cr")),
                _f(entry.get("value_per_share")),
                ratio_str,
            ])
    gw_tbl = Table(gw_data, colWidths=[30*mm, 55*mm, 45*mm, page_width - 130*mm], style=_table_style())
    story.append(gw_tbl)
    story.append(Spacer(1, 5))

    # Step 4: Interpretation
    story.append(Paragraph("<b>Step 4 — Interpretation</b>", styles["body"]))
    interp = gw.get("interpretation", "")
    roc_vs_r = gw.get("roc_vs_r", "")
    interp_col = GREEN if roc_vs_r == "creates_value" else RED
    story.append(Paragraph(
        interp,
        ParagraphStyle("gw_interp", fontName="Helvetica", fontSize=9,
                        textColor=interp_col, leading=13, spaceAfter=4),
    ))

    return story


def _build_sotp_section(valuations: dict, raw_data: dict, styles: dict, page_width: float) -> list:
    """SOTP breakdown for conglomerates — shown instead of / alongside Greenwald."""
    story = []
    sotp = (valuations or {}).get("sotp", {})
    if not sotp or sotp.get("error") or not sotp.get("segments"):
        return story

    story += _section_header("Sum-of-Parts (SOTP) Valuation — Conglomerate", styles)

    segments = sotp.get("segments", [])
    total_ev_pre  = sotp.get("total_ev_pre_discount_cr", 0)
    holdco_disc   = sotp.get("holdco_discount_pct", 15)
    total_ev_post = sotp.get("total_ev_post_discount_cr", 0)
    net_debt      = sotp.get("net_debt_cr", 0)
    equity_val    = sotp.get("equity_value_cr", 0)
    base_ps       = sotp.get("base", 0)
    bear_ps       = sotp.get("bear", 0)
    bull_ps       = sotp.get("bull", 0)
    upside_pct    = sotp.get("upside_pct")

    # Intro note
    formula = sotp.get("formula", "Sigma(Segment EV × Stake%) × (1 − HoldCo Discount%) − Net Debt")
    story.append(Paragraph(f"<b>Formula:</b> {formula}", styles["small"]))
    story.append(Spacer(1, 4))

    # Segment breakdown table
    seg_data = [["Segment", "Type", "Stake%", "EBITDA (RsCr)", "Multiple", "Gross EV (RsCr)", "Attrib. EV (RsCr)", "Per Share (Rs)"]]
    for s in segments:
        ebitda = s.get("ebitda_cr")
        seg_data.append([
            str(s.get("segment", "—"))[:22],
            str(s.get("type", "—")).replace("_", " ").title()[:12],
            f"{_f(s.get('stake_pct'), 1)}%",
            _f(ebitda) if ebitda else "—",
            f"{_f(s.get('multiple'), 1)}×" if s.get("multiple") else "—",
            _f(s.get("gross_ev_cr")),
            _f(s.get("attributable_ev_cr")),
            Paragraph(f"Rs{_f(s.get('per_share'))}", ParagraphStyle(
                "sotp_ps", fontName="Helvetica-Bold", fontSize=8,
                textColor=NAVY, alignment=TA_CENTER)),
        ])

    seg_tbl = Table(
        seg_data,
        colWidths=[32*mm, 18*mm, 14*mm, 22*mm, 18*mm, 22*mm, 22*mm, page_width - 148*mm],
        style=_table_style(),
    )
    story.append(seg_tbl)
    story.append(Spacer(1, 6))

    # Bridge table: from gross EV → per-share equity value
    bridge_data = [
        ["Item", "Value (Rs Cr)"],
        ["Total EV (pre-discount)", _f(total_ev_pre)],
        [f"Less: HoldCo Discount ({holdco_disc:.0f}%)", f"−{_f(total_ev_pre - total_ev_post)}"],
        ["EV Post Discount", _f(total_ev_post)],
        [f"Less: Net Debt", f"−{_f(net_debt)}" if net_debt >= 0 else f"+{_f(abs(net_debt))} (net cash)"],
        ["Equity Value", _f(equity_val)],
    ]
    bridge_tbl = Table(bridge_data, colWidths=[80*mm, page_width - 80*mm],
                       style=TableStyle([
                           ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                           ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
                           ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
                           ("BACKGROUND", (0, -1), (-1, -1), SKY),
                           ("FONTSIZE",   (0, 0), (-1, -1), 8),
                           ("ALIGN",      (0, 0), (-1, -1), "LEFT"),
                           ("ALIGN",      (1, 0), (1, -1), "RIGHT"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -2), [WHITE, LIGHT_GRAY]),
                           ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#cdd5e0")),
                           ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING",   (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
                       ]))
    story.append(bridge_tbl)
    story.append(Spacer(1, 6))

    # Per-share summary strip
    current_price = float(raw_data.get("current_price") or 0)
    upside_str = f"{upside_pct:+.1f}%" if upside_pct is not None else "—"
    upside_col = GREEN if (upside_pct or 0) > 10 else (RED if (upside_pct or 0) < -10 else YELLOW)

    ps_data = [
        [Paragraph("BEAR (Rs)", styles["label"]),
         Paragraph("BASE (Rs)", styles["label"]),
         Paragraph("BULL (Rs)", styles["label"]),
         Paragraph("UPSIDE vs CMP", styles["label"])],
        [Paragraph(_f(bear_ps), styles["value"]),
         Paragraph(_f(base_ps), ParagraphStyle("sotp_base", fontName="Helvetica-Bold",
                                                fontSize=12, textColor=NAVY, alignment=TA_CENTER)),
         Paragraph(_f(bull_ps), styles["value"]),
         Paragraph(upside_str, ParagraphStyle("sotp_up", fontName="Helvetica-Bold",
                                               fontSize=11, textColor=upside_col,
                                               alignment=TA_CENTER))],
    ]
    ps_tbl = Table(ps_data, colWidths=[page_width / 4] * 4,
                   style=TableStyle([
                       ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
                       ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                       ("TOPPADDING",    (0, 0), (-1, -1), 5),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                       ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                       ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8d4e8")),
                       ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d8e0ec")),
                   ]))
    story.append(ps_tbl)

    # Warnings
    warnings = sotp.get("warnings", [])
    if warnings:
        story.append(Spacer(1, 4))
        for w in warnings[:4]:
            story.append(Paragraph(f"<i>⚠ {w}</i>", styles["small"]))

    note = sotp.get("note", "")
    if note:
        story.append(Spacer(1, 3))
        story.append(Paragraph(note, styles["small"]))

    return story


def _build_screener_link(raw_data: dict, styles: dict) -> list:
    story = []
    ticker = raw_data.get("symbol", "")
    if not ticker:
        return story

    story += _section_header("Data Source", styles)
    url = f"https://www.screener.in/company/{ticker}/consolidated/"
    story.append(Paragraph(
        f"Full financial data, balance sheet, and cash flow statements available at:<br/>"
        f"<b>Screener.in:</b> {url}",
        styles["body"],
    ))
    return story


# ── Main Entry Point ──────────────────────────────────────────────────────────

def generate_report_pdf(result: dict) -> bytes:
    """
    Generate a professional A4 PDF from the pipeline result dict.
    Returns raw PDF bytes.
    """
    buf = BytesIO()
    styles = _build_styles()

    company    = result.get("company_name") or result.get("ticker", "Unknown")
    ticker     = result.get("ticker", "")
    report_date = date.today().isoformat()

    margin = 15*mm
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=27*mm,    # leave room for the running header band
        bottomMargin=13*mm,
        title=f"{company} ({ticker}) — ScreenerClaw Report",
        author="ScreenerClaw AI",
    )

    page_width = A4[0] - 2 * margin

    raw_data         = result.get("raw_data", {})
    business_analysis = result.get("business_analysis") or {}
    macro_analysis   = result.get("macro_analysis") or {}
    report_outlook   = result.get("report_outlook") or {}
    assumptions      = result.get("assumptions") or {}
    valuations       = result.get("valuations") or {}
    valuation_table  = result.get("valuation_table") or []
    mos_prices       = result.get("mos_prices") or {}
    verdict          = result.get("verdict") or {}
    scoring          = result.get("scoring") or {}
    stock_type       = result.get("stock_type", "")

    story = []

    # ── Key metrics + score (no financial ratios strip — just price/mcap/sector)
    story += _build_key_metrics(raw_data, stock_type, mos_prices, verdict, scoring, styles, page_width)
    story.append(_hr())

    # ── 1. Business Profile
    story += _build_business_section(business_analysis, report_outlook, styles, page_width)
    story.append(_hr())

    # ── 2. Business Outlook (short/medium/long)
    story += _build_outlook_section(report_outlook, styles)
    if (report_outlook or {}).get("outlook"):
        story.append(_hr())

    # ── 3. Macro Analysis
    story += _build_macro_section(macro_analysis, styles, page_width)
    story.append(_hr())

    # ── 4. Valuation — All Methods Summary
    story += _build_valuation_section(assumptions, valuation_table, mos_prices, valuations, styles, page_width)
    story.append(_hr())

    # ── 5a. SOTP Detailed Analysis (conglomerates only)
    sotp_story = _build_sotp_section(valuations, raw_data, styles, page_width)
    if sotp_story:
        story += sotp_story
        story.append(_hr())

    # ── 5b. Greenwald Detailed Analysis (all stock types)
    greenwald_story = _build_greenwald_section(valuations, raw_data, styles, page_width)
    if greenwald_story:
        story += greenwald_story
        story.append(_hr())

    # ── 6. Composite Score Breakdown
    story += _build_score_section(scoring, styles, page_width)
    story.append(_hr())

    # ── 7. Risk Matrix (full — all business + macro risks)
    risk_story = _build_risk_section(business_analysis, macro_analysis, styles, page_width)
    if risk_story:
        story += risk_story
        story.append(_hr())

    # ── 8. Buy Range Tiers
    current_price = float(raw_data.get("current_price") or 0)
    buy_story = _build_buy_ranges(verdict, current_price, styles, page_width)
    if buy_story:
        story += buy_story
        story.append(_hr())

    # ── 9. Screener.in link (replaces financial highlights)
    story += _build_screener_link(raw_data, styles)

    # ── Disclaimer
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "This report is generated by ScreenerClaw AI and is for informational purposes only. "
        "It does not constitute financial advice. Past performance is not indicative of future results. "
        "Assess your own risk tolerance. Capital at risk — conduct your own due diligence.",
        styles["disclaimer"],
    ))

    # Build with running header/footer on every page
    doc.build(
        story,
        onFirstPage=lambda c, d: _on_page(c, d, company, ticker, report_date),
        onLaterPages=lambda c, d: _on_page(c, d, company, ticker, report_date),
    )

    return buf.getvalue()


# ── Screening PDF ─────────────────────────────────────────────────────────────

# Column metadata reused for PDF (mirrors result_formatter.py)
_SCREEN_COL_META: dict[str, tuple[str, int]] = {
    "current_price":     ("CMP Rs",    2),
    "pe":                ("P/E",       1),
    "market_cap":        ("MCap Cr",   0),
    "roce":              ("ROCE%",     1),
    "roe":               ("ROE%",      1),
    "debt_to_equity":    ("D/E",       2),
    "dividend_yield":    ("Div%",      2),
    "pb":                ("P/B",       1),
    "roa":               ("ROA%",      1),
    "sales_qtr":         ("Sales Qtr", 0),
    "profit_qtr":        ("NP Qtr",    0),
    "sales_growth_qtr":  ("SVar%",     1),
    "profit_growth_qtr": ("PVar%",     1),
    "sales_growth_5y":   ("Sal5Y%",    1),
    "profit_growth_5y":  ("Prf5Y%",    1),
    "sales_growth_3y":   ("Sal3Y%",    1),
    "profit_growth_3y":  ("Prf3Y%",    1),
    "return_1y":         ("Ret1Y%",    1),
    "return_3m":         ("Ret3M%",    1),
    "return_6m":         ("Ret6M%",    1),
    "book_value":        ("B.V.",      2),
    "intrinsic_value":   ("IV Rs",     2),
    "piotroski":         ("Pitr",      0),
    "rsi":               ("RSI",       1),
    "dma_50":            ("DMA50",     1),
    "dma_200":           ("DMA200",    1),
    "current_ratio":     ("CurrR",     2),
    "interest_coverage": ("IntCov",    1),
    "promoter_holding":  ("Promo%",    1),
    "pledged_pct":       ("Plg%",      1),
    "fii_holding":       ("FII%",      1),
    "dii_holding":       ("DII%",      1),
    "peg":               ("PEG",       2),
    "fcf":               ("FCF Cr",    0),
    "eps":               ("EPS",       2),
}

_SCREEN_PRIORITY = [
    "current_price", "pe", "market_cap", "roce", "roe", "debt_to_equity",
    "dividend_yield", "pb", "intrinsic_value", "book_value",
    "sales_growth_5y", "profit_growth_5y", "return_1y",
    "promoter_holding", "pledged_pct",
    "sales_qtr", "profit_qtr", "piotroski",
]

_SCREEN_SKIP = frozenset({
    "screener_company_id", "company_name", "ticker", "symbol", "bse_code",
    "score", "verdict", "verdict_emoji",
})


def _screen_col_header(key: str) -> str:
    if key in _SCREEN_COL_META:
        return _SCREEN_COL_META[key][0]
    # Fallback: short-ify the key
    return key.replace("_", " ").title()[:8]


def _screen_col_dec(key: str) -> int:
    return _SCREEN_COL_META.get(key, ("", 1))[1]


def _fv(v: Any, dec: int = 1) -> str:
    """Format numeric value; returns '—' for None."""
    if v is None:
        return "—"
    try:
        f = float(v)
        if dec == 0:
            return f"{f:,.0f}"
        return f"{f:,.{dec}f}"
    except (TypeError, ValueError):
        return str(v)


def _screen_verdict_emoji(verdict: Optional[str]) -> str:
    v = (verdict or "").upper()
    if "STRONG BUY" in v or "BUY" in v:
        return "BUY"
    if "WATCHLIST" in v or "WATCH" in v:
        return "WATCH"
    if "AVOID" in v or "SELL" in v:
        return "AVOID"
    return ""


def _screen_verdict_color(verdict: str) -> Any:
    v = verdict.upper()
    if "BUY" in v:
        return GREEN
    if "WATCH" in v:
        return YELLOW
    if "AVOID" in v or "SELL" in v:
        return RED
    return NAVY


def _on_screen_page(canvas, doc, query: str, report_date: str, total_count: int) -> None:
    """Header/footer for screening PDF pages."""
    W, H = A4
    canvas.saveState()

    # Top band
    canvas.setFillColor(NAVY)
    canvas.rect(0, H - 20*mm, W, 20*mm, fill=1, stroke=0)

    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(15*mm, H - 10*mm, "ScreenerClaw — Screening Results")

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#c8d4e8"))
    canvas.drawRightString(W - 15*mm, H - 10*mm, f"{total_count} results  |  {report_date}")

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#e8edf8"))
    # Truncate query if too long
    q_display = query if len(query) <= 100 else query[:97] + "..."
    canvas.drawString(15*mm, H - 16*mm, f"Query: {q_display}")

    # Orange accent line
    canvas.setFillColor(ORANGE)
    canvas.rect(0, H - 21*mm, W, 1.2*mm, fill=1, stroke=0)

    # Footer
    canvas.setFillColor(colors.HexColor("#f0f3f8"))
    canvas.rect(0, 0, W, 9*mm, fill=1, stroke=0)
    canvas.setFillColor(MID_GRAY)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(15*mm, 3*mm, "Data: Screener.in  |  ScreenerClaw AI  |  Not financial advice")
    canvas.drawRightString(W - 15*mm, 3*mm, f"Page {doc.page}")

    canvas.restoreState()


def generate_screening_pdf(
    results: list[dict],
    query: str,
    total_count: int = 0,
) -> bytes:
    """
    Generate a professional A4 PDF for screening results.
    Shows ALL fetched results (up to 150) with ALL dynamic columns
    present in the data (CMP, P/E, ROCE, IV, B.V., etc.).
    Returns raw PDF bytes.
    """
    from reportlab.lib.pagesizes import A4, landscape

    buf = BytesIO()
    report_date = date.today().isoformat()
    shown_count = total_count or len(results)

    # ── Determine data columns ─────────────────────────────────────────────────
    present: set[str] = set()
    for r in results:
        for k, v in r.items():
            if k not in _SCREEN_SKIP and v is not None:
                present.add(k)

    data_cols: list[str] = []
    for col in _SCREEN_PRIORITY:
        if col in present:
            data_cols.append(col)
            present.discard(col)
    for col in sorted(present):
        data_cols.append(col)

    has_score = any(r.get("score") is not None for r in results)

    # ── Choose orientation based on column count ───────────────────────────────
    # > 9 data cols → landscape; otherwise portrait
    n_data_cols = len(data_cols) + (1 if has_score else 0)
    use_landscape = n_data_cols > 9
    page_size = landscape(A4) if use_landscape else A4
    PW, PH = page_size
    MARGIN = 12*mm
    page_width = PW - 2 * MARGIN

    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=28*mm,
        bottomMargin=16*mm,
    )

    styles = _build_styles()

    # ── Compact table styles for screening ────────────────────────────────────
    base = type(list(styles.values())[0])  # ParagraphStyle class

    th_style = base("sc_th", fontName="Helvetica-Bold", fontSize=6.5,
                    textColor=WHITE, alignment=TA_CENTER, leading=8)
    td_style = base("sc_td", fontName="Helvetica", fontSize=7,
                    textColor=DARK_TEXT, alignment=TA_LEFT, leading=9)
    td_num_style = base("sc_tdn", fontName="Helvetica", fontSize=7,
                        textColor=DARK_TEXT, alignment=TA_RIGHT, leading=9)

    # ── Column width calculation ───────────────────────────────────────────────
    # Fixed cols: # (8mm), Company (42mm), then remaining split evenly
    fixed_w = 8*mm + 42*mm
    n_extra = len(data_cols) + (1 if has_score else 0)
    extra_w = (page_width - fixed_w) / max(n_extra, 1)
    extra_w = max(extra_w, 11*mm)  # minimum 11mm per column

    col_widths = [8*mm, 42*mm] + [extra_w] * n_extra

    # ── Build header row ──────────────────────────────────────────────────────
    header = (
        [Paragraph("#", th_style), Paragraph("Company", th_style)]
        + [Paragraph(_screen_col_header(c), th_style) for c in data_cols]
    )
    if has_score:
        header.append(Paragraph("Score", th_style))

    # ── Build data rows ───────────────────────────────────────────────────────
    table_data = [header]
    for i, r in enumerate(results, 1):
        name = (r.get("company_name") or r.get("ticker") or "?")[:22]
        ticker_sym = r.get("ticker") or r.get("symbol") or ""
        company_str = f"{name}\n({ticker_sym})" if ticker_sym else name

        row = [
            Paragraph(str(i), td_num_style),
            Paragraph(company_str, td_style),
        ]
        for col in data_cols:
            val = r.get(col)
            row.append(Paragraph(_fv(val, _screen_col_dec(col)), td_num_style))

        if has_score:
            score = r.get("score")
            verdict = r.get("verdict", "")
            v_label = _screen_verdict_emoji(verdict)
            v_color = _screen_verdict_color(v_label)
            if score is not None:
                score_para = Paragraph(
                    f"<font color='#{v_color.hexval()[2:]}'>{_fv(score, 0)}</font>"
                    + (f"<br/><font size='5'>{v_label}</font>" if v_label else ""),
                    td_num_style,
                )
            else:
                score_para = Paragraph("—", td_num_style)
            row.append(score_para)

        table_data.append(row)

    # ── TableStyle ────────────────────────────────────────────────────────────
    n_rows = len(table_data)
    tbl_style = TableStyle([
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 6.5),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        # Data rows
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 7),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("ALIGN",         (0, 1), (0, -1), "CENTER"),    # # col
        ("ALIGN",         (1, 1), (1, -1), "LEFT"),      # Company col
        ("ALIGN",         (2, 1), (-1, -1), "RIGHT"),    # data cols right-aligned
        # Grid
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#cdd5e0")),
        ("LINEBELOW",     (0, 0), (-1, 0), 1.0, ORANGE),
        # Padding (compact)
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ])

    tbl = Table(table_data, colWidths=col_widths, style=tbl_style, repeatRows=1)

    # ── Story ─────────────────────────────────────────────────────────────────
    story: list = []

    # Summary box
    story.append(
        Table(
            [[
                Paragraph(f"<b>{shown_count} results</b> matching your query", styles["body"]),
                Paragraph(
                    "Reply with a number (1–20) or company name for full analysis",
                    styles["small"],
                ),
            ]],
            colWidths=[page_width * 0.5, page_width * 0.5],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), SKY),
                ("LEFTPADDING",  (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING",   (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
                ("LINEAFTER",  (0, 0), (0, -1), 2, ORANGE),
                ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ]),
        )
    )
    story.append(Spacer(1, 6))
    story.append(tbl)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Generated by ScreenerClaw AI. Not financial advice. Data sourced from Screener.in.",
        styles["disclaimer"],
    ))

    doc.build(
        story,
        onFirstPage=lambda c, d: _on_screen_page(c, d, query, report_date, shown_count),
        onLaterPages=lambda c, d: _on_screen_page(c, d, query, report_date, shown_count),
    )

    return buf.getvalue()
