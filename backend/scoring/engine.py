"""
ScreenerClaw — Scoring Engine
Provides intent-based weight helpers and a screening-specific quick scorer.

score_for_screening() only uses columns actually present in Screener filter results
(CMP, P/E, ROCE, ROE, D/E, Div%, MCap, Sales/Profit Qtr growth, Piotroski, etc.)
instead of the full pipeline RankingAgent which needs LLM analysis & valuation tables.
"""
from __future__ import annotations

from typing import Any, Optional

from backend.config import INTENT_SCORE_WEIGHTS, DEFAULT_SCORE_WEIGHTS


def get_weights_for_intent(intent: str) -> dict:
    """Return scoring weights for a given investment intent."""
    return INTENT_SCORE_WEIGHTS.get(intent.lower(), DEFAULT_SCORE_WEIGHTS).copy()


# ── Helper ────────────────────────────────────────────────────────────────────

def _safe(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Component scorers (screening-specific) ───────────────────────────────────

def _score_quality(d: dict) -> Optional[float]:
    """Business quality from ROCE, ROE, OPM."""
    parts, n = 0.0, 0

    roce = _safe(d.get("roce"))
    if roce is not None:
        if roce >= 30:   parts += 100
        elif roce >= 22: parts += 85
        elif roce >= 15: parts += 65
        elif roce >= 10: parts += 45
        else:            parts += 20
        n += 1

    roe = _safe(d.get("roe"))
    if roe is not None:
        if roe >= 25:    parts += 100
        elif roe >= 18:  parts += 85
        elif roe >= 12:  parts += 65
        elif roe >= 8:   parts += 45
        else:            parts += 20
        n += 1

    opm = _safe(d.get("opm"))
    if opm is not None:
        if opm >= 25:    parts += 100
        elif opm >= 15:  parts += 80
        elif opm >= 10:  parts += 60
        elif opm >= 5:   parts += 40
        else:            parts += 15
        n += 1

    return (parts / n) if n else None


def _score_valuation(d: dict) -> Optional[float]:
    """Valuation from P/E vs industry context."""
    pe = _safe(d.get("pe"))
    pb = _safe(d.get("pb"))
    parts, n = 0.0, 0

    if pe is not None and pe > 0:
        if pe < 8:       parts += 95
        elif pe < 12:    parts += 85
        elif pe < 18:    parts += 70
        elif pe < 25:    parts += 55
        elif pe < 35:    parts += 40
        elif pe < 50:    parts += 25
        else:            parts += 10
        n += 1

    if pb is not None and pb > 0:
        if pb < 1:       parts += 95
        elif pb < 2:     parts += 80
        elif pb < 3:     parts += 65
        elif pb < 5:     parts += 50
        else:            parts += 30
        n += 1

    # Intrinsic value vs CMP
    iv = _safe(d.get("intrinsic_value"))
    cmp = _safe(d.get("current_price"))
    if iv and cmp and iv > 0 and cmp > 0:
        margin = (iv - cmp) / iv * 100
        if margin >= 40:   parts += 100
        elif margin >= 25: parts += 85
        elif margin >= 10: parts += 70
        elif margin >= 0:  parts += 55
        elif margin >= -15: parts += 35
        else:              parts += 15
        n += 1

    # Book value vs CMP (P/B implied)
    bv = _safe(d.get("book_value"))
    if bv and cmp and bv > 0 and cmp > 0 and pb is None:  # avoid double-counting pb
        pb_implied = cmp / bv
        if pb_implied < 1:   parts += 95
        elif pb_implied < 2: parts += 80
        elif pb_implied < 3: parts += 65
        elif pb_implied < 5: parts += 50
        else:                parts += 30
        n += 1

    return (parts / n) if n else None


def _score_growth(d: dict) -> Optional[float]:
    """Growth from qtr profit/sales growth, 3Y/5Y growth rates."""
    parts, n = 0.0, 0

    def _growth_score(g: Optional[float]) -> float:
        if g is None:
            return 50.0
        if g >= 25:   return 100
        if g >= 18:   return 88
        if g >= 12:   return 75
        if g >= 8:    return 62
        if g >= 3:    return 50
        if g >= 0:    return 38
        return 20   # negative growth

    # Quarterly growth (most recent)
    pg = _safe(d.get("profit_growth_qtr"))
    sg = _safe(d.get("sales_growth_qtr"))
    if pg is not None:
        parts += _growth_score(pg)
        n += 1
    if sg is not None:
        parts += _growth_score(sg)
        n += 1

    # Multi-year growth rates
    for field in ("profit_growth_5y", "profit_growth_3y", "sales_growth_5y", "sales_growth_3y"):
        v = _safe(d.get(field))
        if v is not None:
            parts += _growth_score(v)
            n += 1
            break  # use the first available multi-year metric only

    return (parts / n) if n else None


def _score_health(d: dict) -> Optional[float]:
    """Financial health from D/E, interest coverage, current ratio."""
    parts, n = 0.0, 0

    de = _safe(d.get("debt_to_equity"))
    if de is not None:
        if de <= 0.05:   parts += 100   # net cash / debt-free
        elif de <= 0.3:  parts += 90
        elif de <= 0.5:  parts += 78
        elif de <= 1.0:  parts += 60
        elif de <= 1.5:  parts += 40
        else:            parts += 15
        n += 1

    ic = _safe(d.get("interest_coverage"))
    if ic is not None:
        if ic >= 15:     parts += 100
        elif ic >= 8:    parts += 85
        elif ic >= 5:    parts += 70
        elif ic >= 3:    parts += 50
        elif ic >= 1:    parts += 25
        else:            parts += 5
        n += 1

    cr = _safe(d.get("current_ratio"))
    if cr is not None:
        if cr >= 2.5:    parts += 100
        elif cr >= 1.8:  parts += 85
        elif cr >= 1.3:  parts += 70
        elif cr >= 1.0:  parts += 50
        else:            parts += 20
        n += 1

    return (parts / n) if n else None


def _score_dividend_income(d: dict) -> Optional[float]:
    """Dividend yield attractiveness."""
    dy = _safe(d.get("dividend_yield"))
    if dy is None:
        return None
    if dy >= 4:      return 100
    if dy >= 3:      return 85
    if dy >= 2:      return 70
    if dy >= 1:      return 55
    if dy > 0:       return 40
    return 30  # 0% yield — not necessarily bad


def _score_momentum(d: dict) -> Optional[float]:
    """Price momentum from 1Y/6M/3M returns and RSI."""
    parts, n = 0.0, 0

    def _ret_score(r: Optional[float]) -> Optional[float]:
        if r is None:
            return None
        if r >= 50:   return 100
        if r >= 30:   return 85
        if r >= 15:   return 70
        if r >= 5:    return 55
        if r >= -5:   return 45
        if r >= -20:  return 30
        return 15

    for field in ("return_1y", "return_6m", "return_3m"):
        s = _ret_score(_safe(d.get(field)))
        if s is not None:
            parts += s
            n += 1

    rsi = _safe(d.get("rsi"))
    if rsi is not None:
        # Sweet spot 40-60 is neutral; >70 overbought; <30 oversold (potential reversal)
        if 40 <= rsi <= 60:   parts += 70
        elif 60 < rsi <= 70:  parts += 60
        elif rsi > 70:        parts += 40
        elif 30 <= rsi < 40:  parts += 75   # slightly oversold = opportunity
        else:                 parts += 80   # very oversold
        n += 1

    return (parts / n) if n else None


def _score_governance(d: dict) -> Optional[float]:
    """Promoter holding and pledge quality."""
    parts, n = 0.0, 0

    ph = _safe(d.get("promoter_holding"))
    if ph is not None:
        if ph >= 60:   parts += 90
        elif ph >= 50: parts += 80
        elif ph >= 40: parts += 65
        elif ph >= 25: parts += 50
        else:          parts += 30
        n += 1

    plg = _safe(d.get("pledged_pct"))
    if plg is not None:
        if plg <= 0:    parts += 100
        elif plg <= 5:  parts += 85
        elif plg <= 15: parts += 60
        elif plg <= 30: parts += 35
        else:           parts += 10
        n += 1

    return (parts / n) if n else None


# ── Intent weight maps for screening ─────────────────────────────────────────
# Maps (quality, valuation, growth, health, dividend, momentum, governance) → weights

_SCREENING_WEIGHTS: dict[str, dict[str, float]] = {
    "default": {
        "quality": 0.30, "valuation": 0.25, "growth": 0.20,
        "health": 0.15, "dividend": 0.00, "momentum": 0.05, "governance": 0.05,
    },
    "quality": {
        "quality": 0.45, "valuation": 0.15, "growth": 0.20,
        "health": 0.10, "dividend": 0.00, "momentum": 0.05, "governance": 0.05,
    },
    "value": {
        "quality": 0.25, "valuation": 0.40, "growth": 0.15,
        "health": 0.10, "dividend": 0.05, "momentum": 0.00, "governance": 0.05,
    },
    "undervalued": {
        "quality": 0.25, "valuation": 0.40, "growth": 0.15,
        "health": 0.10, "dividend": 0.05, "momentum": 0.00, "governance": 0.05,
    },
    "growth": {
        "quality": 0.25, "valuation": 0.15, "growth": 0.40,
        "health": 0.10, "dividend": 0.00, "momentum": 0.05, "governance": 0.05,
    },
    "dividend": {
        "quality": 0.20, "valuation": 0.20, "growth": 0.10,
        "health": 0.15, "dividend": 0.30, "momentum": 0.00, "governance": 0.05,
    },
    "momentum": {
        "quality": 0.20, "valuation": 0.10, "growth": 0.25,
        "health": 0.10, "dividend": 0.00, "momentum": 0.30, "governance": 0.05,
    },
    "compounder": {
        "quality": 0.35, "valuation": 0.15, "growth": 0.30,
        "health": 0.10, "dividend": 0.00, "momentum": 0.05, "governance": 0.05,
    },
}

_VERDICT_MAP = [
    (78, "STRONG BUY", "🟢"),
    (62, "BUY",        "🔵"),
    (50, "WATCHLIST",  "🟡"),
    (38, "NEUTRAL",    "⚪"),
    (0,  "AVOID",      "🔴"),
]


def score_for_screening(
    raw_data: dict,
    intent: str = "default",
) -> dict[str, Any]:
    """
    Quick scoring for screening results using only available filter columns.
    Components where no data is present are excluded from the weighted average
    rather than defaulting to 50 — giving differentiated, meaningful scores.
    """
    w = _SCREENING_WEIGHTS.get(intent.lower(), _SCREENING_WEIGHTS["default"])

    scorers = {
        "quality":    _score_quality(raw_data),
        "valuation":  _score_valuation(raw_data),
        "growth":     _score_growth(raw_data),
        "health":     _score_health(raw_data),
        "dividend":   _score_dividend_income(raw_data),
        "momentum":   _score_momentum(raw_data),
        "governance": _score_governance(raw_data),
    }

    # Only include components that have data
    total_w = 0.0
    weighted_sum = 0.0
    component_scores = {}

    for comp, s in scorers.items():
        if s is not None:
            wt = w.get(comp, 0.0)
            weighted_sum += s * wt
            total_w += wt
            component_scores[comp] = round(s, 1)

    if total_w == 0:
        composite = 50.0
    else:
        # Rescale so weights always sum to 1 (even if some components missing)
        composite = weighted_sum / total_w

    composite = round(composite, 1)

    verdict, emoji = "NEUTRAL", "⚪"
    for threshold, v, e in _VERDICT_MAP:
        if composite >= threshold:
            verdict, emoji = v, e
            break

    return {
        "composite_score": composite,
        "verdict":         verdict,
        "verdict_emoji":   emoji,
        "component_scores": component_scores,
    }
