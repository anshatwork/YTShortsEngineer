# Coding Guidelines (Repository-Specific)

General Python style is assumed. This file captures the conventions that are specific to *this*
repo — the ones that keep the pipeline maintainable. See also the root `CLAUDE.md` for the
condensed rules and Definition of Done.

## Layering (the one rule that matters most)

Dependencies point **downward only**:

```
frontend → api → graph/nodes → tools → core
```

- `core/` imports nothing from the repo above it. It is the leaf (config, cache, exceptions,
  logging, enums).
- `tools/` may import `core/` only. **Never** import graph state, node modules, or `api/`.
- Nodes (`agents/long_to_shorts/*_node.py`) may import `tools/`, `core/`, and `agents/state.py`.
- `api/` wires everything; it owns the task queue, stores, auth, credits.

If you find yourself importing "upward", the abstraction belongs lower. This is what makes
`tools/` reusable by the future agents in `docs/future/`.

## Typing

- Use `TypedDict` for graph state (`agents/state.py`) and **Pydantic** models for API I/O
  (`api/models.py`) and LLM structured output (`HookSegment`, `ClipMeta`, `ThumbnailSpec`, …).
- Prefer `llm.parse(prompt, Schema, system=...)` over hand-parsing LLM text. Regex fallback
  parsers exist for non-structured providers but are the fallback path, not the default.
- State `TypedDict`s are `total=False`; always `.get()` and default — never assume a key exists.

## Async vs threads

- The event loop runs FastAPI + SSE. **CPU/IO-heavy pipeline work runs in worker threads** on the
  `ThreadPoolTaskQueue` (`WORKER_THREADS`, default 2), NOT on the event loop.
- Route handlers are `async`; they enqueue work and return `202` — they must never call FFmpeg,
  Whisper, or `graph.invoke` inline.
- Runners are **synchronous** functions executed on the queue. Don't spawn your own threads inside
  a runner; concurrency is the queue's job. Within a node, bounded `ThreadPoolExecutor`s for
  per-clip parallelism are fine (that's the existing pattern) — keep worker counts modest and
  configurable.
- Cross-thread → event-loop communication only via the event bus (`loop.call_soon_threadsafe`
  after `bind_loop`). Never touch `asyncio` primitives from a worker thread directly.

## Graph nodes

- Signature: `def <name>_node(state) -> dict`, returning a **partial** state dict. Delegate the
  body to a private `_<name>_impl` for testability.
- Wrap the body in `with node_stage(state, "<name>"):` — this is mandatory instrumentation
  (logging context + stage store + `current_node`).
- Keep nodes **small and single-purpose**. One node = one transformation. If a node does two
  things (e.g. "generate metadata AND pick music"), that's a smell — but note content_gen does
  both today for cache locality; new work should prefer separate nodes.
- **Optional post-processing nodes must degrade, not fail:** on a per-clip error, log and leave
  `clip["path"]` unchanged. The pipeline must always emit output.
- Read feature flags **state-first, env-var-second** (`state.get("add_x") or _env_flag("ADD_X")`).
- Only the owning node writes a given state key (see `state.md`). Never mutate `generated_clips`
  entries owned by another node except to set your own field.

## Prompts

- System prompts are module-level constants (`_ANALYSIS_SYSTEM`, `_CONTENT_SYSTEM`, …), sent to
  Anthropic as an ephemeral cache block. Keep them static; parameterize via the *user* prompt.
- Creator guidance goes through `guidance_block(user_context)` into the user prompt — never
  concatenated into the system prompt.
- Memoize completions with `cached_llm_text(operation, version, invoke)`. **Bump `version` when a
  prompt's meaning changes**; leave it when only parsing changes.
- See `prompts.md` and `.claude/skills/prompt-review.md`.

## FFmpeg wrappers

- Prefer the existing modular wrappers (`tools/video_editing/`, node-local builders) over adding a
  new FFmpeg invocation style. There are already four (subprocess, ffmpeg-python, MoviePy,
  yt-dlp) — don't add a fifth.
- Resolve the binary with `imageio_ffmpeg.get_ffmpeg_exe()` fallback to PATH (see
  `audio_mixer._resolve_ffmpeg_bin`). Note `imageio_ffmpeg` bundles no `ffprobe` — use
  `ffmpeg.probe` (ffmpeg-python) for probing.
- Always set `-movflags +faststart` and `-pix_fmt yuv420p` on final outputs (browser + mobile).
- On Windows, subtitle/ASS burn-in needs `cwd`-relative bare filenames to dodge colon/backslash
  escaping — follow `subtitles_node`. Fonts must exist on the box (Arial on Windows, DejaVu in
  Docker); `caption_generator.py` hardcodes `C:\Windows\Fonts\impact.ttf` (portability debt).
- Copy the video stream (`-c:v copy`) when only the audio changes (see `audio_mixer`) — never
  re-encode video unnecessarily.
- See `.claude/skills/ffmpeg-best-practices.md`.

## Logging

- Get loggers via `logging.getLogger(__name__)`; the central config
  (`core/logging_config.configure_logging`) adds handlers + the `[job:<id>|<node>]` formatter.
  Don't add your own handlers.
- Node/job context is set by `node_stage` and `job_log_context`/`job_log_scope` — don't set
  `current_job_id`/`current_node` contextvars by hand outside those.
- Never log secrets. Providers redact keys (`redact_key`); follow that. The YouTube OAuth callback
  deliberately logs only exception *type*.

## Config

- Prefer `from core.config import settings` for new code. Be aware many modules read `os.getenv`
  directly so they survive a `Settings` construction failure — match the local file's existing
  choice rather than mixing both in one module. See `design-decisions.md` ADR-006.
- New env vars: add to `core/config.py` (with a default), document in `.env.example`, and if it's
  deploy-only, in `docs/go-live-setup.md`.

## Errors

- Raise the typed exceptions in `core/exceptions.py` (`VideoDownloadError`,
  `AudioGenerationError`, `RenderingError`, `ScriptGenerationError`, `ConfigurationError`) — not
  bare `RuntimeError` (the legacy `editor_engine.py` does; don't copy it).
- Credit/quota meters **fail open** on transient store errors (a billing hiccup must not block a
  paying user) but raise `402` on a real shortfall. Preserve this behavior.
- Store writes in instrumentation are best-effort (swallow + log); business writes are not.

## Money paths (credits/quota/webhooks)

- Debit before enqueue; refund on failure with an **idempotent key** (`refund:{job_id}`).
- Webhook grants are idempotent on a period-scoped key. Verify signatures
  (`STRIPE_WEBHOOK_SECRET`, HMAC for Razorpay) before trusting a payload.
- Never trust `plan`/`user_id` from a request body for entitlement — derive from the verified JWT
  or a signed webhook.

## Backward compatibility

- Keep REST response shapes stable (the frontend + MCP depend on them). Add fields; don't rename
  or remove. New behavior goes behind a flag with a safe default.
- The `/static` and `/library` URL contracts must survive a blob-store swap — return URLs via the
  store's `url()`, don't hardcode local paths.
