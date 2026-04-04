"""
ScreenerClaw — Valuation Engine (Step 4)
Implements 9 valuation methods.
Selects 4-5 appropriate methods based on stock type.

Registry:
  1. dcf_eps          — Two-stage EPS DCF (GuruFocus style)
  2. dcf_fcf          — Two-stage Free Cash Flow DCF
  3. graham_formula   — EPS × (8.5 + 2G) × 4.4/AAA_yield
  4. pe_based         — PE vs sector median, own 5/10yr average
  5. epv              — Earnings Power Value (Greenwald)
  6. ddm              — Gordon Growth Model for dividend stocks
  7. reverse_dcf      — What EPS CAGR does today's price imply?
  8. greenwald_growth — Greenwald EPV + Growth (quality/growth stocks)
  9. sotp             — Sum of Parts (CONGLOMERATE type only)
"""
from __future__ import annotations

import math
from typing import Any, Optional

from backend.config import INDIA_PARAMS
from backend.logger import get_logger

logger = get_logger(__name__)


class ValuationEngine:

    # ── SOTP: Analyst-validated EV/EBITDA multiples by segment type ──────────
    # Sources: Emkay Sep-2025, Citi Dec-2025, Morgan Stanley India reports
    SOTP_MULTIPLES: dict[str, float] = {
        "telecom":         13.0,   # Jio-type, Citi Dec-2025 uses 14x FY27
        "digital":         13.0,
        "retail":          28.0,   # Organised retail, Emkay 28x
        "o2c":             7.5,    # Oil-to-Chemicals, Emkay 7.5x Sep'27E
        "refining":        7.5,
        "petrochemicals":  7.5,
        "oil_gas":         6.5,    # Upstream E&P
        "upstream":        6.5,
        "renewable":       12.0,   # New energy / green
        "energy":          12.0,
        "financial":       None,   # Use P/B instead (handled separately)
        "nbfc":            None,
        "it":              14.0,   # IT services
        "technology":      14.0,
        "fmcg":            18.0,
        "consumer":        18.0,
        "auto":            14.0,
        "automotive":      14.0,
        "infrastructure":  10.0,
        "ports":           10.0,
        "media":           10.0,
        "cement":          9.0,
        "generic":         9.0,    # Unknown segment — conservative
    }

    CONGLOMERATE_DISCOUNT = 0.15  # 15% holding company discount (analyst consensus)

    def compute(
        self,
        raw_data: dict,
        assumptions: dict,
        methods: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Run applicable valuation methods.
        If methods is None, runs all methods that have sufficient data.
        Returns dict keyed by method name.
        """
        price = float(raw_data.get("current_price") or 0)
        eps_rep = float(raw_data.get("eps_ttm") or 0)
        bv = float(raw_data.get("book_value") or 0)
        opm = float(raw_data.get("opm") or 0)
        pe_current = float(raw_data.get("pe") or 0)

        # From assumptions agent
        ne = assumptions.get("normalized_eps", {})
        norm_eps = float(ne.get("value") or eps_rep or 0)

        nr = assumptions.get("normalized_roce", {})
        norm_roce = float(nr.get("value") or raw_data.get("roce") or 15)

        gs = assumptions.get("growth_scenarios", {})
        g_bear = float(gs.get("bear", {}).get("g", 6))
        g_base = float(gs.get("base", {}).get("g", 12))
        g_bull = float(gs.get("bull", {}).get("g", 18))

        r_val = float(assumptions.get("required_return_r", {}).get("value", 13))
        y_val = float(INDIA_PARAMS["risk_free_rate"] * 100)  # as %
        aaa_yield = float(INDIA_PARAMS["aaa_bond_yield"] * 100)

        dps = float(assumptions.get("dps_latest") or 0)
        shares_cr = float(assumptions.get("shares_outstanding_cr") or 0)
        if not shares_cr and price and raw_data.get("market_cap"):
            shares_cr = float(raw_data["market_cap"]) / price

        capital_per_share = float(assumptions.get("capital_invested_per_share") or bv or 0)
        total_capital_cr = capital_per_share * shares_cr if shares_cr else 0

        # Cash flow
        cf = raw_data.get("cash_flow", {})
        ops_cf_avg = float(assumptions.get("operating_cf_avg_3yr") or self._avg_cf(cf.get("operating", [])))
        capex_avg = float(assumptions.get("capex_avg_3yr") or abs(self._avg_cf(cf.get("investing", [])) or 0))
        fcf_avg = ops_cf_avg - capex_avg
        net_debt = float(raw_data.get("net_debt") or 0)

        applic = assumptions.get("valuation_methods_applicable", {})
        if methods is None:
            methods = list(applic.keys()) or [
                "dcf_eps", "dcf_fcf", "graham_formula",
                "pe_based", "epv", "ddm", "reverse_dcf",
            ]

        results: dict[str, Any] = {}

        # ── 1. DCF EPS (GuruFocus / Two-stage EPS) ────────────────────────────
        if "dcf_eps" in methods and norm_eps > 0 and shares_cr > 0:
            results["dcf_eps"] = self._dcf_eps(
                norm_eps=norm_eps, g_bear=g_bear, g_base=g_base, g_bull=g_bull,
                r=r_val, shares_cr=shares_cr,
            )

        # ── 2. DCF FCF ────────────────────────────────────────────────────────
        if "dcf_fcf" in methods:
            results["dcf_fcf"] = self._dcf_fcf(
                fcf_avg_cr=fcf_avg, g_bear=g_bear, g_base=g_base, g_bull=g_bull,
                r=r_val, shares_cr=shares_cr,
            )

        # ── 3. Graham Formula ─────────────────────────────────────────────────
        if "graham_formula" in methods and norm_eps > 0:
            results["graham_formula"] = self._graham_formula(
                norm_eps=norm_eps, g_bear=g_bear, g_base=g_base, g_bull=g_bull,
                y=y_val, aaa_yield=aaa_yield,
            )
        elif "graham_formula" in methods:
            results["graham_formula"] = {"applicable": False, "reason": "EPS ≤ 0"}

        # ── 5. PE-based ────────────────────────────────────────────────────────
        if "pe_based" in methods and norm_eps > 0:
            results["pe_based"] = self._pe_based(
                norm_eps=norm_eps, pe_current=pe_current,
                g_bear=g_bear, g_base=g_base, g_bull=g_bull,
            )

        # ── 6. EPV (Greenwald Earnings Power Value) ────────────────────────────
        if "epv" in methods and norm_eps > 0 and shares_cr > 0:
            results["epv"] = self._epv(
                norm_eps_total_cr=norm_eps * shares_cr, r=r_val, shares_cr=shares_cr,
            )

        # ── 6. DDM ─────────────────────────────────────────────────────────────
        if "ddm" in methods and dps > 0:
            results["ddm"] = self._ddm(dps=dps, g_base=g_base, g_bull=g_bull, r=r_val)
        elif "ddm" in methods:
            results["ddm"] = {"applicable": False, "reason": "No dividend"}

        # ── 7. Reverse DCF ────────────────────────────────────────────────────
        if "reverse_dcf" in methods and norm_eps > 0 and price > 0:
            results["reverse_dcf"] = self._reverse_dcf(
                price=price, norm_eps=norm_eps, r=r_val, shares_cr=shares_cr,
                actual_5yr_cagr=g_base,
            )

        # ── 8. Greenwald EPV + Growth ─────────────────────────────────────────
        if norm_eps > 0 and norm_roce > 0 and capital_per_share > 0 and shares_cr > 0:
            results["greenwald_growth"] = self._greenwald(
                norm_eps=norm_eps,
                norm_roce=norm_roce,
                capital_per_share=capital_per_share,
                shares_cr=shares_cr,
                r=r_val,
            )

        # ── 9. SOTP — Sum of Parts (conglomerates only) ───────────────────────
        if "sotp" in methods:
            sotp_segments = assumptions.get("sotp_segments") or raw_data.get("sotp_segments")
            if sotp_segments and isinstance(sotp_segments, list) and len(sotp_segments) >= 2:
                results["sotp"] = self._sotp(
                    segments=sotp_segments,
                    net_debt=net_debt,
                    shares_cr=shares_cr,
                    price=price,
                )

        results.setdefault("dcf", results.get("dcf_fcf"))

        return results

    # ── Method 1: Two-Stage EPS DCF ───────────────────────────────────────────

    def _dcf_eps(
        self, norm_eps: float, g_bear: float, g_base: float, g_bull: float,
        r: float, shares_cr: float,
    ) -> dict:
        """Two-stage EPS-based DCF (GuruFocus / Buffett-style).
        Stage 1: 10yr at scenario growth rate
        Stage 2: 10yr at terminal growth (6% nominal)
        Discount at WACC."""
        terminal_g = INDIA_PARAMS["terminal_growth_nominal"] * 100  # 6%

        def compute(g1_pct: float) -> dict:
            if r <= terminal_g:
                return {"value_per_share": None, "error": "WACC ≤ terminal growth"}
            r_d = r / 100
            g1_d = g1_pct / 100
            tg_d = terminal_g / 100

            eps = norm_eps
            npv = 0.0
            for yr in range(1, 21):
                if yr <= 10:
                    eps = eps * (1 + g1_d)
                else:
                    eps = eps * (1 + tg_d)
                pv = eps / (1 + r_d) ** yr
                npv += pv

            tv = eps * (1 + tg_d) / (r_d - tg_d)
            pv_tv = tv / (1 + r_d) ** 20
            total = npv + pv_tv

            return {
                "value_per_share": round(total, 2),
                "tv_pct_of_total": round(pv_tv / total * 100, 1) if total else 0,
            }

        return {
            "method": "Two-Stage EPS DCF",
            "formula": "Sum of PV(EPS yr1-20) + TV",
            "stage1_years": 10, "stage2_years": 10,
            "terminal_growth_pct": terminal_g,
            "discount_rate_pct": r,
            "bear": compute(g_bear),
            "base": compute(g_base),
            "bull": compute(g_bull),
            "applicable": True,
        }

    # ── Method 2: FCF DCF ─────────────────────────────────────────────────────

    def _dcf_fcf(
        self, fcf_avg_cr: float, g_bear: float, g_base: float, g_bull: float,
        r: float, shares_cr: float,
    ) -> dict:
        if fcf_avg_cr <= 0:
            return {
                "applicable": False,
                "reason": f"FCF is negative (avg 3yr = {fcf_avg_cr:.0f} Cr)",
                "fcf_avg_cr": round(fcf_avg_cr, 2),
            }
        terminal_g = INDIA_PARAMS["terminal_growth_nominal"] * 100

        def compute(g1_pct: float) -> dict:
            if r <= terminal_g:
                return {"value_per_share": None, "error": "WACC ≤ terminal growth"}
            r_d, g1_d, tg_d = r / 100, g1_pct / 100, terminal_g / 100
            fcf = fcf_avg_cr
            npv = 0.0
            for yr in range(1, 11):
                g = g1_d if yr <= 5 else (g1_pct / 2) / 100
                fcf = fcf * (1 + g)
                npv += fcf / (1 + r_d) ** yr

            tv = fcf * (1 + tg_d) / (r_d - tg_d)
            pv_tv = tv / (1 + r_d) ** 10
            total = npv + pv_tv
            per_share = total / shares_cr if shares_cr else None

            return {
                "total_npv_cr": round(total, 2),
                "value_per_share": round(per_share, 2) if per_share else None,
                "tv_pct_of_total": round(pv_tv / total * 100, 1) if total else 0,
            }

        return {
            "method": "FCF DCF",
            "formula": "NPV of FCF 10yr + TV",
            "fcf_avg_3yr_cr": round(fcf_avg_cr, 2),
            "terminal_growth_pct": terminal_g,
            "r_pct": r,
            "bear": compute(g_bear),
            "base": compute(g_base),
            "bull": compute(g_bull),
            "applicable": True,
        }

    # ── Method 3: Graham Formula ──────────────────────────────────────────────

    def _graham_formula(
        self, norm_eps: float, g_bear: float, g_base: float, g_bull: float,
        y: float, aaa_yield: float,
    ) -> dict:
        def compute(g: float) -> Optional[float]:
            if aaa_yield <= 0:
                return None
            # Original Graham: V = EPS × (8.5 + 2G) × 4.4 / AAA_bond_yield
            return round(max(norm_eps * (8.5 + 2 * g) * 4.4 / aaa_yield, 0), 2)

        return {
            "method": "Graham Formula",
            "formula": "EPS × (8.5 + 2G) × 4.4 / AAA_yield",
            "norm_eps": norm_eps, "y": y, "aaa_yield": aaa_yield,
            "bear": compute(g_bear), "base": compute(g_base), "bull": compute(g_bull),
            "applicable": True,
        }

    # ── Method 5: PE-Based ────────────────────────────────────────────────────

    def _pe_based(
        self, norm_eps: float, pe_current: float,
        g_bear: float, g_base: float, g_bull: float,
    ) -> dict:
        # Graham's "fair PE" = 15x for no-growth, + growth premium
        graham_pe = 15
        growth_pe_base = min(graham_pe + g_base * 0.5, 40)  # cap at 40x
        growth_pe_bear = min(graham_pe + g_bear * 0.5, 35)
        growth_pe_bull = min(graham_pe + g_bull * 0.5, 45)

        current_peg = (pe_current / g_base) if (pe_current and g_base) else None

        return {
            "method": "PE-Based",
            "norm_eps": norm_eps,
            "pe_current": pe_current,
            "graham_fair_pe": graham_pe,
            "implied_pe_bear": round(growth_pe_bear, 1),
            "implied_pe_base": round(growth_pe_base, 1),
            "implied_pe_bull": round(growth_pe_bull, 1),
            "bear": round(norm_eps * growth_pe_bear, 2),
            "base": round(norm_eps * growth_pe_base, 2),
            "bull": round(norm_eps * growth_pe_bull, 2),
            "current_peg": round(current_peg, 2) if current_peg else None,
            "peg_interpretation": (
                "Undervalued (PEG < 1)" if current_peg and current_peg < 1 else
                "Fair value (PEG 1-2)" if current_peg and current_peg < 2 else
                "Overvalued (PEG > 2)" if current_peg else "N/A"
            ),
            "applicable": True,
        }

    # ── Method 6: EPV ─────────────────────────────────────────────────────────

    def _epv(self, norm_eps_total_cr: float, r: float, shares_cr: float) -> dict:
        def per_share(r_pct: float) -> Optional[float]:
            if r_pct <= 0 or shares_cr <= 0:
                return None
            return round(norm_eps_total_cr / (r_pct / 100) / shares_cr, 2)

        return {
            "method": "Earnings Power Value",
            "formula": "EPV = Normalized Earnings / R",
            "norm_earnings_cr": round(norm_eps_total_cr, 2),
            "r10_value": per_share(10),
            "r12_value": per_share(12),
            "r13_value": per_share(13),
            "base": per_share(r),
            "applicable": True,
        }

    # ── Method 6: DDM ─────────────────────────────────────────────────────────

    def _ddm(self, dps: float, g_base: float, g_bull: float, r: float) -> dict:
        def compute(g_pct: float) -> Optional[float]:
            r_d, g_d = r / 100, g_pct / 100
            if r_d <= g_d:
                return None
            return round(dps * (1 + g_d) / (r_d - g_d), 2)

        return {
            "method": "DDM — Gordon Growth",
            "formula": "D1 / (R - G)",
            "dps": dps,
            "base": compute(g_base),
            "bull": compute(g_bull),
            "applicable": True,
        }

    # ── Method 7: Reverse DCF ────────────────────────────────────────────────

    def _reverse_dcf(
        self, price: float, norm_eps: float, r: float,
        shares_cr: float, actual_5yr_cagr: float,
    ) -> dict:
        """Solve for the EPS growth rate that justifies today's price."""
        terminal_g = INDIA_PARAMS["terminal_growth_nominal"] * 100
        r_d = r / 100
        tg_d = terminal_g / 100

        implied_g = None
        # Binary search for implied CAGR
        lo, hi = 0.0, 50.0
        for _ in range(50):
            mid = (lo + hi) / 2
            g_d = mid / 100
            eps = norm_eps
            npv = 0.0
            for yr in range(1, 21):
                if yr <= 10:
                    eps = eps * (1 + g_d)
                else:
                    eps = eps * (1 + tg_d)
                npv += eps / (1 + r_d) ** yr
            tv = eps * (1 + tg_d) / (r_d - tg_d) / (1 + r_d) ** 20
            model_price = npv + tv

            if abs(model_price - price) < 0.1:
                implied_g = mid
                break
            if model_price < price:
                lo = mid
            else:
                hi = mid
        else:
            implied_g = lo

        implied_g = round(implied_g, 1) if implied_g is not None else None

        verdict = "N/A"
        if implied_g is not None:
            if implied_g < actual_5yr_cagr * 0.7:
                verdict = "Opportunity — market is pricing in much less growth than history suggests"
            elif implied_g > actual_5yr_cagr * 1.3:
                verdict = "Risky — market is pricing in acceleration beyond historical growth"
            else:
                verdict = "Fair — market is pricing in growth in line with historical trajectory"

        return {
            "method": "Reverse DCF",
            "formula": "Solve for G that makes DCF = current price",
            "current_price": price,
            "implied_eps_cagr_pct": implied_g,
            "actual_5yr_eps_cagr_pct": round(actual_5yr_cagr, 1),
            "verdict": verdict,
            "applicable": True,
        }

    # ── Method 8: Greenwald EPV + Growth Valuation ────────────────────────────

    def _greenwald(
        self,
        norm_eps: float,
        norm_roce: float,
        capital_per_share: float,
        shares_cr: float,
        r: float,
    ) -> dict:
        """
        Greenwald Earnings Power Value + Growth Valuation.

        Step 1: Capital Invested
            Capital = Book Value per share × Shares outstanding
            Total Earnings = EPS × Shares

        Step 2: No-Growth EPV
            EPV = Normalized Earnings / R
            Computed for R = 10% and R = 12%

        Step 3: Greenwald Growth Formula
            PV = Capital × (ROC − G) / (R − G)
            For R=12%, G = 4%, 6%, 8%, 10%
            Also compute PV / EPV ratio (growth premium multiple)

        Step 4: Interpretation
            ROC > R  → growth CREATES value (higher G = higher IV)
            ROC < R  → growth DESTROYS value (EPV is the ceiling, not the floor)
        """
        if shares_cr <= 0 or capital_per_share <= 0:
            return {"applicable": False, "reason": "Insufficient capital/shares data"}

        roc = norm_roce / 100
        r_d = r / 100
        total_earnings_cr = norm_eps * shares_cr
        total_capital_cr  = capital_per_share * shares_cr

        # ── EPV (no-growth) ───────────────────────────────────────────────────
        def epv(rate_pct: float) -> dict:
            rate = rate_pct / 100
            total = total_earnings_cr / rate if rate > 0 else None
            per_share = total / shares_cr if (total and shares_cr) else None
            return {
                "r_pct": rate_pct,
                "total_cr": round(total, 2) if total else None,
                "per_share": round(per_share, 2) if per_share else None,
            }

        epv_r10 = epv(10)
        epv_r12 = epv(12)
        epv_base = epv(r)

        # ── Growth scenarios ──────────────────────────────────────────────────
        growth_scenarios: dict = {}
        epv_r12_ps = epv_r12["per_share"]

        for g_pct in (4, 6, 8, 10):
            g_d = g_pct / 100
            key = f"g{g_pct}"
            if r_d <= g_d:
                growth_scenarios[key] = {
                    "g_pct": g_pct,
                    "value_per_share": None,
                    "error": "G ≥ R — formula undefined (terminal growth ≥ discount rate)",
                }
                continue
            # PV = Capital × (ROC − G) / (R − G)
            pv_total = total_capital_cr * (roc - g_d) / (r_d - g_d)
            pv_per_share = pv_total / shares_cr
            pv_epv_ratio = (pv_per_share / epv_r12_ps) if (epv_r12_ps and epv_r12_ps > 0) else None
            growth_scenarios[key] = {
                "g_pct": g_pct,
                "pv_total_cr": round(pv_total, 2),
                "value_per_share": round(pv_per_share, 2),
                "pv_epv_ratio": round(pv_epv_ratio, 2) if pv_epv_ratio else None,
            }

        # ── Interpretation ────────────────────────────────────────────────────
        creates_value = roc > r_d
        if creates_value:
            interp = (
                f"ROC ({norm_roce:.1f}%) > Required Return ({r:.1f}%) → "
                f"Growth CREATES value. Every rupee reinvested earns above your hurdle rate. "
                f"Higher growth = meaningfully higher intrinsic value. "
                f"Pay attention to G=6–8% scenarios as the realistic range."
            )
        else:
            interp = (
                f"ROC ({norm_roce:.1f}%) < Required Return ({r:.1f}%) → "
                f"Growth DESTROYS shareholder value. Capital deployed earns below required returns. "
                f"The EPV (no-growth value) is the CEILING, not the floor. "
                f"A 'growth' story here is actually a value trap — demand a larger discount."
            )

        return {
            "method": "Greenwald EPV + Growth",
            "formula": "EPV = Earnings/R  |  PV = Capital × (ROC−G) / (R−G)",
            "applicable": True,
            # Inputs
            "norm_eps": norm_eps,
            "norm_roce_pct": norm_roce,
            "capital_per_share": capital_per_share,
            "total_capital_cr": round(total_capital_cr, 2),
            "total_earnings_cr": round(total_earnings_cr, 2),
            "shares_cr": round(shares_cr, 2),
            # Step 2: EPV
            "epv_r10": epv_r10,
            "epv_r12": epv_r12,
            "epv_base": epv_base,
            # Step 3: Growth
            "growth_scenarios": growth_scenarios,
            # Step 4: Interpretation
            "roc_vs_r": "creates_value" if creates_value else "destroys_value",
            "interpretation": interp,
        }

    # ── Method 13: Sum of Parts (SOTP) — Conglomerates only ──────────────────

    def _sotp(
        self,
        segments: list[dict],
        net_debt: float,
        shares_cr: float,
        price: float,
    ) -> dict:
        """
        Sum-of-Parts valuation for conglomerates.

        Each segment dict should have:
          - name: str
          - segment_type: str  (e.g. "telecom", "retail", "o2c")
          - ebitda_cr: float   (segment EBITDA in Rs crore, annual)
          - revenue_cr: float  (optional, for loss-making segments)
          - book_value_cr: float (optional, for financial segments)
          - stake_pct: float   (parent's ownership %, default 100)
          - note: str          (optional analyst note)

        Returns complete SOTP breakdown with per-share values.
        """
        if shares_cr <= 0:
            return {"error": "No shares data for SOTP"}

        segment_results = []
        total_ev_cr = 0.0
        warnings = []

        for seg in segments:
            seg_name = seg.get("name", "Unknown")
            seg_type = (seg.get("segment_type") or "generic").lower()
            ebitda = float(seg.get("ebitda_cr") or 0)
            revenue = float(seg.get("revenue_cr") or 0)
            bv_cr = float(seg.get("book_value_cr") or 0)
            stake = float(seg.get("stake_pct") or 100) / 100.0

            # Resolve multiple (fuzzy match on segment_type)
            multiple = None
            for key, val in self.SOTP_MULTIPLES.items():
                if key in seg_type:
                    multiple = val
                    break
            if multiple is None:
                multiple = self.SOTP_MULTIPLES["generic"]

            seg_ev_cr = 0.0
            method_used = ""

            if seg_type in ("financial", "nbfc", "bank", "insurance") and bv_cr > 0:
                # Financial segments: use P/B 2.0x on book value
                seg_ev_cr = bv_cr * 2.0
                method_used = f"P/B 2.0x on Rs{bv_cr:,.0f} Cr book value"
            elif ebitda > 0 and multiple is not None:
                seg_ev_cr = ebitda * multiple
                method_used = f"{multiple:.1f}x EV/EBITDA on Rs{ebitda:,.0f} Cr EBITDA"
            elif revenue > 0:
                # Loss-making: use 0.5x Revenue (very conservative)
                seg_ev_cr = revenue * 0.5
                method_used = f"0.5x Revenue (loss-making) on Rs{revenue:,.0f} Cr revenue"
                warnings.append(f"{seg_name}: loss-making, assigned 0.5x revenue — upside if profitable")
            else:
                warnings.append(f"{seg_name}: no data, assigned Rs0")
                seg_ev_cr = 0.0
                method_used = "No data — Rs0 assigned"

            attributable_ev = seg_ev_cr * stake
            per_share = (attributable_ev / shares_cr) if shares_cr > 0 else 0

            segment_results.append({
                "segment": seg_name,
                "type": seg_type,
                "stake_pct": round(stake * 100, 1),
                "ebitda_cr": ebitda if ebitda > 0 else None,
                "multiple": multiple,
                "gross_ev_cr": round(seg_ev_cr, 0),
                "attributable_ev_cr": round(attributable_ev, 0),
                "per_share": round(per_share, 0),
                "method": method_used,
            })
            total_ev_cr += attributable_ev

        # Apply conglomerate/holding company discount
        sotp_ev_pre_discount = total_ev_cr
        sotp_ev_post_discount = total_ev_cr * (1 - self.CONGLOMERATE_DISCOUNT)

        # Equity value = EV - Net Debt
        equity_value_cr = sotp_ev_post_discount - net_debt
        sotp_per_share = equity_value_cr / shares_cr if shares_cr > 0 else 0

        # Upside/downside vs current price
        upside_pct = ((sotp_per_share - price) / price * 100) if price > 0 else None

        return {
            "method": "SOTP — Sum of Parts",
            "formula": "Sigma(Segment EV x Stake%) x (1 - HoldCo Discount%) - Net Debt",
            "segments": segment_results,
            "total_ev_pre_discount_cr": round(sotp_ev_pre_discount, 0),
            "holdco_discount_pct": round(self.CONGLOMERATE_DISCOUNT * 100, 0),
            "total_ev_post_discount_cr": round(sotp_ev_post_discount, 0),
            "net_debt_cr": round(net_debt, 0),
            "equity_value_cr": round(equity_value_cr, 0),
            "bear": round(sotp_per_share * 0.85, 0),
            "base": round(sotp_per_share, 0),
            "bull": round(sotp_per_share * 1.15, 0),
            "upside_pct": round(upside_pct, 1) if upside_pct is not None else None,
            "warnings": warnings,
            "note": (
                f"SOTP across {len(segment_results)} segments. "
                f"{self.CONGLOMERATE_DISCOUNT*100:.0f}% holding company discount applied. "
                "Multiples based on analyst consensus (Emkay/Citi/Morgan Stanley)."
            ),
        }

    # ── Build Comparison Table ────────────────────────────────────────────────

    def build_table(self, valuations: dict, current_price: float) -> list[dict]:
        """Build the valuation comparison table shown in the report."""
        rows = []

        def mos(value: Optional[float]) -> Optional[float]:
            if value is None or current_price <= 0:
                return None
            return round((value - current_price) / value * 100, 1)

        def vs_market(value: Optional[float]) -> Optional[str]:
            if not value or not current_price:
                return None
            pct = (value - current_price) / current_price * 100
            direction = "above" if pct > 0 else "below"
            return f"{direction} by {abs(pct):.0f}%"

        def row(method: str, scenario: str, value: Optional[float]) -> dict:
            return {
                "method": method,
                "scenario": scenario,
                "value_per_share": round(value, 0) if value else None,
                "vs_market": vs_market(value),
                "mos_pct": mos(value),
            }

        # DCF EPS
        d = valuations.get("dcf_eps", {})
        if d.get("applicable") is not False:
            for s in ("bear", "base", "bull"):
                v = (d.get(s) or {}).get("value_per_share")
                if v:
                    rows.append(row(f"DCF-EPS ({s.title()})", f"EPS DCF G={s}", v))

        # DCF FCF
        d = valuations.get("dcf_fcf", {})
        if d and d.get("applicable") is not False:
            for s in ("bear", "base", "bull"):
                v = (d.get(s) or {}).get("value_per_share")
                if v:
                    rows.append(row(f"DCF-FCF ({s.title()})", f"FCF DCF G={s}", v))

        # Graham Formula
        gf = valuations.get("graham_formula", {})
        if gf.get("applicable") is not False:
            for s in ("bear", "base", "bull"):
                if gf.get(s):
                    rows.append(row(f"Graham Formula ({s.title()})", f"G={s}", gf[s]))

        # PE-based
        pe = valuations.get("pe_based", {})
        if pe.get("applicable") is not False:
            for s in ("bear", "base", "bull"):
                if pe.get(s):
                    rows.append(row(f"PE-Based ({s.title()})", f"PE×EPS G={s}", pe[s]))

        # EPV
        epv = valuations.get("epv", {})
        if epv.get("applicable") is not False:
            if epv.get("r13_value"):
                rows.append(row("EPV (R=13%)", "Zero-growth earnings value", epv["r13_value"]))

        # Greenwald
        gw = valuations.get("greenwald_growth", {})
        if gw and gw.get("applicable") is not False:
            epv_r10 = gw.get("epv_r10", {})
            epv_r12 = gw.get("epv_r12", {})
            if epv_r10.get("per_share"):
                rows.append(row("Greenwald EPV (R=10%)", "No-growth value", epv_r10["per_share"]))
            if epv_r12.get("per_share"):
                rows.append(row("Greenwald EPV (R=12%)", "No-growth value", epv_r12["per_share"]))
            for g_key in ("g4", "g6", "g8"):
                gs_data = gw.get("growth_scenarios", {}).get(g_key, {})
                v = gs_data.get("value_per_share")
                if v:
                    rows.append(row(
                        f"Greenwald Growth (G={gs_data['g_pct']}%)",
                        f"PV=Capital×(ROC−G)/(R−G)",
                        v,
                    ))

        # DDM
        ddm = valuations.get("ddm", {})
        if ddm and ddm.get("applicable") is not False:
            if ddm.get("base"):
                rows.append(row("DDM (Base)", "Gordon Growth", ddm["base"]))

        return rows

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _avg_cf(cf_list: list) -> float:
        vals = []
        for item in cf_list[-3:]:
            if isinstance(item, dict) and item.get("value") is not None:
                try:
                    vals.append(float(item["value"]))
                except (TypeError, ValueError):
                    pass
        return sum(vals) / len(vals) if vals else 0.0
