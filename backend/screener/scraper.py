"""
Screener.in Company Page Scraper — Phase 2B
Extracts ALL sections (A through J) from the Screener.in company page.

Sections extracted:
  A. Key Metrics (top ratios)
  B. About / Business Description + Key Points
  C. Quarterly Results (last 12 quarters)
  D. Profit & Loss (annual, 10+ years) + CAGR tables
  E. Balance Sheet (annual)
  F. Cash Flow (annual)
  G. Financial Ratios (annual)
  H. Shareholding Pattern
  I. Peer Comparison
  J. Documents / Announcements
"""
from __future__ import annotations

import re
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup, Tag
from backend.logger import get_logger

logger = get_logger(__name__)

SCREENER_BASE = "https://www.screener.in"
COMPANY_URL = f"{SCREENER_BASE}/company/{{symbol}}/consolidated/"
COMPANY_URL_STANDALONE = f"{SCREENER_BASE}/company/{{symbol}}/"


# ─── Number parsing ───────────────────────────────────────────────────────────

def _num(text: Optional[str]) -> Optional[float]:
    """Parse a human-readable number string to float. Returns None for blanks/dashes."""
    if text is None:
        return None
    text = text.strip()
    if not text or text in ("-", "--", "N/A", "NA", "n/a", ""):
        return None
    # Remove currency symbols, separators, percent
    text = (
        text.replace("₹", "")
            .replace(",", "")
            .replace("%", "")
            .replace("+", "")
    )
    # Remove trailing Cr/Lakh/K/k suffixes (with optional period)
    text = re.sub(r"\s*(Cr\.?|cr\.?|Lakh|lakh|K|k)\s*$", "", text).strip()
    # Take only first number if there's a range or slash
    text = text.split("/")[0].split("–")[0].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _txt(tag: Optional[Tag]) -> Optional[str]:
    if tag is None:
        return None
    return tag.get_text(strip=True) or None


# ─── Main Scraper ──────────────────────────────────────────────────────────────

