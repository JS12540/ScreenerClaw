"""
ScreenerClaw — Stock Type Classifier
Classifies a stock into its type and returns the appropriate
valuation methods to use.
"""
from __future__ import annotations

from backend.config import STOCK_TYPES, VALUATION_METHODS_BY_TYPE


def classify_stock_type(raw_data: dict) -> str:
    """
    Classify a stock into one of the defined stock types.
    Returns one of: QUALITY_COMPOUNDER | CYCLICAL | FINANCIAL | INFRASTRUCTURE
                    REAL_ASSET | GROWTH | DIVIDEND_YIELD | CONGLOMERATE | UNKNOWN
    """
    sector = raw_data.get("sector", "")
    industry = raw_data.get("industry", "")
    combined = f"{sector} {industry}".lower()

    # ── Conglomerate detection (must run before sector loop) ─────────────────
    # Indicators: multiple diverse segments, "diversified" in sector/industry,
    # or large-cap with explicitly diverse business description
    about = (raw_data.get("about") or "").lower()
    conglomerate_keywords = [
        "conglomerate", "diversified", "holding company", "multiple segments",
        "across sectors", "group company",
    ]
    # Also detect by peer segments — if company has 3+ completely different sector peers
    sector_lower = sector.lower()
    industry_lower = industry.lower()
    if any(kw in sector_lower or kw in industry_lower or kw in about[:300] for kw in conglomerate_keywords):
        return "CONGLOMERATE"

    # Also flag known Indian conglomerates by ticker
    known_conglomerates = {
        "RELIANCE", "TATAMOTORS", "TATAPOWER", "TATACHEMICALS", "TATACONSUM",
        "M&M", "BAJAJFINSV", "ADANIENT", "ADANIPORTS", "ITC", "LTIM",
        "GODREJCP", "GODREJPROP", "MAHINDRA", "HINDUNILVR",
        # Holding companies
        "BAJAJHOLD", "TATAINVEST", "KAMA", "PILANIINVST",
    }
    symbol = (raw_data.get("symbol") or "").upper()
    if symbol in known_conglomerates:
        return "CONGLOMERATE"

    # Check each type's sector list
    for stock_type, sectors in STOCK_TYPES.items():
        for s in sectors:
            if s.lower() in combined or s.lower() in sector.lower():
                return stock_type

    # Heuristic fallbacks
    pe = raw_data.get("pe") or 0
    roce = raw_data.get("roce") or 0
    de = raw_data.get("debt_to_equity") or 0
    div_yield = raw_data.get("dividend_yield") or 0

    # Financial companies: high leverage is normal
    if de > 5:
        return "FINANCIAL"

    # Growth: very high PE, low dividend
    if pe and float(pe) > 60 and div_yield < 0.5:
        return "GROWTH"

    # Dividend yield: high yield + low growth
    if div_yield and float(div_yield) > 3:
        return "DIVIDEND_YIELD"

    # Quality compounder: high ROCE + moderate PE
    if roce and float(roce) > 20:
        return "QUALITY_COMPOUNDER"

    # Cyclical: commodity sectors
    cyclical_keywords = ["metal", "mining", "cement", "steel", "aluminium", "commodity"]
    if any(k in combined for k in cyclical_keywords):
        return "CYCLICAL"

    # Real asset: real estate / construction / hospitality keywords
    real_asset_keywords = [
        "real estate", "realty", "construction", "housing", "developer",
        "property", "hospitality", "hotel", "resort", "media",
    ]
    if any(k in combined for k in real_asset_keywords):
        return "REAL_ASSET"

    # Infrastructure keywords not caught by sector list
    infra_keywords = ["infrastructure", "power", "road", "highway", "port", "airport", "railway", "defence"]
    if any(k in combined for k in infra_keywords):
        return "INFRASTRUCTURE"

    return "UNKNOWN"


def get_valuation_methods(stock_type: str) -> list[str]:
    """Return list of valuation method names to use for this stock type."""
    return VALUATION_METHODS_BY_TYPE.get(stock_type, VALUATION_METHODS_BY_TYPE["UNKNOWN"])


def get_margin_of_safety(stock_type: str, sector: str) -> float:
    """Return appropriate margin of safety percentage for this stock type."""
    from backend.config import INDIA_PARAMS

    sector_mos = INDIA_PARAMS["sector_margin_of_safety"]

    # Try sector-specific first
    for sector_key, mos in sector_mos.items():
        if sector_key.lower() in sector.lower():
            return mos

    # Type-based defaults
    type_defaults = {
        "QUALITY_COMPOUNDER": 0.25,
        "CYCLICAL":           0.35,
        "FINANCIAL":          0.25,
        "INFRASTRUCTURE":     0.30,
        "REAL_ASSET":         0.30,
        "GROWTH":             0.45,
        "DIVIDEND_YIELD":     0.20,
        "CONGLOMERATE":       0.20,
        "UNKNOWN":            0.25,
    }
    return type_defaults.get(stock_type, 0.25)


def get_wacc(stock_type: str, sector: str) -> float:
    """Return appropriate WACC for this stock type and sector."""
    from backend.config import INDIA_PARAMS

    sector_wacc = INDIA_PARAMS["sector_wacc"]
    for sector_key, wacc in sector_wacc.items():
        if sector_key.lower() in sector.lower():
            return wacc

    type_defaults = {
        "QUALITY_COMPOUNDER": 0.130,
        "CYCLICAL":           0.145,
        "FINANCIAL":          0.115,
        "INFRASTRUCTURE":     0.140,
        "REAL_ASSET":         0.150,
        "GROWTH":             0.140,
        "DIVIDEND_YIELD":     0.120,
        "CONGLOMERATE":       0.135,
        "UNKNOWN":            0.130,
    }
    return type_defaults.get(stock_type, 0.130)
