"""
ScreenerClaw — Configuration
All app settings, India-specific valuation parameters, and LLM routing.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM API keys ──────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""

    # ── Channel tokens ────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""   # for socket mode (xapp-...)
    discord_bot_token: str = ""

    # ── WhatsApp (Baileys bridge) ─────────────────────────────────────────────
    # No token needed — authenticate via QR code scan on first run.
    whatsapp_bridge_port: int = 3000    # Node.js Baileys bridge HTTP port
    whatsapp_webhook_port: int = 8080   # Python webhook receiver port

    # ── LLM routing: task-type based model selection ─────────────────────────
    # reasoning: deep analysis, valuation, reports (gpt-5-mini)
    reasoning_provider: str = "openai"
    reasoning_model: str = "gpt-5-mini"

    # execution: data fetch, classification, quick tasks (gpt-4.1-mini)
    execution_provider: str = "openai"
    execution_model: str = "gpt-4.1-mini"

    # fast: intent routing, alerts, short responses (groq)
    fast_provider: str = "groq"
    fast_model: str = "llama-3.3-70b-versatile"

    # ── Legacy defaults (kept for backwards compat) ───────────────────────────
    default_llm_provider: str = ""
    default_llm_model: str = ""

    # ── Screener.in ───────────────────────────────────────────────────────────
    screener_base_url: str = "https://www.screener.in"
    screener_username: str = ""
    screener_password: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    request_timeout: int = 30


settings = Settings()

# ─── India Valuation Parameters ───────────────────────────────────────────────

INDIA_PARAMS = {
    "risk_free_rate":           0.070,   # 10yr G-Sec yield
    "equity_risk_premium":      0.060,   # Damodaran India ERP
    "default_wacc":             0.130,
    "terminal_growth_real":     0.040,   # India long-run real GDP
    "terminal_growth_nominal":  0.060,   # 4% real + 2% inflation
    "aaa_bond_yield":           0.075,   # For Graham Formula denominator

    "sector_wacc": {
        "Private Banking":       0.115,
        "FMCG":                  0.110,
        "IT Services":           0.120,
        "Pharmaceuticals":       0.130,
        "Specialty Chemicals":   0.135,
        "Capital Goods":         0.135,
        "Infrastructure":        0.145,
        "Metals & Mining":       0.150,
        "Real Estate":           0.155,
        "default":               0.130,
    },

    "sector_margin_of_safety": {
        "FMCG":                  0.20,
        "IT Services":           0.20,
        "Private Banking":       0.25,
        "Pharmaceuticals":       0.25,
        "Specialty Chemicals":   0.30,
        "Cyclicals":             0.35,
        "PSU Banks":             0.40,
        "Infrastructure":        0.30,
        "default":               0.25,
    },
}

# ─── Stock Type Definitions ───────────────────────────────────────────────────

STOCK_TYPES = {
    "QUALITY_COMPOUNDER":  [
        "Pharmaceuticals", "FMCG", "Specialty Chemicals", "IT Services",
        "Consumer Brands", "Consumer Goods",
    ],
    "CYCLICAL":            [
        "Metals & Mining", "Cement", "Commodity Chemicals",
        "Capital Goods", "Textile",
    ],
    "FINANCIAL":           [
        "Banks", "Private Banking", "PSU Banks", "NBFCs",
        "Financial Services", "Insurance",
    ],
    "INFRASTRUCTURE":      [
        "Infrastructure", "Roads", "Power", "Defence", "Railways",
    ],
    "REAL_ASSET":          [
        "Real Estate", "Realty", "Construction", "Housing",
        "Property", "Hospitality", "Hotels", "Media",
    ],
    "GROWTH":              ["Technology", "E-Commerce", "SaaS"],
    "DIVIDEND_YIELD":      ["Utilities", "Oil & Gas"],
    "CONGLOMERATE":        [
        "Conglomerate", "Diversified", "Holding Company",
    ],
}

# Valuation methods recommended per stock type
VALUATION_METHODS_BY_TYPE = {
    "QUALITY_COMPOUNDER": [
        "greenwald_growth", "dcf_eps", "dcf_fcf", "epv", "pe_based", "reverse_dcf",
    ],
    "CYCLICAL": [
        "graham_formula", "pe_based", "reverse_dcf", "dcf_eps",
    ],
    "FINANCIAL": [
        "pb_roe", "ddm", "pe_based", "reverse_dcf",
    ],
    "INFRASTRUCTURE": [
        "dcf_fcf", "epv", "reverse_dcf", "pe_based",
    ],
    "REAL_ASSET": [
        "pe_based", "graham_formula", "reverse_dcf", "dcf_fcf",
    ],
    "GROWTH": [
        "greenwald_growth", "reverse_dcf", "pe_based", "epv",
    ],
    "DIVIDEND_YIELD": [
        "ddm", "pe_based", "dcf_eps", "reverse_dcf",
    ],
    "CONGLOMERATE": [
        "sotp",        # Sum of Parts — PRIMARY method for conglomerates
        "reverse_dcf", # What growth is priced in?
    ],
    "UNKNOWN": [
        "dcf_eps", "graham_formula", "pe_based", "reverse_dcf",
    ],
}

# ─── India Macro Factor Taxonomy ──────────────────────────────────────────────

INDIA_MACRO_FACTORS = [
    "RBI Rate Cycle",
    "INR/USD Rate",
    "CPI/WPI Inflation",
    "Monsoon and Rural Demand",
    "Government Capex and PLI",
    "GST Collections",
    "Credit Growth",
    "Real Estate Cycle",
    "Crude Oil Price",
]

GEOPOLITICAL_FACTORS = [
    "China+1 Manufacturing Shift",
    "US Tariffs and Trade Policy",
    "Middle East Conflict and Shipping",
    "Russia-Ukraine and European Demand",
    "China Competition",
    "US FDA and EU Regulatory",
]

# ─── Scoring Weights ──────────────────────────────────────────────────────────

DEFAULT_SCORE_WEIGHTS = {
    "business_quality": 0.20,
    "growth_past":      0.10,
    "growth_forward":   0.20,
    "valuation":        0.30,
    "financial_health": 0.10,
    "business_outlook": 0.10,
}

# Per stock-type overrides for score weights (valuation weight boosted where method is definitive)
STOCK_TYPE_SCORE_WEIGHTS: dict[str, dict] = {
    # For conglomerates, SOTP is the most reliable method — raise valuation weight to 35%
    "CONGLOMERATE": {
        "business_quality": 0.20,
        "growth_past":      0.05,
        "growth_forward":   0.15,
        "valuation":        0.35,   # SOTP is primary and most reliable
        "financial_health": 0.10,
        "business_outlook": 0.15,
    },
}

INTENT_SCORE_WEIGHTS = {
    "undervalued": {
        "business_quality": 0.20, "growth_past": 0.10, "growth_forward": 0.15,
        "valuation": 0.35, "financial_health": 0.10, "business_outlook": 0.10,
    },
    "growth": {
        "business_quality": 0.20, "growth_past": 0.20, "growth_forward": 0.35,
        "valuation": 0.10, "financial_health": 0.05, "business_outlook": 0.10,
    },
    "quality": {
        "business_quality": 0.40, "growth_past": 0.15, "growth_forward": 0.15,
        "valuation": 0.10, "financial_health": 0.10, "business_outlook": 0.10,
    },
    "compounder": {
        "business_quality": 0.30, "growth_past": 0.20, "growth_forward": 0.20,
        "valuation": 0.10, "financial_health": 0.05, "business_outlook": 0.15,
    },
    "dividend": {
        "business_quality": 0.20, "growth_past": 0.10, "growth_forward": 0.10,
        "valuation": 0.25, "financial_health": 0.20, "business_outlook": 0.15,
    },
}

SCORE_VERDICT = {
    75: ("STRONG BUY", "🟢"),
    60: ("BUY", "🔵"),
    50: ("WATCHLIST", "🟡"),
    40: ("NEUTRAL", "⚪"),
    0:  ("AVOID", "🔴"),
}

# ─── Market Cap Buckets (INR Crores) ──────────────────────────────────────────

MARKET_CAP_LARGE = 20000
MARKET_CAP_MID   = 5000
MARKET_CAP_SMALL = 500

# ─── Sector Synonyms ──────────────────────────────────────────────────────────

SECTOR_SYNONYMS = {
    "it": "Information Technology",
    "tech": "Information Technology",
    "technology": "Information Technology",
    "software": "Information Technology",
    "it services": "IT Services",
    "pharma": "Pharmaceuticals",
    "pharmaceutical": "Pharmaceuticals",
    "healthcare": "Healthcare",
    "health": "Healthcare",
    "hospital": "Healthcare",
    "banking": "Banks",
    "bank": "Banks",
    "financial services": "Financial Services",
    "finance": "Financial Services",
    "nbfc": "Financial Services",
    "insurance": "Insurance",
    "auto": "Automobile",
    "automobile": "Automobile",
    "automotive": "Automobile",
    "ev": "Automobile",
    "fmcg": "FMCG",
    "consumer goods": "FMCG",
    "consumer staples": "FMCG",
    "retail": "Retail",
    "real estate": "Real Estate",
    "realty": "Real Estate",
    "construction": "Construction",
    "infra": "Infrastructure",
    "infrastructure": "Infrastructure",
    "cement": "Cement",
    "steel": "Metals & Mining",
    "metals": "Metals & Mining",
    "mining": "Metals & Mining",
    "chemicals": "Specialty Chemicals",
    "specialty chemicals": "Specialty Chemicals",
    "agro": "Agriculture",
    "agriculture": "Agriculture",
    "fertilizer": "Agriculture",
    "energy": "Energy",
    "oil": "Oil & Gas",
    "gas": "Oil & Gas",
    "power": "Power",
    "electricity": "Power",
    "renewable": "Power",
    "solar": "Power",
    "telecom": "Telecom",
    "media": "Media & Entertainment",
    "aviation": "Aviation",
    "logistics": "Logistics",
    "railway": "Railways",
    "defense": "Defence",
    "defence": "Defence",
    "psu": "PSU",
    "capital goods": "Capital Goods",
    "engineering": "Engineering",
    "textile": "Textiles",
    "paints": "Paints",
}

# ─── HTTP Headers ─────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}
