---
name: vlm-integration
description: Guide for integrating vision-language (VLM) analysis into this repo — frame sampling, provider abstraction mirroring tools/llm, caching, and wiring a vlm_analyze node. Use when implementing docs/future/vlm-agent.md or any image/video understanding feature.
---

# VLM Integration

Design spec: `docs/future/vlm-agent.md`. This skill is the how-to for building it consistently with
the repo's patterns. Nothing VLM exists yet — build it to mirror `tools/llm/`.

## Principles
- **Mirror the LLM abstraction.** Add `tools/vlm/` with `base.py` (`VLMProvider` protocol),
  `registry.py`, per-provider adapters, and BYOK — same shape as `tools/llm/` so credential/
  fallback plumbing carries over. Default to Claude vision; allow a local VLM (Ollama) for offline.
- **Access only via a factory** (`get_vlm()` analogous to `get_llm()`); never construct providers in
  nodes.
- **Layering:** `tools/vlm/` imports only `core/`. Nodes call it. No upward imports.

## Frame sampling (cost control)
- [ ] Sample keyframes at **scene boundaries** (reuse the gallery agent's scene detection), not
      fixed intervals — fewer calls, better coverage.
- [ ] Batch multiple frames per request.
- [ ] Ground with the transcript window for the segment (better captions/shot classification).

## Caching (mandatory — VLM is the priciest call)
- [ ] Cache results in the CAS keyed on `(file_hash, sampling_params, model, version)` via the
      `cached_llm_text`-style pattern (`core/cache`).
- [ ] Reuse embeddings/keyframes with the gallery + video-sourcing agents (shared CLIP + pgvector).

## Wiring into the pipeline
- [ ] New node `vlm_analyze_node` after `analyze_video`, before `clipping_logic`; writes
      `ShotAnalysis[]` onto state; blend visual `engagement` with transcript `hook_score` for final
      ranking.
- [ ] Gate behind a feature flag + a per-op credit cost in `credits.py` (it's expensive).
- [ ] Degrade-not-fail: if the VLM call fails, fall back to transcript-only ranking.

## Structured output
- [ ] Use Pydantic schemas (`ShotAnalysis`) with `provider.analyze()` returning typed results;
      handle providers without native structured output via the same JSON-extraction seam as
      `tools/llm/base.py`.

## Review with: `architecture-review`, `prompt-review`, `performance-optimization`.
