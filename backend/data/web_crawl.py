"""
ScreenerClaw — Web Crawler / URL Content Fetcher

Fetches full article/page content from URLs returned by DuckDuckGo or Groq
search results. Turns short DDG snippets (~200 chars) into full article text
(3000–6000 chars) for much richer LLM context.

3-tier fallback — all pure pip install, zero browser binaries, server-safe:

  Tier 1: trafilatura  — best-in-class article extraction (used by HuggingFace,
                          Microsoft Research). Strips nav/ads/boilerplate perfectly.
  Tier 2: readability-lxml — Mozilla Readability algorithm ported to Python.
                              Good fallback for pages trafilatura under-extracts.
  Tier 3: BeautifulSoup 4  — manual visible-text extraction. Already a dep.

A single httpx async request fetches the HTML; all three extractors operate on
the same HTML bytes — no duplicate network calls.

Usage:

    from backend.data.web_crawl import WebCrawler

    crawler = WebCrawler()

    # Fetch a single URL
    text = await crawler.fetch_url("https://economictimes.indiatimes.com/...")

    # Enrich a list of SearchResult objects with full article text
    enriched = await crawler.enrich_results(search_results, max_urls=3)
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from backend.logger import get_logger

logger = get_logger(__name__)

# Browser-like headers — reduces 403s from news sites
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Note: do NOT set Accept-Encoding manually — let httpx negotiate it.
    # Setting "br" without the `brotli` package installed causes garbled output.
}

# Semaphore — don't blast financial sites with too many concurrent fetches
_CRAWL_SEMAPHORE = asyncio.Semaphore(4)

# Minimum extracted text length to consider a tier "successful"
_MIN_TEXT_LEN = 150


class WebCrawler:
    """
    Async URL content fetcher with 3-tier fallback.

    Fetches HTML once, tries extractors in order:
      trafilatura → readability-lxml → BeautifulSoup 4
    """

    # ── Public API ────────────────────────────────────────────────────────────

    async def fetch_url(self, url: str, max_chars: int = 6000) -> str:
        """
        Fetch and extract clean article text from *url*.

        Returns extracted text (up to *max_chars*) or "" on failure.
        Internally: one httpx GET → trafilatura → readability → BS4.
        """
        if not url or not url.startswith(("http://", "https://")):
            return ""

        async with _CRAWL_SEMAPHORE:
            html = await self._fetch_html(url)

        if not html:
            return ""

        # Try each extractor on the same HTML — no extra network calls
        for tier_name, extractor in [
            ("trafilatura", self._trafilatura_extract),
            ("readability", self._readability_extract),
            ("bs4", self._bs4_extract),
        ]:
            try:
                loop = asyncio.get_event_loop()
                text = await loop.run_in_executor(None, extractor, html, url)
                if text and len(text.strip()) >= _MIN_TEXT_LEN:
                    text = text[:max_chars].strip()
                    logger.debug(
                        "URL content fetched",
                        extra={
                            "tier": tier_name,
                            "url": url[:80],
                            "chars": len(text),
                        },
                    )
                    return text
            except Exception as exc:
                logger.debug(
                    "Crawl tier failed",
                    extra={
                        "tier": tier_name,
                        "url": url[:80],
                        "error": str(exc)[:120],
                    },
                )

        logger.warning("All crawl tiers failed for URL", extra={"url": url[:80]})
        return ""

    async def enrich_results(
        self,
        results: list,
        max_urls: int = 3,
        max_chars_per_page: int = 4000,
    ) -> list:
        """
        Enrich a list of SearchResult objects with full page content.

        Picks the top *max_urls* results that have a real HTTP URL (e.g. from
        DuckDuckGo), fetches them all in parallel, and replaces their .content
        with the full article text. Results without a URL (e.g. Groq) are kept
        as-is.

        Returns a new list — does not mutate the input.
        """
        from backend.data.web_search import SearchResult  # late import — avoid circular

        # Only crawl results that have a real URL
        crawlable = [r for r in results if r.url and r.url.startswith("http")][:max_urls]

        if not crawlable:
            return list(results)

        # Fetch all in parallel
        fetched_texts = await asyncio.gather(
            *[self.fetch_url(r.url, max_chars=max_chars_per_page) for r in crawlable],
            return_exceptions=True,
        )

        url_to_text: dict[str, str] = {}
        for r, text in zip(crawlable, fetched_texts):
            if isinstance(text, str) and text:
                url_to_text[r.url] = text

        enriched: list = []
        for r in results:
            if r.url in url_to_text:
                enriched.append(
                    SearchResult(
                        title=r.title,
                        url=r.url,
                        content=url_to_text[r.url],
                        score=min(r.score + 0.1, 1.0),
                        source=f"{r.source}+crawl",
                    )
                )
            else:
                enriched.append(r)

        logger.info(
            "Search results enriched",
            extra={
                "input": len(results),
                "crawled": len(url_to_text),
                "requested": max_urls,
            },
        )
        return enriched

    # ── HTML Fetcher ──────────────────────────────────────────────────────────

    async def _fetch_html(self, url: str) -> Optional[str]:
        """Async HTTP GET — returns raw HTML string or None on error."""
        try:
            async with httpx.AsyncClient(
                headers=_HEADERS,
                timeout=12.0,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPStatusError as exc:
            logger.debug(
                "HTTP error fetching URL",
                extra={"url": url[:80], "status": exc.response.status_code},
            )
        except Exception as exc:
            logger.debug(
                "Failed to fetch URL",
                extra={"url": url[:80], "error": str(exc)[:100]},
            )
        return None

    # ── Tier 1: trafilatura ───────────────────────────────────────────────────

    @staticmethod
    def _trafilatura_extract(html: str, url: str) -> str:
        """
        Best-in-class article extractor. Strips ads, nav, footers perfectly.
        Used by HuggingFace and Microsoft Research for web corpus building.
        """
        import trafilatura

        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,       # prefer more text over precision
        )
        return text or ""

    # ── Tier 2: readability-lxml ──────────────────────────────────────────────

    @staticmethod
    def _readability_extract(html: str, url: str) -> str:
        """
        Mozilla Readability algorithm — the same logic Firefox Reader View uses.
        Good fallback for pages with heavy layout boilerplate.
        """
        from readability import Document

        doc = Document(html)
        summary_html = doc.summary(html_partial=True)

        # Strip the summary's HTML tags to get plain text
        soup = BeautifulSoup(summary_html, "lxml")
        text = soup.get_text(separator="\n", strip=True)

        # Collapse blank lines
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines)

    # ── Tier 3: BeautifulSoup 4 ───────────────────────────────────────────────

    @staticmethod
    def _bs4_extract(html: str, url: str) -> str:
        """
        Manual text extraction — strips boilerplate tags, finds main content
        block, returns all visible text. Always available (beautifulsoup4 is
        already a core dependency).
        """
        soup = BeautifulSoup(html, "lxml")

        # Remove clearly non-content tags
        for tag in soup(["script", "style", "nav", "footer", "aside",
                         "header", "form", "noscript", "iframe", "svg"]):
            tag.decompose()

        # Try to isolate the main content block
        main = (
            soup.find("article")
            or soup.find("main")
            or soup.find(id=re.compile(r"content|article|main|body", re.I))
            or soup.find(class_=re.compile(r"article|content|main|story|post", re.I))
            or soup.body
        )
        target = main if main else soup

        text = target.get_text(separator="\n", strip=True)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines)
