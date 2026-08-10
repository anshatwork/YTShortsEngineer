---
name: search-retrieval
description: Guide for search/discovery/retrieval features in this repo — YouTube Data API quota, asset/music retrieval + ranking, conversational query interpretation, trending pool, caching. Use when working on discover/music/search endpoints or asset ranking.
---

# Search & Retrieval

Covers the existing search surfaces (discover, music, assets, trending) and how to extend them.
Context: `docs/claude/tools.md` (tools/assets, tools/youtube), API section of `architecture.md`.

## YouTube Data API — mind the quota
- `search.list` = **100 units/call**; `videos.list` details enrich adds more; `trending_music`
  (chart) = **1 unit**. Prefer chart/trending endpoints and **cache** search results (music search
  is TTL-cached). Don't call `search.list` in a loop.
- Long-form discovery defaults to ≥1200s; discovery duration floor is 30s. Region via
  `YT_TRENDING_REGION`.
- **All calls route through `tools/youtube/quota.py` + `_execute_with_backoff`** — one shared daily
  budget (`YOUTUBE_DAILY_QUOTA`, midnight-Pacific reset) that the crawler *and* discovery charge
  against. Daily-quota exhaustion raises `QuotaExceededError` (NOT retryable — degrade to the cached
  pool); transient rate-limit/5xx retry with exponential backoff+jitter. Per-query results are
  TTL-cached (`YT_SEARCH_CACHE_TTL_HOURS`, 0 units on a hit). The crawler skips below
  `YT_QUOTA_RESERVE` and refreshes only a rotating subset of topics per cycle.

## Asset/music retrieval (the registry pattern)
- Entry: `tools.assets.retrieve(AssetQuery(...), k)`. **Cache-first** — only hits the network when
  the pool is stale (`ASSET_FRESHNESS_TTL_HOURS`, `ASSET_MIN_POOL`).
- Sources iterate in **registration order = tier priority** (Jamendo → Pixabay → Freesound).
  YouTube music is deliberately NOT auto-registered (copyright); it's added only on manual pick and
  carries a `COPYRIGHT_WARNING`.
- Ranking `_rank` blends freshness + popularity + keyword overlap, weighted by `order`
  (latest/popular/relevance). `_personalization_bias` is a v1 stub — the seam for future
  personalization (`docs/future/memory-system.md`).

## Conversational query interpretation
- Discover and music search accept natural-language queries interpreted by
  `interpret_discover_query` / `interpret_music_query` → `get_llm().parse(..., Interpretation)`.
- **Always degrade to plain keyword search** on any LLM failure (existing behavior — preserve it).

## Trending pool
- Warmed by a background task (`trending_crawler`) on the queue (`TRENDING_CRAWLER_HOURS`);
  `/discover/suggestions` ranks the pool against LLM-inferred user interests (last ~40 jobs).
- Prefer the static `TRENDING_QUERY_BANK`; the optional LLM-query path `eval`s output — avoid it.

## Extending
- [ ] New source → implement `AssetSource` (`available/discover/fetch`), register in
      `sources/__init__.py`, gate `available()` on a real (non-placeholder) env key via
      `_env.configured`.
- [ ] Cache results; respect TTL/LRU; never evict `user_*`/`songs`.
- [ ] For semantic search over media, use the shared embedding + pgvector stack — see the
      `rag-indexing` skill and `docs/future/video-sourcing.md`.
- [ ] SSRF: downloads from arbitrary hosts must go through a host allowlist (see music_routes
      `_ALLOWED_DOWNLOAD_HOSTS`).

## Review with: `architecture-review`, `performance-optimization`, `rag-indexing`.