class ScreenerScraper:

    async def scrape(self, client: httpx.AsyncClient, symbol: str) -> dict:
        """
        Scrape Screener.in for *symbol*.
        Tries consolidated URL first, falls back to standalone.
        """
        clean = symbol.upper().strip()
        for prefix in ("NSE:", "BSE:", "NSE_", "BSE_"):
            if clean.startswith(prefix):
                clean = clean[len(prefix):]
                break

        url = COMPANY_URL.format(symbol=clean)
        html = await self._fetch(client, url)

        if html is None:
            # Try standalone
            url = COMPANY_URL_STANDALONE.format(symbol=clean)
            html = await self._fetch(client, url)

        if html is None:
            return {"symbol": clean, "error": "not_found", "url_tried": url}

        soup = BeautifulSoup(html, "lxml")
        return self._parse(clean, url, soup)

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            logger.error("Fetch error for %s: %s", url, exc)
            return None

    # ─── Page parser ──────────────────────────────────────────────────────────

    def _parse(self, symbol: str, url: str, soup: BeautifulSoup) -> dict:
        data: dict[str, Any] = {
            "symbol": symbol,
            "url": url,
        }

        # ── Header ──────────────────────────────────────────────────────────
        data["company_name"] = _txt(soup.select_one("h1.margin-0, .company-name h1, h1"))
        data["bse_code"] = _txt(soup.select_one("a[href*='bseindia.com']"))
        data["nse_code"] = _txt(soup.select_one("a[href*='nseindia.com']"))

        # Sector / industry from <p class="sub"> containing market links
        sector = None
        industry = None
        for p in soup.select("p.sub"):
            links = p.find_all("a", href=True)
            for a in links:
                href = a.get("href", "")
                title = a.get("title", "").lower()
                text = _txt(a)
                if "broad sector" in title or "/market/" in href:
                    if not sector:
                        sector = text
                    elif not industry:
                        industry = text
        data["sector"] = sector
        data["industry"] = industry

        # ── A. Key Metrics ──────────────────────────────────────────────────
        data.update(self._parse_key_metrics(soup))

        # ── B. About / Business Description ────────────────────────────────
        data.update(self._parse_about(soup))

        # ── C. Quarterly Results ────────────────────────────────────────────
        data["quarterly_results"] = self._parse_quarterly(soup)

        # ── D. Profit & Loss ────────────────────────────────────────────────
        data.update(self._parse_profit_loss(soup))

        # ── E. Balance Sheet ────────────────────────────────────────────────
        data["balance_sheet"] = self._parse_balance_sheet(soup)

        # ── F. Cash Flow ────────────────────────────────────────────────────
        data["cash_flow"] = self._parse_cash_flow(soup)

        # ── G. Financial Ratios ─────────────────────────────────────────────
        data["ratios_annual"] = self._parse_ratios(soup)

        # ── H. Shareholding ─────────────────────────────────────────────────
        data["shareholding"] = self._parse_shareholding(soup)

        # ── I. Peers ────────────────────────────────────────────────────────
        data["peers"] = self._parse_peers(soup)

        # ── J. Documents ────────────────────────────────────────────────────
        data["documents"] = self._parse_documents(soup)

        return data

    # ─── A. Key Metrics ───────────────────────────────────────────────────────

    def _parse_key_metrics(self, soup: BeautifulSoup) -> dict:
        """Parse section#top .company-ratios li"""
        result: dict[str, Any] = {}

        LABEL_MAP = {
            "market cap": "market_cap",
            "current price": "current_price",
            "stock p/e": "pe",
            "book value": "book_value",
            "dividend yield": "dividend_yield",
            "roce": "roce",
            "roe": "roe",
            "face value": "face_value",
            "52 week high": "high_52w",
            "52 week low": "low_52w",
            "eps": "eps_ttm",
            "p/b": "pb",
            "debt": "debt",
            "cash": "cash",
            "promoter holding": "promoter_holding",
        }

        # Try multiple selectors for the ratios list
        for selector in [
            "#top-ratios li",
            ".company-ratios li",
            ".flex-row li",
        ]:
            items = soup.select(selector)
            if items:
                for li in items:
                    name_tag = li.select_one(".name, span.sub")
                    value_tag = li.select_one(".value, .number, span.strong")
                    if not name_tag:
                        continue
                    label = (name_tag.get_text(separator=" ", strip=True) or "").lower()
                    raw = value_tag.get_text(separator=" ", strip=True) if value_tag else None

                    # Special case: "High / Low" label has two numbers
                    if "high" in label and "low" in label:
                        numbers = li.select(".number")
                        if len(numbers) >= 2:
                            result["high_52w"] = _num(numbers[0].get_text(strip=True))
                            result["low_52w"] = _num(numbers[1].get_text(strip=True))
                        continue

                    for fragment, key in LABEL_MAP.items():
                        if fragment in label:
                            result[key] = _num(raw)
                            break
                break

        return result

    # ─── B. About ─────────────────────────────────────────────────────────────

    def _parse_about(self, soup: BeautifulSoup) -> dict:
        """Parse about text and key points / pros / cons."""
        about_text = None
        for sel in ["#about p", ".about p", ".company-profile p", ".company-description",
                    "#top p", ".company-about p"]:
            tag = soup.select_one(sel)
            if tag:
                about_text = tag.get_text(separator=" ", strip=True)
                break

        # Screener.in uses #analysis section for pros/cons
        analysis_items = [li.get_text(strip=True) for li in soup.select("#analysis li")]
        # Heuristic: items mentioning "good", "healthy", "strong" are pros; "poor", "weak", "debt" are cons
        pros = []
        cons = []
        neg_keywords = ["poor", "weak", "declined", "negative", "high debt", "slow", "below", "deteriorat"]
        for item in analysis_items:
            lower = item.lower()
            if any(kw in lower for kw in neg_keywords):
                cons.append(item)
            else:
                pros.append(item)

        # Also try legacy selectors
        if not pros and not cons:
            pros = [li.get_text(strip=True) for li in soup.select("#pros li, .pros li")]
            cons = [li.get_text(strip=True) for li in soup.select("#cons li, .cons li")]

        return {
            "about": about_text,
            "pros": pros,
            "cons": cons,
            "key_points": analysis_items,
        }

    # ─── C. Quarterly Results ─────────────────────────────────────────────────

    def _parse_quarterly(self, soup: BeautifulSoup) -> list[dict]:
        """Parse section#quarters table — last 12 quarters."""
        section = soup.find("section", id="quarters")
        if not section:
            return []
        table = section.find("table")
        if not table:
            return []

        headers = self._thead(table)
        rows = self._tbody_map(table)

        results = []
        for i, quarter in enumerate(headers):
            results.append({
                "quarter": quarter,
                "sales": _num(self._cell(rows, ["sales", "revenue"], i)),
                "expenses": _num(self._cell(rows, ["expenses"], i)),
                "operating_profit": _num(self._cell(rows, ["operating profit"], i)),
                "opm_pct": _num(self._cell(rows, ["opm%", "opm %"], i)),
                "other_income": _num(self._cell(rows, ["other income"], i)),
                "interest": _num(self._cell(rows, ["interest"], i)),
                "depreciation": _num(self._cell(rows, ["depreciation"], i)),
                "pbt": _num(self._cell(rows, ["profit before tax"], i)),
                "tax_pct": _num(self._cell(rows, ["tax %", "tax%"], i)),
                "net_profit": _num(self._cell(rows, ["net profit"], i)),
                "eps": _num(self._cell(rows, ["eps"], i)),
            })
        return results

    # ─── D. Profit & Loss ─────────────────────────────────────────────────────

    def _parse_profit_loss(self, soup: BeautifulSoup) -> dict:
        """Parse section#profit-loss table + CAGR tables."""
        section = soup.find("section", id="profit-loss")
        if not section:
            return {}

        table = section.find("table")
        if not table:
            return {}

        headers = self._thead(table)
        rows = self._tbody_map(table)

        def history(hints: list[str]) -> list[dict]:
            key = self._find_key(rows, hints)
            if not key:
                return []
            return [{"year": h, "value": _num(v)} for h, v in zip(headers, rows[key])]

        # CAGR sub-sections (compounded growth tables below main P&L)
        sales_cagr = self._parse_cagr_list(section, "compounded-sales-growth")
        profit_cagr = self._parse_cagr_list(section, "compounded-profit-growth")
        roe_history = self._parse_cagr_list(section, "return-on-equity")
        price_cagr = self._parse_cagr_list(section, "stock-price-cagr")

        # Also try document-wide CAGR sections
        if not sales_cagr:
            sales_cagr = self._parse_cagr_list(soup, "compounded-sales-growth")
        if not profit_cagr:
            profit_cagr = self._parse_cagr_list(soup, "compounded-profit-growth")
        if not roe_history:
            roe_history = self._parse_cagr_list(soup, "return-on-equity")

        return {
            "pl_years": headers,
            "pl_sales": history(["sales", "revenue from operations"]),
            "pl_expenses": history(["expenses"]),
            "pl_operating_profit": history(["operating profit"]),
            "pl_opm_pct": history(["opm%", "opm %"]),
            "pl_other_income": history(["other income"]),
            "pl_interest": history(["interest"]),
            "pl_depreciation": history(["depreciation"]),
            "pl_pbt": history(["profit before tax", "pbt"]),
            "pl_tax_pct": history(["tax %", "tax%"]),
            "pl_net_profit": history(["net profit"]),
            "pl_eps": history(["eps"]),
            "pl_dividend_payout_pct": history(["dividend payout"]),
            "sales_growth_cagr": sales_cagr,
            "profit_growth_cagr": profit_cagr,
            "roe_history_cagr": roe_history,
            "price_cagr": price_cagr,
        }

    def _parse_cagr_list(self, scope, section_id: str) -> dict:
        """
        Parse CAGR sub-sections.
        Screener.in uses <table class='ranges-table'> inside #profit-loss for CAGR data.
        Table rows: "Compounded Sales Growth", "10 Years: 10%", "5 Years: 10%", etc.
        We match by the header row text.
        """
        # Try legacy section IDs first
        if isinstance(scope, BeautifulSoup):
            section = scope.find("section", id=section_id)
        else:
            section = scope.find(id=section_id)
            if section is None and hasattr(scope, "find_next"):
                section = scope.find_next("section", id=section_id)

        if section is not None:
            result = {}
            for li in section.select("li"):
                text = li.get_text(separator=":", strip=True)
                parts = text.split(":")
                if len(parts) == 2:
                    period = parts[0].strip().lower().replace(" ", "_")
                    result[period] = _num(parts[1])
            return result

        # New Screener.in format: <table class='ranges-table'> in profit-loss section
        # Map section_id to the header text in the ranges-table
        HEADER_MAP = {
            "compounded-sales-growth": "compounded sales growth",
            "compounded-profit-growth": "compounded profit growth",
            "return-on-equity": "return on equity",
            "stock-price-cagr": "stock price cagr",
        }
        target_header = HEADER_MAP.get(section_id, "")
        if not target_header:
            return {}

        # Search in the whole soup / scope for ranges-tables
        search_scope = scope if isinstance(scope, BeautifulSoup) else scope
        for table in search_scope.find_all("table", class_="ranges-table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            # Check if first row matches target header
            first_text = rows[0].get_text(strip=True).lower()
            if target_header in first_text:
                result = {}
                for tr in rows[1:]:
                    text = tr.get_text(separator=":", strip=True)
                    parts = [p for p in text.split(":") if p.strip()]  # filter empty parts
                    if len(parts) == 2:
                        period = parts[0].strip().lower().replace(" ", "_")
                        result[period] = _num(parts[1])
                return result
        return {}

    # ─── E. Balance Sheet ─────────────────────────────────────────────────────

    def _parse_balance_sheet(self, soup: BeautifulSoup) -> dict:
        """Parse section#balance-sheet table."""
        section = soup.find("section", id="balance-sheet")
        if not section:
            return {}
        table = section.find("table")
        if not table:
            return {}

        headers = self._thead(table)
        rows = self._tbody_map(table)

        def history(hints: list[str]) -> list[dict]:
            key = self._find_key(rows, hints)
            if not key:
                return []
            return [{"year": h, "value": _num(v)} for h, v in zip(headers, rows[key])]

        return {
            "years": headers,
            "equity_capital": history(["equity capital"]),
            "reserves": history(["reserves"]),
            "borrowings": history(["borrowings"]),
            "other_liabilities": history(["other liabilities"]),
            "total_liabilities": history(["total liabilities"]),
            "fixed_assets": history(["fixed assets", "net block"]),
            "cwip": history(["cwip", "capital work"]),
            "investments": history(["investments"]),
            "other_assets": history(["other assets"]),
            "total_assets": history(["total assets"]),
        }

    # ─── F. Cash Flow ─────────────────────────────────────────────────────────

    def _parse_cash_flow(self, soup: BeautifulSoup) -> dict:
        """Parse section#cash-flow table."""
        section = soup.find("section", id="cash-flow")
        if not section:
            return {}
        table = section.find("table")
        if not table:
            return {}

        headers = self._thead(table)
        rows = self._tbody_map(table)

        def history(hints: list[str]) -> list[dict]:
            key = self._find_key(rows, hints)
            if not key:
                return []
            return [{"year": h, "value": _num(v)} for h, v in zip(headers, rows[key])]

        return {
            "years": headers,
            "operating": history(["cash from operating", "operating activities"]),
            "investing": history(["cash from investing", "investing activities"]),
            "financing": history(["cash from financing", "financing activities"]),
            "net_cash_flow": history(["net cash"]),
        }

    # ─── G. Financial Ratios ──────────────────────────────────────────────────

    def _parse_ratios(self, soup: BeautifulSoup) -> dict:
        """Parse section#ratios table."""
        section = soup.find("section", id="ratios")
        if not section:
            return {}
        table = section.find("table")
        if not table:
            return {}

        headers = self._thead(table)
        rows = self._tbody_map(table)

        def history(hints: list[str]) -> list[dict]:
            key = self._find_key(rows, hints)
            if not key:
                return []
            return [{"year": h, "value": _num(v)} for h, v in zip(headers, rows[key])]

        return {
            "years": headers,
            "debtor_days": history(["debtor days"]),
            "inventory_days": history(["inventory days"]),
            "days_payable": history(["days payable"]),
            "cash_conversion_cycle": history(["cash conversion"]),
            "working_capital_days": history(["working capital days"]),
            "roce_pct": history(["roce"]),
        }

    # ─── H. Shareholding ──────────────────────────────────────────────────────

    def _parse_shareholding(self, soup: BeautifulSoup) -> dict:
        """Parse section#shareholding table — returns latest quarter."""
        section = soup.find("section", id="shareholding")
        if not section:
            return {}
        table = section.find("table")
        if not table:
            return {}

        headers = self._thead(table)
        rows = self._tbody_map(table)

        # Use latest column (last header)
        idx = -1

        def latest(hints: list[str]) -> Optional[float]:
            key = self._find_key(rows, hints)
            if key and rows[key]:
                vals = rows[key]
                return _num(vals[idx] if len(vals) >= abs(idx) else vals[-1])
            return None

        # Full historical data for promoters
        promoter_key = self._find_key(rows, ["promoters", "promoter"])
        promoter_history = []
        if promoter_key:
            promoter_history = [
                {"quarter": h, "value": _num(v)}
                for h, v in zip(headers, rows[promoter_key])
            ]

        return {
            "latest_quarter": headers[idx] if headers else None,
            "promoters": latest(["promoters", "promoter"]),
            "fiis": latest(["fii", "foreign institutional"]),
            "diis": latest(["dii", "domestic institutional"]),
            "government": latest(["government"]),
            "public": latest(["public"]),
            "num_shareholders": latest(["no. of shareholders", "shareholders"]),
            "promoter_history": promoter_history,
        }

    # ─── I. Peers ─────────────────────────────────────────────────────────────

    def _parse_peers(self, soup: BeautifulSoup) -> list[dict]:
        """Parse section#peers table."""
        section = soup.find("section", id="peers")
        if not section:
            return []
        table = section.find("table")
        if not table:
            return []

        thead = table.find("thead")
        col_headers = []
        if thead:
            col_headers = [
                th.get_text(strip=True).lower()
                for th in thead.find_all("th")
            ]

        tbody = table.find("tbody")
        if not tbody:
            return []

        peers = []
        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue

            name_tag = cells[0].find("a")
            name = _txt(name_tag) if name_tag else _txt(cells[0])
            href = name_tag.get("href", "") if name_tag else ""
            ticker = href.rstrip("/").split("/")[-1] if href else None

            # Try to match columns by header
            peer: dict[str, Any] = {
                "name": name,
                "symbol": ticker,
            }
            for j, col in enumerate(col_headers[1:], start=1):
                if j < len(cells):
                    val = cells[j].get_text(strip=True)
                    if "p/e" in col or "pe" == col:
                        peer["pe"] = _num(val)
                    elif "mar cap" in col or "market cap" in col:
                        peer["market_cap"] = _num(val)
                    elif "roce" in col:
                        peer["roce"] = _num(val)
                    elif "roe" in col:
                        peer["roe"] = _num(val)
                    elif "sales" in col:
                        peer["sales"] = _num(val)
                    elif "profit" in col and "growth" in col:
                        peer["profit_growth"] = _num(val)
                    elif "cmp" in col or "price" in col:
                        peer["price"] = _num(val)
                    elif "p/b" in col or "pb" == col:
                        peer["pb"] = _num(val)
                    elif "div" in col:
                        peer["dividend_yield"] = _num(val)
            peers.append(peer)

        return peers

    # ─── J. Documents ─────────────────────────────────────────────────────────

    def _parse_documents(self, soup: BeautifulSoup) -> list[dict]:
        """Parse section#documents — last 10 announcements."""
        section = soup.find("section", id="documents")
        if not section:
            return []
        docs = []
        for item in section.select("li, .document-item")[:10]:
            title_tag = item.select_one("a, .title")
            date_tag = item.select_one(".date, time")
            docs.append({
                "title": _txt(title_tag),
                "date": _txt(date_tag),
                "href": title_tag.get("href") if title_tag else None,
            })
        return docs

    # ─── Table utilities ──────────────────────────────────────────────────────

    def _thead(self, table: Tag) -> list[str]:
        thead = table.find("thead")
        if not thead:
            return []
        ths = thead.find_all("th")
        return [th.get_text(strip=True) for th in ths][1:]  # skip label col

    def _tbody_map(self, table: Tag) -> dict[str, list[str]]:
        rows: dict[str, list[str]] = {}
        tbody = table.find("tbody")
        if not tbody:
            return rows
        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower()
            values = [c.get_text(strip=True) for c in cells[1:]]
            rows[label] = values
        return rows

    def _find_key(self, rows: dict, hints: list[str]) -> Optional[str]:
        for hint in hints:
            for key in rows:
                if hint.lower() in key:
                    return key
        return None

    def _cell(self, rows: dict, hints: list[str], index: int) -> Optional[str]:
        key = self._find_key(rows, hints)
        if key is None:
            return None
        vals = rows[key]
        if index < len(vals):
            return vals[index]
        return None
