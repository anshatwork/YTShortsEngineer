# Autonomous Publishing Agent

The publishing agent turns the clip generator into an **intelligent publishing assistant**: the
human makes exactly **two** decisions — approve the source video, approve the upload — and
discovery, ranking, generation, scoring, evaluation, revision and selection run autonomously,
explainably, resumably, and cheaply on local Ollama. It is **additive**: it wraps the existing clip
pipeline (Stage 2) and upload runner unchanged, and adds three layers around them.

## The three new layers

1. **Inference scheduler** (`core/inference/` + `tools/llm/inference.py`) — the single choke point
   for every LLM call. `core/inference` is a generic priority executor (stdlib only, imports nothing
   upward); `tools/llm/inference.py` is the LLM adapter (cache-first via `core.cache`, model-tier
   routing, BYOK carry-through, retries). **Nodes call `get_inference_client()`, never Ollama
   directly.** Priorities: `CRITICAL` (approval-blocking), `INTERACTIVE`, `BACKGROUND`. Default
   `INFERENCE_MAX_CONCURRENCY=1` serialises inference on a single GPU.

2. **Review sub-graph** (`agents/publishing/`) — mirrors the `agents/ingestion` template. Compiled
   `publishing_review_app`: `scoring → eval → (revise ↺ eval) → END`.
   - `scoring_node` — Stage 3. Deterministic, no-LLM multi-factor `ScoreCard`; keeps top-K
     (`PUBLISH_SCORE_KEEP`) into eval so the GPU never scores clips that can't win.
   - `eval_agent_node` — Stage 4. The **Eval Agent** — evaluates only, never generates. Emits strict
     `EvalReport` JSON; `passed` is derived purely from numbers (`EVAL_PASS_THRESHOLD` +
     `EVAL_MIN_DIMENSION`), never prose. Degrades to a neutral verdict on LLM error.
   - `revise_node` — regenerates the flagged text metadata; increments `revision_count` **even on
     failure** so the loop is always bounded (`PUBLISH_MAX_REVISIONS`).
   - `discovery_agent.py` — Stage 1. Reuses `fetch_trending_videos`/`_rank_videos`, adds explainable
     recommendations (why selected, expected clip quality, hook potential, topic relevance).

3. **Durable orchestration** (`agents/long_to_shorts/api/`) — a store-driven state machine, **not** a
   LangGraph checkpointer.
   - `publishing_store` (`publishing_jobs` table, migration `011_publishing.sql`) is the source of
     truth; wrapped in `EventEmittingStore` (channel `publish:<id>`) for SSE.
   - `publishing_orchestrator.py` — pure, testable transition logic (used by runner + routes).
   - `publishing_runner.py::run_publishing_step` — the self-contained task-queue step; one stage per
     call, stops at a gate/terminal. `recover_publishing_jobs()` re-enqueues resumable jobs after a
     crash (steps are idempotent via CAS + upload idempotency keys).
   - `youtube_service.py` — clean facade over search/rank + the resumable, idempotent upload runner,
     plus lightweight quota accounting.
   - `publishing_routes.py` — `POST /publishing`, `GET /publishing[/{id}]`, the two approval
     endpoints, `GET /publishing/metrics`; SSE at `/publishing/{id}/events` (`events_routes.py`).

## State machine (`core/execution/lifecycle.py`, `PUB_*`)

```
DISCOVERING → WAITING_FOR_SOURCE_APPROVAL → GENERATING → SCORING → EVALUATING
   → (REVISING ↺ EVALUATING) → WAITING_FOR_UPLOAD_APPROVAL → UPLOADING → COMPLETE
   (any → FAILED / CANCELLED)
```

`WAITING_FOR_*` are the only non-terminal states with no queued work — they idle until an approval
endpoint fires. `SCORING/EVALUATING/REVISING` are advanced automatically by the review sub-graph's
`node_stage` (guarded by `can_transition_publishing`). The `generating|scoring|evaluating|revising`
statuses all map to the runner's generate-and-review step: `GENERATING` regenerates fresh; the others
mean a crash mid-review, so the already-generated clips are reloaded from `clip_job_id`.

