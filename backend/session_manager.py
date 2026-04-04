"""
ScreenerClaw — Session State Manager
Tracks per-user session state across messages.
Used to enable follow-up stock selection after a screening result.
"""
from __future__ import annotations

import time
from typing import Any, Optional

# Session expires after 15 minutes of inactivity
SESSION_TTL = 15 * 60


class SessionState:
    IDLE = "idle"
    AWAITING_STOCK = "awaiting_stock"  # user just got screening results, can pick a stock


class SessionManager:
    """
    In-memory session store keyed by session_id.
    Thread-safe for asyncio (single-threaded event loop).
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def set_screening_result(self, session_id: str, results: list[dict], query: str) -> None:
        """Store screening results so the user can follow up by picking a stock."""
        self._sessions[session_id] = {
            "state": SessionState.AWAITING_STOCK,
            "results": results,
            "query": query,
            "ts": time.monotonic(),
        }

    def get_state(self, session_id: str) -> Optional[dict]:
        """Return session state if it exists and hasn't expired."""
        s = self._sessions.get(session_id)
        if not s:
            return None
        if time.monotonic() - s["ts"] > SESSION_TTL:
            del self._sessions[session_id]
            return None
        return s

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def resolve_stock_from_input(
        self, session_id: str, user_text: str
    ) -> Optional[dict]:
        """
        Given a follow-up message, try to match it to one of the screening results.
        Returns the matched result dict or None if no match.

        Accepts:
          - A number like "3" or "3." → picks result #3 from the list
          - A ticker like "TCS" → matches symbol
          - A company name (fuzzy) → matches by substring
        """
        s = self.get_state(session_id)
        if not s or s["state"] != SessionState.AWAITING_STOCK:
            return None

        results = s.get("results", [])
        if not results:
            return None

        text = user_text.strip().rstrip(".")

        # Try numeric selection ("3", "03", "3.")
        try:
            idx = int(text) - 1
            if 0 <= idx < len(results):
                self.clear(session_id)
                return results[idx]
        except ValueError:
            pass

        # Try exact ticker match
        text_upper = text.upper()
        for r in results:
            ticker = (r.get("ticker") or r.get("symbol") or "").upper()
            if ticker and ticker == text_upper:
                self.clear(session_id)
                return r

        # Try substring company name match (case-insensitive)
        text_lower = text.lower()
        for r in results:
            name = (r.get("company_name") or "").lower()
            if text_lower in name or name in text_lower:
                self.clear(session_id)
                return r

        return None


# Module-level singleton
_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager
