# Architecture (Claude Knowledge Base)

> This complements — does not replace — the authoritative `docs/ARCHITECTURE.md` (FE/BE/worker
> diagrams, sequence flows, §7 execution layer, scaling path). Read that for the full picture.
> This file is the Claude-oriented map: what's actually wired, the three graphs, the dependency
> graph, and the request lifecycle, with pointers into the code.

## System in one paragraph

A FastAPI backend exposes a LangGraph video pipeline that turns long-form video into vertical
9:16 short clips. Jobs are submitted over REST (or MCP), executed on an in-process thread-pool
task queue, stream progress over SSE, and persist to Supabase (or in-memory in dev). A Next.js
16 frontend (hosted separately) drives it. The same backend is reachable by Claude.ai/ChatGPT
via a mounted MCP connector.

## ⚠️ There are THREE graphs — know which one you're touching

| Graph | State | Entry point | Status |
|---|---|---|---|
| `agents/long_to_shorts/graph.py` → `long_to_shorts_app` | `LongToShortsState` | **API `runner.py`**, `run_clipping_workflow.py` | **ACTIVE / current product** |
| `agents/graph.py` → `app` | `agents/state.py::ShortsState` | `agents/batch_processor.py` | Legacy (modular node functions) |
| `workflows/graph.py` → `app` | `workflows/state.py::ShortsState` | `main.py` | Oldest (class-based `BaseAgent` agents) |

**Almost all real work happens in the first graph.** The other two are the historical
"topic → generated short" system. Node functions in `agents/node.py` and class agents in
`agents/*.py` (trend_discovery, content_sourcing, script_generation, voice_synthesis,
video_assembly, quality_control, publisher) belong to the legacy graphs. Only
`ScriptParserAgent` and `VideoSelectionAgent` are reused by the modular graph. See
`agents.md` for the per-node breakdown and `design-decisions.md` ADR-001 for why they coexist.

## Long-to-Shorts pipeline (the one that matters)

Linear graph, no checkpointer, compiled as `long_to_shorts_app`:

```
START → analyze_video → clipping_logic → content_gen → thumbnail
      → top_text → subtitles → intro_attach → music_attach → END
```

- **analyze_video** — LLM hook-scores transcript segments (Map over chunks).
- **clipping_logic** — parallel FFmpeg 9:16 extraction into a per-run `clips_dir`.
- **content_gen** — LLM writes title/summary/hook_text/hashtags + music mood (Reduce).
- **thumbnail / top_text / subtitles / intro_attach / music_attach** — optional post-processing
  steps, each gated by a per-job flag (state) or env var. `intro_attach` is on by default; the
  rest are opt-in. Each rewrites `clip["path"]` to a new suffixed file and never raises on a
  per-clip failure (degrades to the previous path).

Full per-node I/O is in `agents.md`; the state schema is in `state.md`.

## Request lifecycle (async job)

```
POST /api/v1/jobs
  → auth (Supabase JWT via get_current_user_id)
  → enforce_quota (monthly job cap) + enforce_and_debit (credit ledger)
  → job_store.create(status="queued")            # EventEmittingStore → SSE
  → task_queue.enqueue(run_job, job_id, body, user_id)
  → 202 Accepted (returns immediately)

worker thread (ThreadPoolTaskQueue):
  run_job → _run_job_impl
    → status queued→running
    → Phase 1: acquire video + transcript (yt-dlp / local probe / captions / Whisper)
    → Phase 2: set ADD_* feature-flag env vars the nodes read
    → Phase 3: build initial_state
    → Phase 4: long_to_shorts_app.invoke(state) inside llm_credential_context(byok)
    → Phase 5: map generated_clips → ClipResult; job_store.update(status="done", clips=…)
    → on error: status="failed"; refund credits (idempotent)

browser: GET /api/v1/jobs/{id}/events?token=<jwt>   # SSE snapshot + update frames
```

Every `*_store.update(...)` flows through `EventEmittingStore` (`event_store.py`), which
publishes an `Event` on the resource channel (`job:{id}` / `edit:{id}` / `upload:{id}`). The
event bus binds the running event loop at startup so worker threads can push cross-thread via
`loop.call_soon_threadsafe`. SSE has no replay buffer — reconnect re-syncs from a fresh
snapshot. See `docs/ARCHITECTURE.md` §7 and `core/execution/`.

## FastAPI lifecycle

`agents/long_to_shorts/api/app.py` — app factory with a `lifespan` that:
1. configures context-aware logging (`core/logging_config`),
2. binds the event loop to the event bus, exposes `task_queue`/`executor` on `app.state`,
3. starts self-warming background loops on the task queue: music cache refresh
   (`MUSIC_CACHE_REFRESH_HOURS`) and trending crawl (`TRENDING_CRAWLER_HOURS`),
