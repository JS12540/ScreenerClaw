"""
ScreenerClaw — Parallel Web Search Client

All three backends run SIMULTANEOUSLY via asyncio.gather:
  - OpenAI Responses API  (gpt-4.1-mini + web_search_preview tool)
  - Groq Compound         (compound-beta-mini, built-in web search)
  - DuckDuckGo            (free, no API key, always available)

Results from all available backends are merged and deduplicated.
Multiple search queries also run in parallel.

Optional URL enrichment (enrich_with_crawl):
  After search, call enrich_with_crawl(results) to fetch full article text
  from the top DDG URLs. Uses WebCrawler (trafilatura → readability → BS4).
  Turns 200-char DDG snippets into 4000-char full articles for the LLM.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from backend.logger import get_logger

logger = get_logger(__name__)

# Limit concurrent DuckDuckGo requests — hitting DDG with 6 simultaneous
# requests triggers rate limiting (HTTP 202 / empty results).
# Max 2 concurrent DDG calls; others queue and run when a slot frees up.
_DDG_SEMAPHORE = asyncio.Semaphore(2)


class SearchResult:
    __slots__ = ("title", "url", "content", "score", "source")

    def __init__(
        self,
        title: str,
        url: str,
        content: str,
        score: float = 0.0,
        source: str = "unknown",
    ):
        self.title = title
        self.url = url
        self.content = content
        self.score = score
        self.source = source  # "openai" | "groq" | "duckduckgo"

    def to_context_block(self) -> str:
        header = f"**{self.title}**" if self.title else ""
        source = f"\nSource: {self.url}" if self.url else ""
        tag = f" [{self.source}]" if self.source else ""
        return f"{header}{tag}\n{self.content}{source}".strip()


class WebSearchClient:
    """
    Async web search client.
    Runs OpenAI + Groq + DuckDuckGo in PARALLEL and merges all results.
    Multiple queries are also gathered concurrently.
    """

    def __init__(self) -> None:
        from backend.config import settings
        self._settings = settings

    # OpenAI web search disabled — uncomment to re-enable (requires openai package + OPENAI_API_KEY)
    # @property
    # def _has_openai(self) -> bool:
    #     return bool(self._settings.openai_api_key)

    @property
    def _has_groq(self) -> bool:
        return bool(self._settings.groq_api_key)

    # ── Single query — all backends in parallel ───────────────────────────────

    async def search(
        self,
        query: str,
        num_results: int = 5,
        search_depth: str = "basic",
    ) -> list[SearchResult]:
        """
        Search one query across ALL available backends in parallel.
        Returns merged results from all sources.
        """
        t0 = time.monotonic()
        tasks: list[asyncio.Task] = []

        # OpenAI web search disabled — uncomment to re-enable
        # if self._has_openai:
        #     tasks.append(asyncio.create_task(self._openai_search(query)))
        if self._has_groq:
            tasks.append(asyncio.create_task(self._groq_search(query)))
        tasks.append(asyncio.create_task(self._ddg_search(query, num_results)))

        raw = await asyncio.gather(*tasks, return_exceptions=True)

        merged: list[SearchResult] = []
        sources_hit = []
        for result in raw:
            if isinstance(result, list) and result:
                merged.extend(result)
                sources_hit.append(result[0].source if result else "?")
            elif isinstance(result, Exception):
                logger.warning(
                    "Search backend failed",
                    extra={"query": query[:60], "error": str(result)},
                )

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            "Web search complete",
            extra={
                "query": query[:80],
                "results": len(merged),
                "sources": sources_hit,
                "elapsed_ms": round(elapsed, 1),
            },
        )
        return merged

    async def search_news(self, query: str, num_results: int = 5) -> list[SearchResult]:
        return await self.search(f"latest news: {query}", num_results)

    # ── Multiple queries — all in parallel ───────────────────────────────────

    async def search_many(
        self,
        queries: list[str],
        num_results: int = 3,
    ) -> list[SearchResult]:
        """
        Run multiple queries ALL IN PARALLEL (both across queries and backends).
        Returns merged deduplicated results from all queries × all backends.
        """
        if not queries:
            return []

        t0 = time.monotonic()
        logger.info(
            "Parallel multi-query search starting",
            extra={"num_queries": len(queries), "queries": [q[:60] for q in queries]},
        )

        results_per_query = await asyncio.gather(
            *[self.search(q, num_results=num_results) for q in queries],
            return_exceptions=True,
        )

        merged: list[SearchResult] = []
        for r in results_per_query:
            if isinstance(r, list):
                merged.extend(r)

        # Deduplicate by content fingerprint (first 100 chars)
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for result in merged:
            key = result.content[:100].strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(result)

        elapsed = (time.monotonic() - t0) * 1000
        if not deduped:
            logger.warning(
                "All search backends returned zero results — LLM will use Screener.in data only",
                extra={"queries": len(queries), "elapsed_ms": round(elapsed, 1)},
            )
        else:
            logger.info(
                "Parallel multi-query search complete",
                extra={
                    "queries": len(queries),
                    "raw_results": len(merged),
                    "deduped_results": len(deduped),
                    "elapsed_ms": round(elapsed, 1),
                },
            )
        return deduped

    async def enrich_with_crawl(
        self,
        results: list[SearchResult],
        max_urls: int = 3,
    ) -> list[SearchResult]:
        """
        Fetch full article text for the top *max_urls* results that have a URL.

        Replaces the short DDG snippet (.content ~200 chars) with the full
        crawled page text (~4000 chars). Groq results (no URL) are unchanged.

        Uses WebCrawler: trafilatura → readability-lxml → BeautifulSoup4.
        All three are pure pip installs — no browser binaries needed.

        Example:
            results = await client.search_many(queries)
            enriched = await client.enrich_with_crawl(results, max_urls=3)
            context = client.format_results_for_llm(enriched)
        """
        from backend.data.web_crawl import WebCrawler
        crawler = WebCrawler()
        return await crawler.enrich_results(results, max_urls=max_urls)

    def format_results_for_llm(self, results: list[SearchResult], max_chars: int = 8000) -> str:
        """Format merged search results into a context block for LLM consumption."""
        if not results:
            return "No search results found."

        blocks: list[str] = []
        total = 0
        for i, r in enumerate(results, 1):
            block = f"[{i}] {r.to_context_block()}\n"
            if total + len(block) > max_chars:
                break
            blocks.append(block)
            total += len(block)

        return "\n".join(blocks)

    # ── OpenAI Responses API ──────────────────────────────────────────────────
    # OpenAI web search disabled — uncomment to re-enable (requires openai package + OPENAI_API_KEY)

    # async def _openai_search(self, query: str) -> list[SearchResult]:
    #     import openai as _openai
    #
    #     client = _openai.AsyncOpenAI(api_key=self._settings.openai_api_key)
    #     model = self._settings.execution_model or "gpt-4.1-mini"
    #
    #     logger.debug("OpenAI web search", extra={"query": query[:60], "model": model})
    #
    #     response = await client.responses.create(
    #         model=model,
    #         tools=[{"type": "web_search_preview"}],
    #         input=query,
    #     )
    #
    #     content = response.output_text or ""
    #     if not content:
    #         raise ValueError("OpenAI Responses API returned empty content")
    #
    #     return [SearchResult(
    #         title=f"Web search: {query[:80]}",
    #         url="",
    #         content=content,
    #         score=1.0,
    #         source="openai",
    #     )]

    # ── Groq Compound ─────────────────────────────────────────────────────────

    async def _groq_search(self, query: str) -> list[SearchResult]:
        import groq as _groq

        client = _groq.Groq(api_key=self._settings.groq_api_key)

        logger.debug("Groq Compound web search", extra={"query": query[:60]})

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="compound-beta-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a research assistant. Search the web and provide "
                            "factual, up-to-date information. Be concise but thorough."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                max_tokens=800,
            ),
        )

        content = response.choices[0].message.content or ""
        if not content:
            raise ValueError("Groq Compound returned empty content")

        return [SearchResult(
            title=f"Web search: {query[:80]}",
            url="",
            content=content,
            score=0.9,
            source="groq",
        )]

    # ── DuckDuckGo ────────────────────────────────────────────────────────────

    async def _ddg_search(self, query: str, num_results: int) -> list[SearchResult]:
        """
        DuckDuckGo search with semaphore (max 2 concurrent) and retry (up to 2 attempts).
        The semaphore prevents rate-limiting when many queries run in parallel.
        """
        from ddgs import DDGS

        async with _DDG_SEMAPHORE:
            for attempt in range(2):
                try:
                    logger.debug(
                        "DuckDuckGo search",
                        extra={"query": query[:60], "attempt": attempt + 1},
                    )

                    def _sync_search() -> list[dict]:
                        with DDGS() as ddgs:
                            return list(ddgs.text(query, max_results=num_results))

                    loop = asyncio.get_event_loop()
                    raw = await loop.run_in_executor(None, _sync_search)

                    if raw:
                        return [
                            SearchResult(
                                title=r.get("title", ""),
                                url=r.get("href", ""),
                                content=r.get("body", ""),
                                score=0.7,
                                source="duckduckgo",
                            )
                            for r in raw
                        ]
                    # DDG returned empty list (rate-limited) — wait and retry
                    if attempt == 0:
                        logger.debug(
                            "DuckDuckGo returned empty — retrying after 1s",
                            extra={"query": query[:60]},
                        )
                        await asyncio.sleep(1.0)

                except Exception as exc:
                    logger.warning(
                        "DuckDuckGo search failed",
                        extra={"error": str(exc), "query": query[:60], "attempt": attempt + 1},
                    )
                    if attempt == 0:
                        await asyncio.sleep(1.0)

            logger.warning(
                "DuckDuckGo gave no results after retries",
                extra={"query": query[:60]},
            )
            return []

    async def _ddg_news_search(self, query: str, num_results: int) -> list[SearchResult]:
        try:
            from ddgs import DDGS

            def _sync_news() -> list[dict]:
                with DDGS() as ddgs:
                    return list(ddgs.news(query, max_results=num_results))

            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(None, _sync_news)

            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    content=r.get("body", ""),
                    score=0.7,
                    source="duckduckgo",
                )
                for r in raw
            ]
        except Exception as exc:
            logger.warning("DuckDuckGo news search failed", extra={"error": str(exc)})
            return []


# ── Pre-built Search Query Templates ─────────────────────────────────────────

def build_business_search_queries(company_name: str, sector: str) -> list[str]:
    return [
        f'"{company_name}" annual report business model revenue segments 2024 2025 site:screener.in OR site:bseindia.com OR site:nseindia.com OR site:moneycontrol.com',
        f'"{company_name}" competitive advantage moat India {sector} investor presentation',
        f'"{company_name}" management commentary concall Q3 Q4 FY2025 outlook guidance',
    ]


def build_macro_search_queries(company_name: str, sector: str) -> list[str]:
    return [
        f"India {sector} sector outlook FY2025 FY2026 macro headwinds tailwinds",
        f"RBI monetary policy interest rate cut impact India {sector} stocks 2025",
        f"{company_name} raw material cost INR USD China competition impact 2025",
    ]


def build_news_search_queries(company_name: str) -> list[str]:
    return [
        f'"{company_name}" quarterly results earnings FY2025 Q3 Q4 India stock',
        f'"{company_name}" news 2025 analyst rating target price India',
    ]
