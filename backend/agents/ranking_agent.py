"""
ScreenerClaw — Ranking & Scoring Agent (Step 5)
Combines backward-looking financials + forward-looking estimates
into a composite score and verdict.

Score Components:
  business_quality  25%  ROCE, ROE, OPM trend, FCF conversion
  growth_past       20%  Revenue CAGR 3/5yr, EPS CAGR, consistency
  growth_forward    20%  Estimated EPS CAGR 3yr, macro tailwind
  valuation         15%  PE vs 5yr avg, MOS gap, reverse DCF implied
  financial_health  10%  D/E, interest coverage, CFO/PAT
  business_outlook  10%  Moat trajectory, management quality
"""
from __future__ import annotations

import time
from typing import Any, Optional

from backend.logger import get_logger

logger = get_logger(__name__)


class RankingAgent:
    """
    Step 5 of the 5-step pipeline.
    Computes a composite 0-100 score and investment verdict.
    """

    def __init__(self) -> None:
        pass

    def score(
        self,
        raw_data: dict,
        business_analysis: dict,
        macro_analysis: dict,
        valuation_table: list[dict],
        outlook: dict,
        weights: Optional[dict] = None,
    ) -> dict[str, Any]:
        from backend.config import DEFAULT_SCORE_WEIGHTS, SCORE_VERDICT

        w = weights or DEFAULT_SCORE_WEIGHTS.copy()

        # Individual component scores (0-100 each)
        bq = self._score_business_quality(raw_data)
        gp = self._score_growth_past(raw_data)
        gf = self._score_growth_forward(macro_analysis, outlook)
        vs = self._score_valuation(raw_data, valuation_table)
        fh = self._score_financial_health(raw_data)
        bo = self._score_business_outlook(business_analysis, macro_analysis)

        components = {
            "business_quality": round(bq, 1),
            "growth_past":      round(gp, 1),
            "growth_forward":   round(gf, 1),
            "valuation":        round(vs, 1),
            "financial_health": round(fh, 1),
            "business_outlook": round(bo, 1),
        }

        # Weighted composite
        composite = sum(components[k] * w[k] for k in components)
        composite = round(composite, 1)

        # Verdict
        verdict, emoji = self._get_verdict(composite)

        return {
            "composite_score": composite,
            "verdict": verdict,
            "verdict_emoji": emoji,
            "component_scores": components,
            "weights_used": w,
            "score_breakdown": self._build_breakdown(components, w),
        }

    # ── Component Scorers ─────────────────────────────────────────────────────

    def _score_business_quality(self, raw_data: dict) -> float:
        score = 0.0
        count = 0

        # ROCE
        roce = raw_data.get("roce")
        if roce is not None:
            if roce >= 25:   score += 100
            elif roce >= 20: score += 85
            elif roce >= 15: score += 70
            elif roce >= 10: score += 50
            else:            score += 20
            count += 1

        # ROE
        roe = raw_data.get("roe")
        if roe is not None:
            if roe >= 20:    score += 100
            elif roe >= 15:  score += 80
            elif roe >= 10:  score += 60
            else:            score += 30
            count += 1

        # OPM (operating profit margin)
        opm = raw_data.get("opm")
        if opm is not None:
            if opm >= 25:    score += 100
            elif opm >= 15:  score += 80
            elif opm >= 10:  score += 60
            elif opm >= 5:   score += 40
            else:            score += 15
            count += 1

        # Profit consistency
        pl_np = [x for x in raw_data.get("pl_net_profit", []) if isinstance(x, dict)]
        if len(pl_np) >= 5:
            positives = sum(1 for x in pl_np[-5:] if (x.get("value") or 0) > 0)
            consistency_pct = (positives / 5) * 100
            score += consistency_pct
            count += 1

        return (score / count) if count else 50.0

    def _score_growth_past(self, raw_data: dict) -> float:
        score = 0.0
        count = 0

        def _cagr_score(cagr_pct: Optional[float]) -> float:
            if cagr_pct is None:
                return 50.0
            if cagr_pct >= 20:   return 100
            if cagr_pct >= 15:   return 85
            if cagr_pct >= 12:   return 70
            if cagr_pct >= 8:    return 55
            if cagr_pct >= 5:    return 40
            if cagr_pct >= 0:    return 25
            return 10  # negative growth

        sc = raw_data.get("sales_growth_cagr", {})
        pc = raw_data.get("profit_growth_cagr", {})

        for key in ("5_years", "5yr"):
            v = sc.get(key)
            if v is not None:
                score += _cagr_score(float(v))
                count += 1
                break

        for key in ("5_years", "5yr"):
            v = pc.get(key)
            if v is not None:
                score += _cagr_score(float(v))
                count += 1
                break

        # EPS CAGR from ratios if available
        ratios = raw_data.get("ratios", {})
        eps_list = ratios.get("eps", [])
        if len(eps_list) >= 5:
            try:
                start = float(eps_list[-5].get("value") or 0)
                end = float(eps_list[-1].get("value") or 0)
                if start > 0 and end > 0:
                    eps_cagr = ((end / start) ** (1 / 4) - 1) * 100
                    score += _cagr_score(eps_cagr)
                    count += 1
            except Exception:
                pass

        return (score / count) if count else 50.0

    def _score_growth_forward(self, macro_analysis: dict, outlook: dict) -> float:
        score = 50.0  # default neutral

        # Macro tailwind score
        macro_score = macro_analysis.get("macro_score", 50) if macro_analysis else 50
        score = macro_score * 0.4  # macro contributes 40%

        # Outlook EPS growth
        short = (outlook or {}).get("short_term", {})
        med = (outlook or {}).get("medium_term", {})

        # EPS estimates from short-term outlook
        base_eps = short.get("eps_estimate_base")
        if base_eps:
            score += 30  # has forward estimates = positive signal

        # Moat trajectory from medium term
        moat_traj = med.get("moat_trajectory", "stable")
        moat_scores = {"strengthening": 100, "stable": 70, "eroding": 30, "unclear": 50}
        score += moat_scores.get(moat_traj, 50) * 0.3

        return min(100, max(0, score))

    def _score_valuation(self, raw_data: dict, valuation_table: list[dict]) -> float:
        if not valuation_table:
            return 50.0

        current_price = raw_data.get("current_price") or 0
        if not current_price:
            return 50.0

        # Average MOS from valuation table (positive MOS = undervalued)
        mos_values = [
            r.get("mos_pct") for r in valuation_table
            if r.get("mos_pct") is not None
        ]
        if not mos_values:
            return 50.0

        avg_mos = sum(mos_values) / len(mos_values)

        # MOS > 25% = very undervalued (score 90)
        # MOS 10-25% = moderately undervalued (score 70)
        # MOS -10% to 10% = fairly valued (score 50)
        # MOS < -10% = overvalued (score 30)
        # MOS < -30% = very overvalued (score 10)

        if avg_mos >= 30:    return 95
        if avg_mos >= 20:    return 80
        if avg_mos >= 10:    return 65
        if avg_mos >= 0:     return 50
        if avg_mos >= -15:   return 35
        if avg_mos >= -30:   return 20
        return 10

    def _score_financial_health(self, raw_data: dict) -> float:
        score = 0.0
        count = 0

        # Debt to equity
        de = raw_data.get("debt_to_equity")
        if de is not None:
            if de <= 0.3:    score += 100
            elif de <= 0.5:  score += 85
            elif de <= 1.0:  score += 65
            elif de <= 1.5:  score += 40
            else:            score += 15
            count += 1

        # Interest coverage from ratios
        ratios = raw_data.get("ratios", {})
        ic_list = ratios.get("interest_coverage", [])
        if ic_list:
            try:
                ic = float(ic_list[-1].get("value") or 0)
                if ic >= 10:     score += 100
                elif ic >= 5:    score += 80
                elif ic >= 3:    score += 60
                elif ic >= 1:    score += 35
                else:            score += 10
                count += 1
            except Exception:
                pass

        # CFO / PAT quality check
        cf = raw_data.get("cash_flow", {})
        ops_list = cf.get("operating", [])
        pl_np = raw_data.get("pl_net_profit", [])
        if ops_list and pl_np:
            try:
                ops_avg = sum(x.get("value", 0) for x in ops_list[-3:]) / 3
                pat_avg = sum(x.get("value", 0) for x in pl_np[-3:]) / 3
                if pat_avg > 0:
                    ratio = ops_avg / pat_avg
                    if ratio >= 1.0:     score += 100
                    elif ratio >= 0.8:   score += 80
                    elif ratio >= 0.5:   score += 50
                    else:                score += 20
                    count += 1
            except Exception:
                pass

        return (score / count) if count else 50.0

    def _score_business_outlook(self, business_analysis: dict, macro_analysis: dict) -> float:
        score = 50.0

        biz = business_analysis or {}
        moat = biz.get("moat_analysis", {})
        if moat:
            advantages = moat.get("advantages", [])
            strong = sum(1 for a in advantages if a.get("strength") in ("strong", "moderate"))
            score = min(100, 40 + strong * 20)

        # Macro boost/penalty
        macro_verdict = (macro_analysis or {}).get("net_macro_verdict", "NEUTRAL")
        adjustments = {"POSITIVE": 15, "NEUTRAL": 0, "NEGATIVE": -15}
        score += adjustments.get(macro_verdict, 0)

        return min(100, max(0, score))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_verdict(self, score: float) -> tuple[str, str]:
        from backend.config import SCORE_VERDICT

        for threshold in sorted(SCORE_VERDICT.keys(), reverse=True):
            if score >= threshold:
                return SCORE_VERDICT[threshold]
        return SCORE_VERDICT[0]

    def _build_breakdown(self, components: dict, weights: dict) -> list[dict]:
        rows = []
        for key, score in components.items():
            weight = weights.get(key, 0)
            contribution = score * weight
            rows.append({
                "component": key.replace("_", " ").title(),
                "score": score,
                "weight_pct": round(weight * 100, 0),
                "contribution": round(contribution, 1),
            })
        rows.sort(key=lambda r: r["contribution"], reverse=True)
        return rows
