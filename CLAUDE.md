# CLAUDE.md — Repository Instructions

Instructions for Claude Code working in this repo. Read this first, then the knowledge base in
[`docs/claude/`](docs/claude/README.md). This file is the contract; the knowledge base is the detail.

> Frontend has its own rules in `frontend/CLAUDE.md` → `frontend/AGENTS.md` (Next.js 16 has
> breaking changes — read `frontend/node_modules/next/dist/docs/` before touching frontend code).

## What this is

An AI YouTube Shorts engine: a **FastAPI backend** running a **LangGraph** pipeline that turns
long-form video into vertical 9:16 short clips (FFmpeg + Whisper + LLM), with Supabase persistence,
SSE progress, credits/billing, YouTube upload, and a mounted **MCP** connector. A separate Next.js
16 frontend drives it.

## ⚠️ Know which graph/workflow you're in

| Graph/workflow | Entry | Status |
|---|---|---|
| `agents/long_to_shorts/graph.py` (`long_to_shorts_app`) | API `runner.py`, `run_clipping_workflow.py` | **ACTIVE — the product. Build here.** |
| Publishing orchestrator | `agents/long_to_shorts/api/publishing_runner.py` + `publishing_orchestrator.py` | **ACTIVE — durable human-gated workflow.** |
| Publishing review graph | `agents/publishing/graph.py` (`publishing_review_app`) | **ACTIVE — scores/evaluates/revises generated clips.** |
| `agents/graph.py` | `agents/batch_processor.py` | Legacy (modular nodes) — frozen |
| `workflows/graph.py` | `main.py` | Oldest (class agents) — frozen |

Default to `long_to_shorts` for clip generation and the publishing workflow for Publish-mode work.
There are different state models for the clipping graph, publishing jobs, and the legacy agents;
do not mix them (see `docs/claude/architecture.md` and `docs/claude/state.md`).

### Active graph topology

The core clip graph is linear and produces publishable Shorts:

```text
START
  → analyze_video
  → clipping_logic
  → content_gen
  → thumbnail [optional]
  → top_text [optional]
  → subtitles [optional]
  → intro_attach [optional]
  → music_attach [optional]
  → END
```

Publish mode wraps that graph in a durable API state machine:

```text
discovering
  → waiting_for_source_approval
  → generating
  → scoring → evaluating ⇄ revising
  → waiting_for_upload_approval
  → uploading → complete
```

`publishing_runner.py` owns the worker-stage execution and crash recovery. The source gate
resolves channel-first prompts such as `Speed` to the latest channel uploads when possible;
topic-style prompts fall back to the existing Discover search/ranking path. Before or during
clip generation, the selected source is enriched with YouTube context: transcript, description,
chapters parsed from the description, channel details, comments, and related videos. The upload
gate exposes the generated clips, context, structured refinement instructions, metadata editing,
clip selection, and explicit final upload approval.

The publishing review subgraph is intentionally bounded:

```text
START → scoring → eval ── pass/budget exhausted ──→ END
                    ↑
                    └──────── revise (bounded) ────┘
```

It is invoked synchronously on a worker thread; durable state lives in the publishing job store,
not in a LangGraph checkpointer.

## Folder responsibilities

```
agents/long_to_shorts/      ACTIVE pipeline: *_node.py graph nodes, graph.py, helpers (_llm_cache, _prompt_utils, _logging_utils)
agents/long_to_shorts/api/  FastAPI: routes*, runner/edit_runner, publishing_* workflow, youtube_service/upload, mcp_*, auth, credits, quota, db/ stores, models.py
agents/publishing/          Active Publish review subgraph: discovery/ranking, clip scoring, Eval Agent, bounded metadata revision
agents/ (top level)         Legacy class agents + modular node.py — frozen
workflows/                  Oldest class-agent graph — frozen
tools/                      Side-effecting adapters: llm/, tts/, video_editing/, assets/, youtube/ search+transcript, thumbnail.py
core/                       Shared primitives: config, cache (CAS), execution (queue/bus/lifecycle), exceptions, logging, enums
supabase/migrations/        SQL schema
frontend/                   Next.js 16 app (own CLAUDE.md/AGENTS.md)
docs/, docs/claude/, docs/future/   Docs, this knowledge base, forward design specs
.claude/skills/             Reusable review guides
```

