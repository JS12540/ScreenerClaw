"""
Screener.in Authentication — Phase 0
Logs in using credentials from environment variables.
Maintains a persistent authenticated session for all subsequent requests.
"""
from __future__ import annotations

from typing import Optional

import httpx
from bs4 import BeautifulSoup

from backend.config import settings
from backend.logger import get_logger

logger = get_logger(__name__)

LOGIN_URL = "https://www.screener.in/login/"
BASE_HEADERS = {
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


class ScreenerAuth:
    """
    Singleton-style auth manager.
    Call get_client() to get an authenticated httpx.AsyncClient.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._logged_in = False

    async def get_client(self) -> httpx.AsyncClient:
        """Return authenticated httpx client, logging in on first call."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=BASE_HEADERS,
                follow_redirects=True,
                timeout=30.0,
            )
        if not self._logged_in:
            await self._login()
        return self._client

    async def _login(self) -> None:
        """POST login form to Screener.in."""
        username = settings.screener_username
        password = settings.screener_password

        if not username or not password:
            logger.warning("Screener.in credentials not set — guest mode", extra={"mode": "guest"})
            self._logged_in = True
            return

        # Step 1: GET login page to extract CSRF token
        resp = await self._client.get(LOGIN_URL)
        resp.raise_for_status()

        # Extract CSRF token from form field or cookie
        soup = BeautifulSoup(resp.text, "lxml")
        csrf_input = soup.find("input", {"name": "csrfmiddlewaretoken"})
        csrf_token = csrf_input.get("value", "") if csrf_input else resp.cookies.get("csrftoken", "")

        if not csrf_token:
            logger.warning("Could not extract CSRF token — login may fail")

        # Step 2: POST credentials
        login_resp = await self._client.post(
            LOGIN_URL,
            data={
                "csrfmiddlewaretoken": csrf_token,
                "username": username,
                "password": password,
                "next": "/",
            },
            headers={"Referer": LOGIN_URL},
        )

        # Success: redirected away from /login/
        if "login" in str(login_resp.url).lower() and login_resp.status_code == 200:
            # Still on login page → failed
            logger.error(
                "Screener.in login failed",
                extra={"username": username, "reason": "still on login page"},
            )
            self._logged_in = True  # continue in guest mode
            return

        self._logged_in = True
        logger.info("Screener.in login successful", extra={"username": username})

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            self._logged_in = False


# Module-level singleton
_auth = ScreenerAuth()


async def get_authenticated_client() -> httpx.AsyncClient:
    """Public helper: return a logged-in httpx.AsyncClient."""
    return await _auth.get_client()


async def close_session() -> None:
    await _auth.close()
