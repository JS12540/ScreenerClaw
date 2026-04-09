"""
Smoke test for WebCrawler and WebSearchClient.enrich_with_crawl().

Run with:
    cd screener_agent
    .venv/Scripts/python tests/test_web_crawl.py
"""
import asyncio
import sys
import os

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Project root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Minimal env so backend.config does not error on missing keys
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("SCREENER_USERNAME", "")
os.environ.setdefault("SCREENER_PASSWORD", "")

from backend.data.web_crawl import WebCrawler
from backend.data.web_search import SearchResult


DIVIDER = "-" * 60

# Public financial news pages for testing
TEST_URLS = [
    ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/stocks/news"),
    ("Moneycontrol Markets",   "https://www.moneycontrol.com/news/business/markets/"),
    ("Mint Markets",           "https://www.livemint.com/market/stock-market-news"),
]


# ── Test 1: fetch individual URLs ─────────────────────────────────────────────

async def test_fetch_url():
    print(f"\n{DIVIDER}")
    print("TEST 1: WebCrawler.fetch_url()")
    print(DIVIDER)

    crawler = WebCrawler()

    for name, url in TEST_URLS:
        print(f"\n  [{name}]")
        print(f"  URL: {url}")
        try:
            text = await crawler.fetch_url(url, max_chars=400)
            if text:
                preview = text[:200].replace("\n", " ")
                print(f"  PASS  {len(text)} chars extracted")
                print(f"  Preview: {preview[:180]}...")
            else:
                print("  SKIP  Empty result (site blocked scraping or JS-only)")
        except Exception as e:
            print(f"  FAIL  Error: {e}")


# ── Test 2: enrich_results with mock SearchResults ────────────────────────────

async def test_enrich_results():
    print(f"\n{DIVIDER}")
    print("TEST 2: WebCrawler.enrich_results() with mock SearchResults")
    print(DIVIDER)

    mock_results = [
        SearchResult(
            title="TCS Q4 FY2025 Results — ET",
            url="https://economictimes.indiatimes.com/markets/stocks/news",
            content="TCS reported strong Q4 results...",   # short DDG snippet
            score=0.7,
            source="duckduckgo",
        ),
        SearchResult(
            title="Groq compound result (no URL)",
            url="",
            content="Based on web search, TCS revenue grew 10% YoY in Q4 FY2025.",
            score=0.9,
            source="groq",
        ),
        SearchResult(
            title="Mint stock news",
            url="https://www.livemint.com/market/stock-market-news",
            content="Indian markets closed higher on Friday...",
            score=0.7,
            source="duckduckgo",
        ),
    ]

    print(f"\n  Input : {len(mock_results)} results")
    print("          2 DuckDuckGo results with URLs  -> will be crawled")
    print("          1 Groq result without URL       -> kept as-is")

    crawler = WebCrawler()
    enriched = await crawler.enrich_results(mock_results, max_urls=2, max_chars_per_page=400)

    print(f"\n  Output: {len(enriched)} results\n")
    for orig, enr in zip(mock_results, enriched):
        was_crawled = "+crawl" in enr.source
        status = "ENRICHED" if was_crawled else "unchanged"
        print(f"  [{status:8s}]  {enr.title}")
        print(f"    source : {enr.source}")
        print(f"    content: {len(enr.content)} chars  (was {len(orig.content)} chars)")
        if was_crawled and enr.content:
            preview = enr.content[:120].replace("\n", " ")
            print(f"    preview: {preview}...")
        print()


# ── Test 3: individual extractor tiers ────────────────────────────────────────

async def test_individual_tiers():
    print(f"\n{DIVIDER}")
    print("TEST 3: Individual extractor tiers (trafilatura / readability / bs4)")
    print(DIVIDER)

    import httpx

    url = "https://economictimes.indiatimes.com/markets/stocks/news"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    print(f"\n  Fetching HTML from:\n  {url}\n")
    try:
        async with httpx.AsyncClient(headers=headers, timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(url)
            html = resp.text
        print(f"  HTML size: {len(html):,} chars")
    except Exception as e:
        print(f"  Could not fetch HTML: {e}")
        return

    crawler = WebCrawler()
    loop = asyncio.get_event_loop()

    for tier_name, method in [
        ("trafilatura", crawler._trafilatura_extract),
        ("readability",  crawler._readability_extract),
        ("bs4",          crawler._bs4_extract),
    ]:
        try:
            text = await loop.run_in_executor(None, method, html, url)
            if text and len(text.strip()) >= 150:
                preview = text[:100].replace("\n", " ")
                print(f"\n  [{tier_name:12s}]  PASS  {len(text):,} chars")
                print(f"               {preview}...")
            else:
                print(f"\n  [{tier_name:12s}]  SKIP  too short / empty ({len(text) if text else 0} chars)")
        except Exception as e:
            print(f"\n  [{tier_name:12s}]  FAIL  {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("\nScreenerClaw WebCrawler Smoke Test")
    print("Libraries: trafilatura, readability-lxml, BeautifulSoup4")

    await test_individual_tiers()
    await test_fetch_url()
    await test_enrich_results()

    print(DIVIDER)
    print("Done.")
    print(DIVIDER)


if __name__ == "__main__":
    asyncio.run(main())