## Architecture rules (non-negotiable)

- **Dependencies point downward only:** `frontend → api → nodes → tools → core`. `core/` imports
  nothing above it; `tools/` imports only `core/` and NEVER graph state or `api/`. If you're
  importing upward, the code belongs lower.
- **Never duplicate business logic.** MCP tools wrap the REST API in-process (don't reimplement);
  edit workers reuse pipeline building blocks; new sources go behind the existing registry
  patterns (`tools/assets/`, `tools/llm/`).
- **Prefer composition over inheritance.** The active pipeline is composed node functions, not a
  class hierarchy. Don't grow the legacy `BaseAgent` tree.
- **Keep graph nodes small and focused.** One node = one transformation. Delegate the body to a
  private `_<name>_impl` for testability.
- **Maintain backward compatibility.** Don't rename/remove REST response fields or `/static`
  `/library` URL contracts (frontend + MCP depend on them). Add behind flags with safe defaults.
- **Keep Publish additive.** Existing `/publishing`, `/publishing/{id}/approve-source`, and
  `/publishing/{id}/approve-upload` contracts remain valid. New source context, generated clips,
  selected clip, review instructions, and upload-option fields are optional/defaulted for older jobs.

### Publish-mode rules

- Channel discovery belongs in `tools/youtube/search.py` and is exposed through
  `agents/long_to_shorts/api/youtube_service.py`; do not duplicate YouTube API calls in routes or
  React components.
- Generic/topic prompts continue using the existing Discover ranking machinery. Short creator-like
  prompts may resolve a channel and return its newest five uploads.
- YouTube context enrichment is best-effort. Missing captions, comments, chapters, related videos,
  or channel statistics must not fail the publishing run.
- Publishing jobs may persist `source_context`, `generated_clips`, `selected_clip_id`, and upload
  privacy/category/tags. Update both memory and Supabase stores plus the migration when adding fields.
- Users choose the final clip at the upload gate. `selected_clip` remains the compatibility field used
  by the existing uploader; `generated_clips` is the review list.
- Upload remains explicit and idempotent. Route-provided privacy status, category ID, and tags must be
  persisted before enqueueing and forwarded to `youtube_upload_runner.py`.
- `publishing_store` is event-emitting, so job mutations should go through its `update()` method to
  keep `/publishing/{id}/events` current. Request-option edits use the store's request-update seam.

## LangGraph conventions

- Node signature: `def <name>_node(state) -> dict`, returning a **partial** state dict (LangGraph
  merges it). State `TypedDict`s are `total=False` — always `.get()` with a default.
- Wrap every node body in `with node_stage(state, "<name>"):` (mandatory logging + stage tracking).
- Optional post-processing nodes (`thumbnail`, `top_text`, `subtitles`, `intro_attach`,
  `music_attach`) **must degrade, not fail**: on a per-clip error, log and leave `clip["path"]`
  unchanged. The pipeline must always produce output.
- Read feature flags **state-first, env-var-second** (`state.get("add_x") or env "ADD_X"`).
- Get the LLM only via `from tools.llm import get_llm`. Never construct providers directly.

## State management rules

- **Only the owning node writes a given state key** (ownership table in `docs/claude/state.md`).
  Don't mutate another node's fields on `generated_clips` entries.
- **Never mutate shared state outside a graph node.** Runners build `initial_state` and read the
  final state; they don't reach into state mid-run. Tools/core never see graph state at all.
- `clips_dir` (set by `clipping_logic`) is where **all** clip artifacts go — never write elsewhere.
- The active graph has **no checkpointer**; durability is the content-addressable cache
  (`core/cache`) + the job store, not LangGraph checkpoints.

## Prompt organization

- System prompts are static module constants (`_ANALYSIS_SYSTEM`, `_CONTENT_SYSTEM`,
  `THUMBNAIL_SYSTEM`, …), sent to Anthropic as an ephemeral cache block — keep them static.
- Route creator guidance through `guidance_block(user_context)` into the **user** prompt, never the
  system prompt.
- Prefer `llm.parse(prompt, PydanticSchema, system=...)` over free-text parsing.
- Memoize with `cached_llm_text(operation, version, invoke)` and **bump `version` when a prompt's
  meaning changes** (else stale completions are served). Catalog: `docs/claude/prompts.md`.

## Coding standards (summary — full list in `docs/claude/coding-guidelines.md`)

- Route handlers are `async` and only enqueue work (return `202`); heavy work runs **synchronously
  on worker threads** via the task queue. Never run FFmpeg/Whisper/`graph.invoke` on the event loop.
- Cross-thread → loop communication only via the event bus (`loop.call_soon_threadsafe`).
- Raise the typed exceptions in `core/exceptions.py` (not bare `RuntimeError`).
- All final video outputs set `-pix_fmt yuv420p` and `-movflags +faststart`. Don't add a fifth
  FFmpeg invocation style — reuse existing wrappers (`.claude/skills/ffmpeg-best-practices.md`).
- Logging via `logging.getLogger(__name__)`; don't add handlers or set job/node contextvars by hand.
- Money paths: debit before enqueue, refund idempotently on failure, verify webhook signatures,
  derive entitlement from the JWT/signed webhook — never from a request body. Meters **fail open**.
- New env vars → add to `core/config.py` with a default → document in `.env.example` (and
  `docs/go-live-setup.md` if deploy-only).

## Testing checklist

- Validate **per-file** (`pytest tests/test_x.py`), not the whole suite — it has known
  shared-singleton redness (`docs/claude/testing.md`). Root `test_*.py` are legacy demo scripts;
  some make live calls — don't run in CI.
- Add tests to `tests/` (pytest), mocking at the boundary (`get_llm`, `tools.*`, ffmpeg, SDKs) with
  in-memory stores + `AUTH_DISABLED=1`.
- Cover: node `_impl` returns, the degrade-not-fail contract, API status codes (422/402/404/409),
  job lifecycle, and money-path idempotency/fail-open.
- Frontend: `cd frontend && npm run lint && npm run build`.
- Publish-specific coverage: channel-name resolution and latest-upload ordering; broad-search fallback;
  best-effort context enrichment; multi-clip selection; review/regeneration; upload metadata forwarding;
  state transitions, crash recovery, idempotency, and credit refund behavior.

## Definition of Done

1. Change lives at the right layer; no upward imports; no duplicated logic.
2. New/changed nodes are small, wrapped in `node_stage`, and degrade gracefully.
3. State changes: owner-only writes; schema updated in `agents/state.py`; threaded through
   `models.py`/runner/`mappers.py` if user-facing; `docs/claude/state.md` updated.
4. Prompt changes bump the cache `version`; catalog updated in `docs/claude/prompts.md`.
5. Tests added/updated and passing **per-file**; `make lint typecheck` clean.
6. REST/URL contracts unchanged (or additive with safe defaults).
7. New env vars documented; secrets never logged.
8. Relevant docs updated (a doc that conflicts with code is a bug — fix it). Run `make docs` if you
   changed structure.

## Handy commands

```bash
# Full pipeline locally, no API (fastest repro)
python run_clipping_workflow.py <youtube-url-or-local-path> [--subtitles --top-text --no-intro --fullscreen]

# API locally (/docs available when ENVIRONMENT != production)
python agents/long_to_shorts/api/server.py --reload
start.bat                      # Windows: API + frontend together

# Tests (per-file), lint, types, docs
pytest tests/test_api.py -v
pytest tests/test_publishing_orchestrator.py tests/test_publishing_runner.py tests/test_publishing_api.py -q
make lint typecheck test docs  # see Makefile

# Code intelligence: prefer the codegraph MCP over grep/read for "how does X work / who calls Y"
```

See `docs/claude/README.md` for the full knowledge base and `docs/future/` for forward specs.
