---
name: performance-optimization
description: Find and fix performance issues in this repo — caching, FFmpeg encode cost, LLM call/token cost, worker/thread concurrency, Whisper, SSE. Use when a job is slow, costs too much, or before scaling.
---

# Performance Optimization

Context: `docs/claude/architecture.md` (§execution), `tools.md`, `design-decisions.md` ADR-002/003.

## Where the time/cost goes (profile here first)
1. **Clip extraction (FFmpeg)** — the heaviest CPU step. Tunables: `CLIP_WORKER_THREADS`,
   `FFMPEG_THREADS_PER_PART`, `CLIP_PART_TARGET_SECONDS`, `CLIP_MAX_PARTS`, `CLIP_X264_PRESET`.
   Split-encode-concat parallelizes long clips; ensure it's engaged (not falling back to single-pass).
2. **Whisper** — CPU-bound, 2 workers cap. Avoid it entirely when `timed_transcript`/SRT is present
   (subtitles_node + runner already prefer captions). Watch `WHISPER_MAX_MINUTES`.
3. **LLM calls** — latency + $. Cost levers below.
4. **Music/asset fetch** — network; served from disk cache after warm-up.

## Caching (biggest wins)
- [ ] Rendered clips and LLM completions are memoized in the CAS. Confirm cache **hits** on rerun
      (logs). A miss where you expected a hit usually means an input changed or a `version` bump.
- [ ] Don't defeat the cache: keep inputs to `make_key` canonical/stable; don't include timestamps
      or run-specific junk in the hashed inputs.
- [ ] Anthropic **ephemeral prompt cache**: keep system prompts static and identical across chunks
      (~0.1× cost). Interpolating per-request data into the system prompt breaks it.

## LLM cost
- [ ] Chunk transcripts sensibly (analyze_video); avoid re-sending the whole transcript per clip.
- [ ] Prefer smaller/cheaper models where quality allows (`CLAUDE_MODEL`, GLM flash, Ollama for dev).
- [ ] Batch where the API allows; avoid N+1 LLM calls per clip when one structured call suffices.

## Concurrency & scale
- [ ] `WORKER_THREADS` (default 2) bounds concurrent jobs on one box; raise cautiously (FFmpeg is
      CPU-hungry, and env-var feature flags aren't thread-isolated — ADR-007).
- [ ] Per-clip `ThreadPoolExecutor` counts should be configurable, not hardcoded high.
- [ ] To scale beyond one box, use the ABC seams (Redis bus, external broker, S3 blob store) — don't
      hand-roll (ADR-002/003).

## SSE / event bus
- [ ] Per-subscriber queues are bounded (256, drop-oldest). Don't emit high-frequency spam events;
      coalesce progress.

## Verify
Measure before/after on the same input (a job id in `logs/jobs/`). Report wall-clock per node and
cache hit rate, not just totals.
