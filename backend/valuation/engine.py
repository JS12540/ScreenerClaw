"""
Valuation Engine — Phases 4 & 5
Implements all 7 valuation methods:
  1. Graham Number
  2. Graham Valuation Formula
  3. PEG Ratio
  4. DCF (Discounted Cash Flow)
  5. DDM (Dividend Discount Model)
  6. Greenwald EPV (Earnings Power Value)
  7. Greenwald Growth Value

All monetary values in INR. Rates in percent (e.g. 12 means 12%).
"""
from __future__ import annotations

import math
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

TERMINAL_GROWTH_RATE = 4.0   # % — conservative for India
MAX_TV_NPV_RATIO = 0.60      # flag if terminal value > 60% of total NPV


class ValuationEngine:

    def compute(
        self,
        raw_data: dict,
        assumptions: dict,
    ) -> dict[str, Any]:
        """
        Run all applicable valuation methods.
        Returns dict keyed by method name with results.
        """
        price = raw_data.get("current_price") or 0
        eps_reported = raw_data.get("eps_ttm") or 0
        bv = raw_data.get("book_value") or 0

        ne = assumptions.get("normalized_eps", {})
        norm_eps = ne.get("value") or eps_reported or 0

        nr = assumptions.get("normalized_roce", {})
        norm_roce = nr.get("value") or raw_data.get("roce") or 15

        gs = assumptions.get("growth_scenarios", {})
        g_bear = gs.get("bear", {}).get("g", 6)
        g_base = gs.get("base", {}).get("g", 12)
        g_bull = gs.get("bull", {}).get("g", 18)

        r_val = assumptions.get("required_return_r", {}).get("value", 12)
        y_val = assumptions.get("risk_free_rate_y", 7)

        shares_cr = assumptions.get("shares_outstanding_cr") or (
            (raw_data.get("market_cap") or 0) / price if price else 0
        )

        capital_per_share = assumptions.get("capital_invested_per_share") or bv or 0
        total_capital_cr = capital_per_share * shares_cr if shares_cr else 0

        dps = assumptions.get("dps_latest") or 0
        payout_pct = assumptions.get("dividend_payout_pct") or 0

        # Operating CF & Capex for DCF
        ops_cf_avg = assumptions.get("operating_cf_avg_3yr") or 0
        capex_avg = assumptions.get("capex_avg_3yr") or 0

        # If not provided in assumptions, compute from raw data
        if not ops_cf_avg:
            ops_cf_avg = self._avg_cf(raw_data.get("cash_flow", {}).get("operating", []))
        if not capex_avg:
            inv_cf = raw_data.get("cash_flow", {}).get("investing", [])
            capex_avg = abs(self._avg_cf(inv_cf) or 0)

        fcf_avg = ops_cf_avg - capex_avg

        applicable = assumptions.get("valuation_methods_applicable", {})

        results: dict[str, Any] = {}

        # ── 1. Graham Number ─────────────────────────────────────────────────
        if applicable.get("graham_number", True) and bv > 0:
            results["graham_number"] = self._graham_number(
                eps_reported=eps_reported,
                norm_eps=norm_eps,
                book_value=bv,
            )
        else:
            results["graham_number"] = {"applicable": False, "reason": "EPS ≤ 0 or BV ≤ 0"}

        # ── 2. Graham Formula ────────────────────────────────────────────────
        if applicable.get("graham_formula", True) and norm_eps > 0:
            results["graham_formula"] = self._graham_formula(
                norm_eps=norm_eps,
                g_bear=g_bear,
                g_base=g_base,
                g_bull=g_bull,
                y=y_val,
                r=r_val,
            )
        else:
            results["graham_formula"] = {"applicable": False, "reason": "Normalized EPS ≤ 0"}

        # ── 3. PEG ───────────────────────────────────────────────────────────
        if applicable.get("peg", True) and norm_eps > 0:
            results["peg"] = self._peg(
                norm_eps=norm_eps,
                g_base=g_base,
                current_pe=raw_data.get("pe") or 0,
            )
        else:
            results["peg"] = {"applicable": False, "reason": "Normalized EPS ≤ 0"}

        # ── 4. DCF ───────────────────────────────────────────────────────────
        if applicable.get("dcf", True):
            results["dcf"] = self._dcf(
                fcf_avg_cr=fcf_avg,
                g_bear=g_bear,
                g_base=g_base,
                g_bull=g_bull,
                r=r_val,
                shares_cr=shares_cr,
            )
        else:
            results["dcf"] = {"applicable": False, "reason": "N/A"}

        # ── 5. DDM ───────────────────────────────────────────────────────────
        if applicable.get("ddm", False) and dps > 0 and payout_pct > 20:
            results["ddm"] = self._ddm(
                dps=dps,
                g_base=g_base,
                g_bull=g_bull,
                r=r_val,
            )
        else:
            results["ddm"] = {
                "applicable": False,
                "reason": "Dividend payout < 20% or no dividend",
            }

        # ── 6. Greenwald EPV ─────────────────────────────────────────────────
        if applicable.get("greenwald_epv", True) and norm_eps > 0 and shares_cr > 0:
            results["greenwald_epv"] = self._epv(
                norm_eps_total_cr=norm_eps * shares_cr,
                shares_cr=shares_cr,
            )
        else:
            results["greenwald_epv"] = {"applicable": False, "reason": "EPS ≤ 0 or shares = 0"}

        # ── 7. Greenwald Growth Value ────────────────────────────────────────
        if applicable.get("greenwald_growth", True) and total_capital_cr > 0 and shares_cr > 0:
            results["greenwald_growth"] = self._greenwald_growth(
                total_capital_cr=total_capital_cr,
                roc=norm_roce,
                g_bear=g_bear,
                g_base=g_base,
                g_bull=g_bull,
                r=r_val,
                shares_cr=shares_cr,
            )
        else:
            results["greenwald_growth"] = {"applicable": False, "reason": "Capital = 0 or shares = 0"}

        return results

    # ─── Method 1: Graham Number ───────────────────────────────────────────────

    def _graham_number(
        self, eps_reported: float, norm_eps: float, book_value: float
    ) -> dict:
        """√(22.5 × EPS × BV_per_share)"""
        results = {}

        for label, eps in [("reported", eps_reported), ("normalized", norm_eps)]:
            if eps > 0 and book_value > 0:
                val = math.sqrt(22.5 * eps * book_value)
                results[label] = round(val, 2)
            else:
                results[label] = None

        results["formula"] = "√(22.5 × EPS × Book Value)"
        results["applicable"] = True
        return results

    # ─── Method 2: Graham Valuation Formula ───────────────────────────────────

    def _graham_formula(
        self,
        norm_eps: float,
        g_bear: float,
        g_base: float,
        g_bull: float,
        y: float,
        r: float,
    ) -> dict:
        """V = EPS × (8.5 + 2G) × (Y / R)
        G, Y, R are ALL as numbers (not decimals): e.g. G=12, Y=7, R=12"""
        def compute(g: float) -> Optional[float]:
            if r <= 0:
                return None
            v = norm_eps * (8.5 + 2 * g) * (y / r)
            return round(max(v, 0), 2)

        return {
            "formula": "EPS × (8.5 + 2×G) × (Y/R)",
            "norm_eps": norm_eps,
            "y": y,
            "r": r,
            "bear": compute(g_bear),
            "base": compute(g_base),
            "bull": compute(g_bull),
            "applicable": True,
        }

    # ─── Method 3: PEG ────────────────────────────────────────────────────────

    def _peg(self, norm_eps: float, g_base: float, current_pe: float) -> dict:
        """Fair P/E = G%; Fair Price = EPS × G%"""
        fair_pe = g_base  # e.g. 15 → P/E of 15x
        fair_price = round(norm_eps * fair_pe, 2) if norm_eps and fair_pe else None

        # Current PEG ratio
        current_peg = None
        if current_pe and g_base and g_base > 0:
            current_peg = round(current_pe / g_base, 2)

        interpretation = "N/A"
        if current_peg is not None:
            if current_peg < 1:
                interpretation = "Undervalued (PEG < 1)"
            elif current_peg < 2:
                interpretation = "Fair Value (PEG 1-2)"
            else:
                interpretation = "Overvalued (PEG > 2)"

        return {
            "formula": "Fair P/E = G%; Fair Price = Normalized EPS × G%",
            "fair_pe": fair_pe,
            "fair_price": fair_price,
            "current_peg": current_peg,
            "interpretation": interpretation,
            "applicable": True,
        }

    # ─── Method 4: DCF ────────────────────────────────────────────────────────

    def _dcf(
        self,
        fcf_avg_cr: float,
        g_bear: float,
        g_base: float,
        g_bull: float,
        r: float,
        shares_cr: float,
    ) -> dict:
        """
        Two-stage DCF.
        Stage 1 (Y1-5): grow at g_stage1 (bear/base/bull)
        Stage 2 (Y6-10): grow at g_stage1 / 2
        Terminal Value: FCF_10 × (1 + terminal_g) / (r - terminal_g)
        """
        terminal_g = TERMINAL_GROWTH_RATE

        def compute_scenario(g1_pct: float) -> dict:
            if r <= terminal_g:
                return {"value_per_share": None, "error": "R ≤ terminal growth rate"}

            r_dec = r / 100
            g1_dec = g1_pct / 100
            g2_dec = (g1_pct / 2) / 100
            tg_dec = terminal_g / 100

            fcf = fcf_avg_cr
            npv = 0.0
            fcf_by_year = []

            for yr in range(1, 11):
                if yr <= 5:
                    fcf = fcf * (1 + g1_dec)
                else:
                    fcf = fcf * (1 + g2_dec)
                pv = fcf / (1 + r_dec) ** yr
                npv += pv
                fcf_by_year.append(round(fcf, 2))

            fcf_year10 = fcf
            terminal_value = fcf_year10 * (1 + tg_dec) / (r_dec - tg_dec)
            pv_terminal = terminal_value / (1 + r_dec) ** 10
            total_npv = npv + pv_terminal

            tv_ratio = pv_terminal / total_npv if total_npv else 0
            flag_tv = tv_ratio > MAX_TV_NPV_RATIO

            # Both total_npv and shares_cr are in Crores → per share in INR
            per_share = (total_npv / shares_cr) if shares_cr else None

            return {
                "total_npv_cr": round(total_npv, 2),
                "terminal_value_cr": round(terminal_value, 2),
                "pv_terminal_cr": round(pv_terminal, 2),
                "tv_pct_of_total": round(tv_ratio * 100, 1),
                "flag_high_terminal_value": flag_tv,
                "value_per_share": round(per_share, 2) if per_share else None,
            }

        if fcf_avg_cr <= 0:
            return {
                "applicable": False,
                "reason": f"FCF is negative or zero (avg 3yr FCF = {fcf_avg_cr:.0f} Cr)",
                "fcf_avg_3yr_cr": fcf_avg_cr,
            }

        return {
            "formula": "NPV of FCF over 10yr + Terminal Value",
            "fcf_avg_3yr_cr": round(fcf_avg_cr, 2),
            "terminal_growth_rate_pct": terminal_g,
            "r_pct": r,
            "bear": compute_scenario(g_bear),
            "base": compute_scenario(g_base),
            "bull": compute_scenario(g_bull),
            "applicable": True,
        }

    # ─── Method 5: DDM ────────────────────────────────────────────────────────

    def _ddm(
        self,
        dps: float,
        g_base: float,
        g_bull: float,
        r: float,
    ) -> dict:
        """Gordon Growth Model: P = D1 / (R - G)"""
        def compute(g_pct: float) -> Optional[float]:
            r_dec = r / 100
            g_dec = g_pct / 100
            if r_dec <= g_dec:
                return None  # Formula breaks down
            d1 = dps * (1 + g_dec)
            return round(d1 / (r_dec - g_dec), 2)

        return {
            "formula": "P = D1 / (R - G), D1 = DPS × (1 + G)",
            "dps": dps,
            "base": compute(g_base),
            "bull": compute(g_bull),
            "applicable": True,
        }

    # ─── Method 6: Greenwald EPV ──────────────────────────────────────────────

    def _epv(self, norm_eps_total_cr: float, shares_cr: float) -> dict:
        """EPV = Normalized Earnings / R"""
        def per_share(r_pct: float) -> Optional[float]:
            if r_pct <= 0 or shares_cr <= 0:
                return None
            epv_total = norm_eps_total_cr / (r_pct / 100)
            # epv_total is in Crores, shares_cr is in Crores → result in INR per share
            return round(epv_total / shares_cr, 2)

        return {
            "formula": "EPV = Normalized Net Profit / R",
            "norm_earnings_total_cr": round(norm_eps_total_cr, 2),
            "r10_value_per_share": per_share(10),
            "r12_value_per_share": per_share(12),
            "applicable": True,
        }

    # ─── Method 7: Greenwald Growth Value ─────────────────────────────────────

    def _greenwald_growth(
        self,
        total_capital_cr: float,
        roc: float,
        g_bear: float,
        g_base: float,
        g_bull: float,
        r: float,
        shares_cr: float,
    ) -> dict:
        """PV = Capital × (ROC - G) / (R - G)
        ROC, G, R all in % (e.g. 20, 12, 12)"""
        growth_creates_value = roc > r

        def compute(g_pct: float, r_pct: float) -> Optional[float]:
            if r_pct <= g_pct:
                return None  # formula breaks down when G >= R
            if shares_cr <= 0:
                return None
            pv_total = total_capital_cr * (roc - g_pct) / (r_pct - g_pct)
            if pv_total < 0:
                return None  # Nonsensical result
            # pv_total in Crores, shares_cr in Crores → per share in INR
            return round(pv_total / shares_cr, 2)

        # Compute EPV separately for PV/EPV ratio
        epv_total = total_capital_cr * roc / r if r > 0 else None

        scenarios = {}
        for label, g in [("bear_r12", g_bear), ("base_r12", g_base), ("bull_r12", g_bull), ("stretch_r12", 10)]:
            scenarios[label] = compute(g, r)

        # Also optional at r=10%
        for label, g in [("bear_r10", g_bear), ("base_r10", g_base), ("bull_r10", g_bull)]:
            scenarios[label] = compute(g, 10)

        # PV/EPV ratio (growth premium) for base case
        pv_base_total = total_capital_cr * (roc - g_base) / (r - g_base) if r != g_base else None
        pv_epv_ratio = None
        if pv_base_total and epv_total and epv_total != 0:
            pv_epv_ratio = round(pv_base_total / epv_total, 2)

        return {
            "formula": "PV = Capital × (ROC - G) / (R - G)",
            "total_capital_cr": round(total_capital_cr, 2),
            "roc_pct": roc,
            "r_pct": r,
            "growth_creates_value": growth_creates_value,
            "warning": None if growth_creates_value else f"⚠️ ROC ({roc}%) < R ({r}%) — growth DESTROYS value",
            "pv_epv_ratio": pv_epv_ratio,
            **scenarios,
            "applicable": True,
        }

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _avg_cf(cf_list: list) -> float:
        """Average of last 3 years of cash flow."""
        vals = []
        for item in cf_list[-3:]:
            if isinstance(item, dict) and item.get("value") is not None:
                vals.append(item["value"])
        return sum(vals) / len(vals) if vals else 0

    # ─── Phase 5: Combined Valuation Table ────────────────────────────────────

    def build_table(
        self, valuations: dict, current_price: float
    ) -> list[dict]:
        """
        Build combined valuation table (Phase 5).
        Returns list of rows for display.
        """
        rows = []

        def mos(value: Optional[float]) -> Optional[float]:
            if value is None or current_price <= 0:
                return None
            return round((value - current_price) / value * 100, 1)

        def row(method: str, assumption: str, value: Optional[float]) -> dict:
            vs = None
            if value and current_price:
                pct = (value - current_price) / current_price * 100
                vs = f"{'above' if pct > 0 else 'below'} by {abs(pct):.0f}%"
            return {
                "method": method,
                "assumption": assumption,
                "value_per_share": round(value, 0) if value else None,
                "vs_market": vs,
                "mos_pct": mos(value),
            }

        # Graham Number
        gn = valuations.get("graham_number", {})
        if gn.get("applicable") is not False:
            rows.append(row("Graham Number", "Reported EPS", gn.get("reported")))
            rows.append(row("Graham Number", "Normalized EPS", gn.get("normalized")))

        # Graham Formula
        gf = valuations.get("graham_formula", {})
        if gf.get("applicable") is not False:
            rows.append(row("Graham Formula (Bear)", "G=Bear", gf.get("bear")))
            rows.append(row("Graham Formula (Base)", "G=Base", gf.get("base")))
            rows.append(row("Graham Formula (Bull)", "G=Bull", gf.get("bull")))

        # PEG
        pg = valuations.get("peg", {})
        if pg.get("applicable") is not False:
            rows.append(row("PEG Ratio", f"G=Base", pg.get("fair_price")))

        # DCF
        dcf = valuations.get("dcf", {})
        if dcf.get("applicable") is not False:
            rows.append(row("DCF (Bear)", "Stage1=Bear, Stage2=Bear/2", dcf.get("bear", {}).get("value_per_share")))
            rows.append(row("DCF (Base)", "Stage1=Base, Stage2=Base/2", dcf.get("base", {}).get("value_per_share")))
            rows.append(row("DCF (Bull)", "Stage1=Bull, Stage2=Bull/2", dcf.get("bull", {}).get("value_per_share")))

        # DDM
        ddm = valuations.get("ddm", {})
        if ddm.get("applicable") is not False:
            rows.append(row("DDM (Base)", "Gordon Growth", ddm.get("base")))
            rows.append(row("DDM (Bull)", "Gordon Growth", ddm.get("bull")))

        # EPV
        epv = valuations.get("greenwald_epv", {})
        if epv.get("applicable") is not False:
            rows.append(row("EPV (R=10%)", "No growth premium", epv.get("r10_value_per_share")))
            rows.append(row("EPV (R=12%)", "No growth premium", epv.get("r12_value_per_share")))

        # Greenwald Growth
        gg = valuations.get("greenwald_growth", {})
        if gg.get("applicable") is not False:
            rows.append(row("Greenwald Growth (Bear)", "G=Bear, R=12%", gg.get("bear_r12")))
            rows.append(row("Greenwald Growth (Base)", "G=Base, R=12%", gg.get("base_r12")))
            rows.append(row("Greenwald Growth (Bull)", "G=Bull, R=12%", gg.get("bull_r12")))

        return rows
