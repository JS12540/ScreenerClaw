"""
Screener.in Filter Scraper — Phase 2A
Runs a Screener.in query filter and returns the results table.

Endpoint: https://www.screener.in/screen/raw/?query=<URL-encoded query>
The response is an HTML page with a results table.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlencode, quote

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SCREEN_URL = "https://www.screener.in/screen/raw/"


def _num(text: Optional[str]) -> Optional[float]:
    if not text or text.strip() in ("-", "--", ""):
        return None
    text = text.strip().replace(",", "").replace("%", "").replace("₹", "")
    try:
        return float(text)
    except ValueError:
        return None


class ScreenerFilterScraper:

    async def run_filter(
        self,
        client: httpx.AsyncClient,
        query: str,
        limit: int = 50,
    ) -> list[dict]:
        """
        Run a Screener.in filter query and return a list of stock dicts.

        query: Screener query syntax, e.g.
            "Return on capital employed > 20 AND Debt to equity < 0.5"
        """
        params = {"query": query, "limit": limit}
        url = f"{SCREEN_URL}?{urlencode(params)}"
        logger.info("Running Screener filter: %s", url)

        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("Filter scraper fetch failed: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse_results(soup)

    def _parse_results(self, soup: BeautifulSoup) -> list[dict]:
        """Parse the results table from Screener's filter page."""
        table = soup.find("table", class_="data-table")
        if not table:
            # Try any visible table
            table = soup.find("table")

        if not table:
            logger.warning("No results table found on Screener filter page")
            return []

        tbody = table.find("tbody") or table
        if not tbody:
            return []

        all_rows = tbody.find_all("tr")
        if not all_rows:
            return []

        # Headers are th elements in first row (no thead on Screener filter pages)
        headers = []
        header_row = all_rows[0]
        if header_row.find("th"):
            headers = [th.get_text(strip=True).lower() for th in header_row.find_all("th")]
            data_rows = all_rows[1:]
        else:
            data_rows = all_rows

        results = []
        for tr in data_rows:
            cells = tr.find_all("td")
            if not cells:
                continue

            row: dict[str, Any] = {}

            for i, cell in enumerate(cells):
                if i >= len(headers):
                    break
                col = headers[i]
                val = cell.get_text(strip=True)

                # Company name + link (first data column)
                if i == 1 or "name" in col:
                    link = cell.find("a")
                    if link:
                        row["company_name"] = link.get_text(strip=True)
                        href = link.get("href", "")
                        # URL: /company/TICKER/ or /company/TICKER/consolidated/
                        if href:
                            parts = [p for p in href.strip("/").split("/") if p]
                            # parts = ["company", "TICKER"] or ["company", "TICKER", "consolidated"]
                            row["symbol"] = parts[1] if len(parts) >= 2 else parts[-1]
                        else:
                            row["symbol"] = None
                    else:
                        row["company_name"] = val

                elif "cmp" in col or "price" in col:
                    row["current_price"] = _num(val)
                elif "p/e" in col or col == "p/e":
                    row["pe"] = _num(val)
                elif "mar cap" in col or "market cap" in col:
                    row["market_cap"] = _num(val)
                elif "div yld" in col or "dividend" in col:
                    row["dividend_yield"] = _num(val)
                elif "roce" in col:
                    row["roce"] = _num(val)
                elif "roe" in col:
                    row["roe"] = _num(val)
                elif "sales" in col and "growth" not in col:
                    row["sales_qtr"] = _num(val)
                elif "sales" in col and "var" in col:
                    row["sales_growth_qtr"] = _num(val)
                elif "np qtr" in col or ("profit" in col and "qtr" in col):
                    row["profit_qtr"] = _num(val)
                elif "qtr profit var" in col or "profit growth" in col:
                    row["profit_growth_qtr"] = _num(val)
                elif "debt" in col:
                    row["debt_to_equity"] = _num(val)

            if row.get("company_name"):
                results.append(row)

        logger.info("Filter returned %d results", len(results))
        return results