## Human decisions (only two)

- `POST /publishing/{id}/approve-source` — `approve` (needs `video_url`) | `reject` | `refresh`.
- `POST /publishing/{id}/approve-upload` — `approve` | `reject` | `regenerate` | `edit_metadata`
  (patches the selected clip's title/description/hashtags and stays at the gate).

Wrong-state actions return **409**; validation **422**; insufficient credits **402** (op `publish`).

## Config (defaults in `core/config.py`, documented in `.env.example`)

`INFERENCE_MAX_CONCURRENCY`, `INFERENCE_QUEUE_MAXSIZE`, `INFERENCE_MAX_RETRIES`,
`INFERENCE_MODEL_{SMALL,MEDIUM,LARGE}`, `PUBLISH_DISCOVER_TOP_N`, `PUBLISH_SCORE_KEEP`,
`PUBLISH_MAX_REVISIONS`, `EVAL_PASS_THRESHOLD`, `EVAL_MIN_DIMENSION`, `YOUTUBE_DAILY_QUOTA`,
`YT_QUOTA_RESERVE`, `YT_SEARCH_CACHE_TTL_HOURS`, `YT_MAX_RETRIES`, `YT_BACKOFF_BASE_SECONDS`,
`TRENDING_CRAWLER_HOURS`, `TRENDING_CRAWLER_TOPICS_PER_CYCLE`, `CREDITS_COST_PUBLISH`.

YouTube quota is a shared daily budget (`tools/youtube/quota.py`): every call charges it and
retries only transient errors; daily-quota exhaustion raises `QuotaExceededError`, and discovery
degrades to the cached trending pool. See the `search-retrieval` skill.

## Phase 2 (built)

- **Single-GPU model management** — `core/inference/gpu.py` (generic `GpuModelManager`: dependency-
  injected warm/evict, thrash counter, idle eviction) + `tools/llm/warm.py` (Ollama `keep_alive`
  binding + singleton). Started in the app lifespan; enabled by `INFERENCE_WARM_ENABLED` (Ollama
  only). The inference client records model residency via `note_use`.
- **YouTube quota discipline** — `youtube_service.search_and_rank` accounts unit cost and, when the
  daily budget can't cover a live search, backs off to the cached trending pool (0 units) via
  `discovery_agent.build_recommendations`.
- **Existing nodes on the scheduler** — `analyze_video_node` + `content_gen_node` route their real
  LLM call through `tools.llm.inference.run_scheduled` behind `INFERENCE_SCHEDULER_ENABLED`
  (default on); `cached_llm_text` keys are unchanged, and a disable flag restores direct `get_llm()`.
- **MCP tools** — `start_publishing`, `get_publishing`, `list_publishing`, `approve_source`,
  `approve_upload`, `publishing_metrics` (thin wrappers over the REST endpoints).
- **Frontend UI** — `frontend/src/app/publishing/` (list/start + detail with live SSE, both approval
  gates), `hooks/usePublishing.ts` + `hooks/usePublishingEvents.ts`, API client + types, nav link.

## Still deferred

Request batching (multiple clips scored in one prompt); thumbnail-frame re-generation inside the
revision loop (Phase 1/2 revise is text-metadata only); a dedicated observability dashboard page
(metrics are exposed at `GET /publishing/metrics`); privacy/tag overrides honoured at the upload
gate for verified Google apps (currently defaults to private + clip hashtags).

## Tests

`tests/test_inference_scheduler.py`, `tests/test_publishing_orchestrator.py`,
`tests/test_publishing_review.py`, `tests/test_publishing_runner.py`, `tests/test_publishing_api.py`
(mock `get_llm`/inference client at the boundary; `AUTH_DISABLED=1`, in-memory stores).
