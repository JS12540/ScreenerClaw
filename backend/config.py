"""
Screener Investment Research Agent — Configuration
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""
    # Default: groq with llama model
    default_llm_provider: str = "groq"
    default_llm_model: str = "llama-3.3-70b-versatile"

    # --- App ---
    environment: str = "development"
    log_level: str = "INFO"

    # --- Screener.in credentials ---
    screener_base_url: str = "https://www.screener.in"
    screener_username: str = ""   # Screener.in login email
    screener_password: str = ""   # Screener.in login password

    # --- Request settings ---
    request_timeout: int = 30


settings = Settings()

# India risk-free rate (10-year G-Sec yield approximation)
INDIA_RISK_FREE_RATE = 0.07  # 7%
EQUITY_RISK_PREMIUM = 0.06   # 6%
DEFAULT_DISCOUNT_RATE = 0.13  # 13% (risk-free + ERP)
TERMINAL_GROWTH_RATE = 0.04  # 4%
DCF_GROWTH_STAGE_YEARS = 10
DCF_TERMINAL_STAGE_YEARS = 10
DCF_MIN_GROWTH_RATE = 0.05   # 5%
DCF_MAX_GROWTH_RATE = 0.20   # 20%

# Market cap buckets (in crores INR)
MARKET_CAP_LARGE = 20000      # > 20,000 cr = Large cap
MARKET_CAP_MID = 5000         # 5,000 - 20,000 cr = Mid cap
MARKET_CAP_SMALL = 500        # 500 - 5,000 cr = Small cap
# < 500 cr = Micro cap

# Sector synonyms mapping
SECTOR_SYNONYMS = {
    "it": "Information Technology",
    "tech": "Information Technology",
    "technology": "Information Technology",
    "software": "Information Technology",
    "it services": "Information Technology",
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
    "chemicals": "Chemicals",
    "speciality chemicals": "Chemicals",
    "specialty chemicals": "Chemicals",
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
    "telecommunication": "Telecom",
    "media": "Media & Entertainment",
    "entertainment": "Media & Entertainment",
    "aviation": "Aviation",
    "airlines": "Aviation",
    "logistics": "Logistics",
    "shipping": "Logistics",
    "railway": "Railways",
    "rail": "Railways",
    "defense": "Defence",
    "defence": "Defence",
    "psu": "PSU",
    "capital goods": "Capital Goods",
    "engineering": "Engineering",
    "textile": "Textiles",
    "paints": "Paints",
}

# Theme-based queries mapping
THEME_MAPPINGS = {
    "compounders": {"roce_min": 15, "profit_cagr_min": 12, "debt_to_equity_max": 1.0},
    "undervalued": {"pe_percentile_max": 40, "pb_percentile_max": 40},
    "growth": {"revenue_cagr_min": 15, "profit_cagr_min": 15},
    "quality": {"roce_min": 20, "roe_min": 15, "debt_to_equity_max": 0.5},
    "dividend": {"dividend_yield_min": 2.0},
    "low debt": {"debt_to_equity_max": 0.3},
    "high cash flow": {"fcf_positive": True},
    "turnaround": {"profit_growth_yoy_min": 20},
    "defensive": {"beta_max": 0.8, "debt_to_equity_max": 0.5},
}

# NSE sector index mapping
NSE_SECTOR_INDICES = {
    "Information Technology": "NIFTY IT",
    "Banks": "NIFTY BANK",
    "Financial Services": "NIFTY FINANCIAL SERVICES",
    "Pharmaceuticals": "NIFTY PHARMA",
    "FMCG": "NIFTY FMCG",
    "Energy": "NIFTY ENERGY",
    "Automobile": "NIFTY AUTO",
    "Metals & Mining": "NIFTY METAL",
    "Real Estate": "NIFTY REALTY",
    "Infrastructure": "NIFTY INFRA",
    "Media & Entertainment": "NIFTY MEDIA",
    "Healthcare": "NIFTY HEALTHCARE",
    "Chemicals": "NIFTY CHEMICALS",
    "Capital Goods": "NIFTY CAPITAL MARKETS",
    "PSU": "NIFTY PSE",
}

# Scoring weights
SCORE_WEIGHTS = {
    "quality": 0.30,
    "growth": 0.25,
    "valuation": 0.20,
    "financial_health": 0.15,
    "consistency": 0.10,
}

# Intent-based weight overrides
INTENT_WEIGHTS = {
    "undervalued": {"quality": 0.20, "growth": 0.15, "valuation": 0.40, "financial_health": 0.15, "consistency": 0.10},
    "growth": {"quality": 0.20, "growth": 0.45, "valuation": 0.15, "financial_health": 0.10, "consistency": 0.10},
    "quality": {"quality": 0.45, "growth": 0.20, "valuation": 0.15, "financial_health": 0.10, "consistency": 0.10},
    "compounder": {"quality": 0.30, "growth": 0.30, "valuation": 0.15, "financial_health": 0.10, "consistency": 0.15},
    "dividend": {"quality": 0.25, "growth": 0.10, "valuation": 0.30, "financial_health": 0.20, "consistency": 0.15},
    "defensive": {"quality": 0.35, "growth": 0.10, "valuation": 0.25, "financial_health": 0.20, "consistency": 0.10},
}

# Request headers for web scraping
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

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
}
