"""
ScreenerClaw — Memory Manager
Reads and writes persistent learnings to agent_skills/memory/
Inspired by OpenClaw's file-based memory architecture.

Structure:
  agent_skills/memory/
    sectors/<sector_slug>.md   — sector-specific learnings
    companies/<ticker>.md      — company-specific notes
    market/observations.md     — market cycle observations
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.logger import get_logger

logger = get_logger(__name__)

# Root of the agent_skills/memory directory
MEMORY_ROOT = Path(__file__).parent.parent / "agent_skills" / "memory"
SECTORS_DIR = MEMORY_ROOT / "sectors"
COMPANIES_DIR = MEMORY_ROOT / "companies"
MARKET_FILE = MEMORY_ROOT / "market" / "observations.md"
HOT_MEMORY_FILE = Path(__file__).parent.parent / "agent_skills" / "MEMORY.md"


def _ensure_dirs():
    SECTORS_DIR.mkdir(parents=True, exist_ok=True)
    COMPANIES_DIR.mkdir(parents=True, exist_ok=True)
    (MEMORY_ROOT / "market").mkdir(parents=True, exist_ok=True)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", text.lower().strip()).strip("_")


class MemoryManager:
    """Reads and writes persistent learnings to agent_skills/memory/."""

    def __init__(self):
        _ensure_dirs()

    # ── Read ──────────────────────────────────────────────────────────────────

    def read_sector_memory(self, sector: str) -> str:
        path = SECTORS_DIR / f"{_slug(sector)}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            logger.info("Loaded sector memory", extra={"sector": sector, "chars": len(content)})
            return content
        return ""

    def read_company_memory(self, ticker: str) -> str:
        path = COMPANIES_DIR / f"{ticker.upper()}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            logger.info("Loaded company memory", extra={"ticker": ticker, "chars": len(content)})
            return content
        return ""

    def read_market_observations(self) -> str:
        if MARKET_FILE.exists():
            return MARKET_FILE.read_text(encoding="utf-8")
        return ""

    def read_hot_memory(self) -> str:
        if HOT_MEMORY_FILE.exists():
            return HOT_MEMORY_FILE.read_text(encoding="utf-8")
        return ""

    def read_all_context(self, ticker: str, sector: str) -> str:
        """Load all relevant memory for a given ticker + sector analysis."""
        parts = []
        sector_mem = self.read_sector_memory(sector)
        if sector_mem:
            parts.append(f"## Prior Sector Learnings ({sector})\n{sector_mem}")
        company_mem = self.read_company_memory(ticker)
        if company_mem:
            parts.append(f"## Prior Company Notes ({ticker})\n{company_mem}")
        return "\n\n".join(parts)

    # ── Write ─────────────────────────────────────────────────────────────────

    def write_company_learning(self, ticker: str, company_name: str, learning: str) -> None:
        """Append a timestamped learning to the company memory file."""
        path = COMPANIES_DIR / f"{ticker.upper()}.md"
        timestamp = datetime.now().strftime("%Y-%m-%d")
        header = f"# {company_name} ({ticker.upper()}) — ScreenerClaw Notes\n\n" if not path.exists() else ""
        entry = f"\n## {timestamp}\n{learning.strip()}\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(header + entry)
        logger.info("Company memory updated", extra={"ticker": ticker})

    def write_sector_learning(self, sector: str, learning: str) -> None:
        """Append a timestamped learning to the sector memory file."""
        path = SECTORS_DIR / f"{_slug(sector)}.md"
        timestamp = datetime.now().strftime("%Y-%m-%d")
        header = f"# {sector} Sector — ScreenerClaw Learnings\n\n" if not path.exists() else ""
        entry = f"\n## {timestamp}\n{learning.strip()}\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(header + entry)
        logger.info("Sector memory updated", extra={"sector": sector})

    def write_market_observation(self, observation: str) -> None:
        """Append a market observation to observations.md."""
        (MEMORY_ROOT / "market").mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d")
        header = "# Market Observations — ScreenerClaw\n\n" if not MARKET_FILE.exists() else ""
        entry = f"\n## {timestamp}\n{observation.strip()}\n"
        with open(MARKET_FILE, "a", encoding="utf-8") as f:
            f.write(header + entry)
        logger.info("Market observation written")

    def extract_and_save_learnings(self, ticker: str, sector: str, pipeline_result: dict) -> None:
        """
        Extract key learnings from a completed pipeline result and persist them.
        Called automatically at the end of each single-stock analysis.
        """
        company_name = pipeline_result.get("company_name", ticker)
        business = pipeline_result.get("business_analysis", {})
        macro = pipeline_result.get("macro_analysis", {})
        scoring = pipeline_result.get("scoring", {})

        # Company learning: one_line_verdict + moat + score
        verdict_line = business.get("one_line_verdict", "")
        moat = (business.get("moat_analysis") or {}).get("overall_moat_verdict", "")
        score = scoring.get("composite_score", "N/A")
        comp_verdict = (scoring.get("verdict") or "").upper()
        buy_ranges = pipeline_result.get("verdict", {}).get("buy_ranges", [])

        company_learning_parts = []
        if verdict_line:
            company_learning_parts.append(f"**Verdict:** {verdict_line}")
        if moat:
            company_learning_parts.append(f"**Moat:** {moat}")
        if score:
            company_learning_parts.append(f"**Score:** {score}/100 ({comp_verdict})")
        if buy_ranges:
            br = buy_ranges[0] if buy_ranges else {}
            pf = br.get("price_from") or br.get("lower", "")
            pt = br.get("price_to") or br.get("upper", "")
            if pf and pt:
                company_learning_parts.append(f"**Buy Range:** ₹{pf}–₹{pt}")

        if company_learning_parts:
            self.write_company_learning(ticker, company_name, "\n".join(company_learning_parts))

        # Sector learning: net_macro_verdict + key headwinds/tailwinds
        macro_verdict = macro.get("net_macro_verdict", "")
        headwinds = macro.get("headwinds_summary", [])
        tailwinds = macro.get("tailwinds_summary", [])

        sector_parts = []
        if macro_verdict:
            sector_parts.append(f"**Macro verdict for {company_name}:** {macro_verdict}")
        if headwinds:
            sector_parts.append("**Key headwinds:** " + "; ".join(str(h) for h in headwinds[:3]))
        if tailwinds:
            sector_parts.append("**Key tailwinds:** " + "; ".join(str(t) for t in tailwinds[:3]))

        if sector_parts:
            self.write_sector_learning(sector, "\n".join(sector_parts))
