"""
Screener.in Filter Scraper
Runs a query on https://www.screener.in/screen/raw/ and parses the HTML results table.

URL pattern used by Screener:
  GET /screen/raw/?sort=&order=&source_id=&query=<URL-encoded>&page=<N>&limit=50

The page renders a <table class="data-table"> with column headers using
data-tooltip attributes for the full column name, and <tr data-row-company-id>
for each result row.

Fetches ALL pages from Screener concurrently (5 pages at a time) so that
every matching stock is returned regardless of total count.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup
from backend.logger import get_logger

logger = get_logger(__name__)

SCREEN_URL = "https://www.screener.in/screen/raw/"
DEFAULT_PER_PAGE = 50
PAGE_DELAY_SECONDS = 1.2    # pause between every page fetch to avoid 429


def _num(text: Optional[str]) -> Optional[float]:
    if not text or text.strip() in ("-", "--", "N/A", ""):
        return None
    text = text.strip().replace(",", "").replace("%", "").replace("₹", "").replace("Rs.", "")
    try:
        return float(text)
    except ValueError:
        return None


def _extract_ticker(href: str) -> Optional[str]:
    """Extract ticker from Screener company URL like /company/TCS/ or /company/514330/."""
    if not href:
        return None
    parts = [p for p in href.strip("/").split("/") if p]
    # parts = ["company", "TICKER"] or ["company", "TICKER", "consolidated"]
    if len(parts) >= 2 and parts[0] == "company":
        return parts[1]
    return None


def _normalise_column(tooltip: str) -> str:
    """Normalise a data-tooltip column name to a standard field key."""
    t = tooltip.lower().strip()
    mapping = {
        "current price":             "current_price",
        "price to earning":          "pe",
        "market capitalization":     "market_cap",
        "dividend yield":            "dividend_yield",
        "net profit latest quarter": "profit_qtr",
        "yoy quarterly profit growth": "profit_growth_qtr",
        "sales latest quarter":      "sales_qtr",
        "yoy quarterly sales growth":"sales_growth_qtr",
        "return on capital employed":"roce",
        "return on equity":          "roe",
        "return on assets":          "roa",
        "debt to equity":            "debt_to_equity",
        "price to book value":       "pb",
        "earnings yield":            "earnings_yield",
        "enterprise value":          "enterprise_value",
        "ev/ebitda":                 "ev_ebitda",
        "peg ratio":                 "peg",
        "current ratio":             "current_ratio",
        "interest coverage ratio":   "interest_coverage",
        "promoter holding":          "promoter_holding",
        "pledged percentage":        "pledged_pct",
        "fii holding":               "fii_holding",
        "dii holding":               "dii_holding",
        "sales growth 5years":       "sales_growth_5y",
        "sales growth 3years":       "sales_growth_3y",
        "profit growth 5years":      "profit_growth_5y",
        "profit growth 3years":      "profit_growth_3y",
        "return over 1year":         "return_1y",
        "return over 3months":       "return_3m",
        "return over 6months":       "return_6m",
        "eps":                       "eps",
        "book value":                "book_value",
        "piotroski score":           "piotroski",
        "rsi":                       "rsi",
        "dma 50":                    "dma_50",
        "dma 200":                   "dma_200",
        "free cash flow last year":  "fcf",
        "intrinsic value":           "intrinsic_value",
    }
    return mapping.get(t, t.replace(" ", "_").replace("/", "_"))


class ScreenerFilterScraper:

    async def run_filter(
        self,
        client: httpx.AsyncClient,
        query: str,
    ) -> tuple[list[dict], int]:
        """
        Fetch ALL pages for a Screener.in filter query, one page at a time with
        a fixed delay between each to avoid 429 rate-limiting.

        Returns (results, total_count_on_site).
        """
        results: list[dict] = []
        site_total = 0
        total_pages = 1

        for page in range(1, 9999):   # upper bound; breaks on last page naturally
            params = {
                "sort": "", "order": "", "source_id": "",
                "query": query, "page": page, "limit": DEFAULT_PER_PAGE,
            }
            url = f"{SCREEN_URL}?{urlencode(params)}"
            logger.info("Screener filter fetch", extra={"page": page, "of": total_pages, "query": query[:80]})

            # Fetch with retry on 429
            page_rows, page_site_total = await self._fetch_page_with_retry(client, url, page)

            if page == 1:
                site_total = page_site_total
                pages_info = await self._get_pagination_from_url(client, url)
                total_pages = pages_info
                logger.info(
                    "Filter page 1 done",
                    extra={"rows": len(page_rows), "total_on_site": site_total, "total_pages": total_pages},
                )
            else:
                logger.info("Filter page parsed", extra={"page": page, "rows": len(page_rows)})

            results.extend(page_rows)

            # Stop when we've fetched the last page or got an empty page
            if page >= total_pages or not page_rows:
                break

            # Polite delay before next page
            await asyncio.sleep(PAGE_DELAY_SECONDS)

        logger.info(
            "Filter scraper done",
            extra={"total": len(results), "site_total": site_total, "pages_fetched": page},
        )
        return results, site_total

    async def _fetch_page_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        page: int,
    ) -> tuple[list[dict], int]:
        """Fetch a single page, retrying on 429 with exponential back-off."""
        for attempt in range(4):   # up to 4 attempts: delays 2s, 4s, 8s
            try:
                resp = await client.get(url, timeout=30)
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)   # 2, 4, 8, 16 seconds
                    logger.warning(
                        "429 rate limit — waiting before retry",
                        extra={"page": page, "wait_s": wait, "attempt": attempt + 1},
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")
                rows, total = self._parse_results(soup)
                return rows, total
            except httpx.HTTPStatusError:
                raise   # re-raise non-429 HTTP errors immediately
            except Exception as exc:
                logger.error(
                    "Filter fetch failed",
                    extra={"page": page, "attempt": attempt + 1, "error": str(exc)},
                )
                if attempt < 3:
                    await asyncio.sleep(2 ** (attempt + 1))
        logger.error("Filter fetch gave up after retries", extra={"page": page})
        return [], 0

    async def _get_pagination_from_url(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> int:
        """Re-use the already-fetched page-1 HTML to get total_pages (called right after page 1)."""
        # We already fetched page 1 above; re-fetch just to parse pagination.
        # To avoid double-fetching, we accept a slight duplication on page 1 only.
        try:
            resp = await client.get(url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            info = self._parse_pagination(soup)
            return info.get("total_pages", 1)
        except Exception:
            return 1

    def _parse_results(self, soup: BeautifulSoup) -> tuple[list[dict], int]:
        """
        Parse the results table.
        Returns (list_of_rows, total_result_count_on_site).
        """
        # Extract total result count from the page info div
        total_count = 0
        page_info = soup.find(attrs={"data-page-info": True})
        if page_info:
            text = page_info.get_text()
            m = re.search(r"(\d[\d,]*)\s+result", text)
            if m:
                total_count = int(m.group(1).replace(",", ""))

        table = soup.find("table", class_="data-table")
        if not table:
            table = soup.find("table")
        if not table:
            logger.warning("No results table found on Screener filter page")
            return [], total_count

        tbody = table.find("tbody") or table
        all_rows = tbody.find_all("tr")
        if not all_rows:
            return [], total_count

        # Extract column definitions from the FIRST header row.
        # Headers use <th data-tooltip="Column Name"> for all data columns.
        # The S.No. column has no tooltip; the Name column has no tooltip.
        columns: list[str] = []
        header_row = all_rows[0]
        if header_row.find("th"):
            for th in header_row.find_all("th"):
                tooltip = th.get("data-tooltip", "").strip()
                text = th.get_text(strip=True).lower()
                if tooltip:
                    columns.append(_normalise_column(tooltip))
                elif "s.no" in text or text == "":
                    columns.append("_sno")
                else:
                    columns.append("_name")

        results: list[dict] = []
        for tr in all_rows:
            # Skip header rows (rows that contain <th> elements)
            if tr.find("th"):
                continue

            # Only process data rows (they have data-row-company-id)
            company_id = tr.get("data-row-company-id")
            if not company_id:
                continue

            cells = tr.find_all("td")
            if len(cells) < 2:
                continue

            row: dict[str, Any] = {"screener_company_id": company_id}

            for i, cell in enumerate(cells):
                if i >= len(columns):
                    break
                col = columns[i]

                if col == "_sno":
                    continue

                if col == "_name":
                    link = cell.find("a")
                    if link:
                        row["company_name"] = link.get_text(strip=True)
                        ticker = _extract_ticker(link.get("href", ""))
                        row["ticker"] = ticker
                        row["symbol"] = ticker
                        # Track whether BSE code or NSE symbol
                        if ticker and ticker.isdigit():
                            row["bse_code"] = ticker
                    else:
                        row["company_name"] = cell.get_text(strip=True)
                    continue

                val_text = cell.get_text(strip=True)
                num_val = _num(val_text)

                # Store numeric where possible, else string
                if num_val is not None:
                    row[col] = num_val
                elif val_text and val_text not in ("-", "--"):
                    row[col] = val_text

            if row.get("company_name"):
                results.append(row)

        return results, total_count

    def _parse_pagination(self, soup: BeautifulSoup) -> dict:
        """Extract pagination info from the page."""
        page_info = soup.find(attrs={"data-page-info": True})
        if not page_info:
            return {"total_pages": 1}

        text = page_info.get_text()
        # "103 results found: Showing page 1 of 3"
        m = re.search(r"page\s+\d+\s+of\s+(\d+)", text, re.IGNORECASE)
        if m:
            return {"total_pages": int(m.group(1))}
        return {"total_pages": 1}