4. enters the mounted MCP sub-app's lifespan (so its Streamable-HTTP session manager starts),
5. on shutdown, cancels loops and drains the executor + task queue.

Routers (all under `/api/v1`): core jobs (`routes.py`), `edit`, `youtube`, `discover`,
`music`, `llm` (BYOK), `billing`, and SSE `events`. MCP is mounted at `/mcp`; artifacts are
served from `/static` (OUTPUT_DIR) and `/library` (music cache). `/health` is unversioned.
Full endpoint list: see `docs/ARCHITECTURE.md` and the router files (indexed in `agents.md`).

## MCP integration

`mcp_server.py` builds a `FastMCP` app (Streamable HTTP) mounted at `/mcp`. Its tools are thin
wrappers that call the same `/api/v1` routes **in-process** via `httpx.ASGITransport`
(`mcp_client.py`) — so behavior matches REST exactly and shares `app.state` (including the task
queue). Auth is a Supabase OAuth flow (`mcp_auth.py`); the bearer token is forwarded verbatim so
routes run as the authenticated user. RFC 9728 discovery routes are registered on the app root.

## FFmpeg pipeline

FFmpeg is invoked four ways (see `tools.md` + `.claude/skills/ffmpeg-best-practices.md`):
- **raw subprocess** — `clipping_logic_node` (split-encode-concat with a CAS cache),
  `audio_mixer.py`, `subtitles_node` (ASS burn-in).
- **ffmpeg-python** — `top_text_node`, `intro_attach_node`, `thumbnail.py`, TTS transcode.
- **MoviePy** — `layout_engine.py`, legacy `editor_engine.py`.
- **yt-dlp postprocessor** — `download_audio`.
Clip encode defaults: libx264 8000k, aac 192k, 1080×1920, 60fps, yuv420p, `+faststart`.

## Storage & persistence

- **Supabase** (Postgres) is the system of record when `JOB_STORE=supabase` (+ per-store toggles
  `CREDIT_STORE`, `SUBSCRIPTION_STORE`). Workers use the **service-role** client (bypasses RLS);
  routes enforce ownership with the `user_id` from the verified JWT. Migrations in
  `supabase/migrations/`. In dev, stores default to in-memory.
- **Content-addressable cache** (`core/cache`): CAS keyed by
  `sha256(operation, version, canonical_json(inputs))`. Backends: local sharded blob store or S3
  (`BLOB_STORE_BACKEND`); index in SQLite or Supabase (`CACHE_INDEX_BACKEND`). Memoizes rendered
  clips and LLM completions so reruns are cheap. See `state.md` → persistence/checkpoints.
- **Artifacts**: `OUTPUT_DIR` (clips + edits, served at `/static`), `assets/audio_cache` (music,
  served at `/library`), `assets/uploads` (user uploads).

## Dependency graph (module layers)

```
frontend (Next.js 16)                         ← separate deploy, talks REST + SSE
        │  HTTP/SSE
        ▼
agents/long_to_shorts/api/  (FastAPI routers, runners, MCP, db stores, auth, credits, quota)
        │ invoke                         │ persist                 │ progress
        ▼                                ▼                          ▼
agents/long_to_shorts/ (graph + nodes)   supabase/ (Postgres)   core/execution (queue,bus,lifecycle)
        │ uses
        ▼
tools/ (llm, tts, video_editing, assets, youtube, thumbnail)   ← side-effecting adapters
        │ uses
        ▼
core/ (config, cache, exceptions, logging, audio_themes, intents)  ← shared primitives, no upward deps
```

Rule: dependencies point **downward only**. `tools/` and `core/` never import graph state or API
modules. `core/` is the leaf. See `coding-guidelines.md`.

## Configuration

`core/config.py` (`Settings`, pydantic-settings, reads `.env`) is the intended central config,
but many modules also read `os.getenv` directly so they work even if `Settings` construction
fails. This dual-read is deliberate (resilience) but inconsistent — see `tools.md` cross-cutting
notes and `design-decisions.md` ADR-006. `.env.example` documents the common vars; `docs/go-live-setup.md`
documents the deployment-only vars (S3/CloudFront, `BYOK_FERNET_KEY`, `MCP_*`, `DOMAIN`, `ACME_EMAIL`).

## Deployment

Single-EC2 topology: API+workers in Docker (CPU-only torch, ffmpeg with libass) behind Caddy
(TLS, SSE-aware `flush_interval -1`); Ollama optionally on a separate GPU box; Supabase + S3/
CloudFront managed. `docker-compose.yml` runs `api` + `caddy`. See `deploy/README.md` and
`docs/go-live-setup.md`.
