---
name: screener-claw-agents
version: 1.0.0
description: Operational guidelines for all ScreenerClaw agents
---

# Pipeline (5 Steps)
1. **BusinessAgent** — Business model, moat, management quality (Greenwald framework)
2. **MacroAgent** — India macro + geopolitical impact (quantified EPS impact)
3. **ReportAgent** — Outlook: what happens in 12-24 months, catalysts and risks
4. **AssumptionsAgent + VerdictAgent** — Valuation assumptions + buy range tiers
5. **RankingAgent** — Composite score with capital-safety weighted scoring

# Memory Protocol
- After every single-stock analysis, write learnings to `agent_skills/memory/`
- Sector learnings → `agent_skills/memory/sectors/<sector_slug>.md`
- Company learnings → `agent_skills/memory/companies/<ticker>.md`
- Market cycle observations → `agent_skills/memory/market/observations.md`
- Always read relevant memory files before starting analysis

# Skill Loading
- Each agent loads its system prompt from its own `SKILL.md`
- Skill files can be edited to update agent behaviour without code changes
- Skills are versioned — increment version when making significant changes

# Red Lines
- Never fabricate financial data — use only Screener.in scraped data
- Never recommend a stock without a valuation anchor
- Never skip the risk matrix — it is mandatory in every analysis
- Never use vague language ("could", "may", "might") without a probabilistic qualifier

# Web Search
- Primary: DuckDuckGo (always available, no API key)
- Secondary: Groq Compound (requires GROQ_API_KEY)
- OpenAI web search: disabled (see web_search.py to re-enable)
- All queries use targeted India-specific templates from `build_*_search_queries()`

# Scoring Weights
| Component | Weight |
|-----------|--------|
| Valuation | 30% |
| Business Quality | 20% |
| Growth (Forward) | 20% |
| Growth (Past) | 10% |
| Financial Health | 10% |
| Business Outlook | 10% |
