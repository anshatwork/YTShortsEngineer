# Roadmap

Engineering-facing roadmap: infrastructure, quality, and scale. Product features are out of scope
here. Horizons: **Now** (in-flight/next sprint), **Next** (this quarter), **Later** (planned),
**Research** (unvalidated). Design specs for many "Later/Research" items live in `docs/future/`.

## Now

- **Go-live hardening.** Finish the runbook in `docs/go-live-setup.md`: secrets rotation,
  YouTube OAuth verification, Stripe/Razorpay live keys. Backend for all SaaS phases is
  implemented (subscriptions, credits, BYOK, MCP).
- **Test-suite green.** Fix the shared task-queue-singleton + auth-ordering issues so
  `pytest tests/` passes whole-suite, not just per-file (`docs/claude/testing.md`).
- **`.env.example` completeness.** Add the deploy-only vars currently only in
  `docs/go-live-setup.md` (S3/CloudFront, `BYOK_FERNET_KEY`, `MCP_*`, `ENVIRONMENT`, `DOMAIN`,
  `ACME_EMAIL`).

## Next

- **Config consolidation (ADR-006).** Make `core/config.Settings` the single source of truth;
  remove ad-hoc `os.getenv` reads where safe. Add missing vars to `Settings` with defaults.
- **Cross-platform media.** Replace hardcoded `C:\Windows\Fonts\impact.ttf` (caption_generator)
  and Windows-only assumptions with a font resolver that works on Docker/Linux.
- **CI pipeline.** Wire `make lint typecheck` + per-file pytest on push; add a video-pipeline
  smoke test behind an ffmpeg-available marker.
- **LLM evaluation harness.** Implement `docs/future/llm-judge.md` P1 (title/hook rubrics + tiny
  golden set + `make evals`) to guard prompt/model regressions and supersede
  `compare_llm_content.py`.
- **Legacy graph decision (ADR-001).** Decide: freeze-and-document vs extract-and-delete the two
  legacy graphs (`agents/graph.py`, `workflows/graph.py`) and their class agents.

## Later

- **Distributed execution.** Swap the in-process ABCs for real backends: Redis event bus, external
  broker task queue (Celery/RQ/Temporal), S3 blob store + Supabase cache index — enabling
  multi-worker/multi-box scale (`docs/ARCHITECTURE.md` §7; ADR-002/003).
- **Unified video sourcing.** `docs/future/video-sourcing.md` — one `VideoSource` registry across
  YouTube/Pexels/Pixabay/local/Drive/S3 with ranking + dedup + embeddings, mirroring
  `tools/assets/`.
- **Gallery agent.** `docs/future/gallery-agent.md` — local media indexing (scene detect,
  keyframes, OCR, CLIP embeddings, semantic search).
- **VLM agent.** `docs/future/vlm-agent.md` — visual understanding (caption/OCR/shot-class/
  engagement) blended into clip ranking, thumbnails, top-text.
- **Training agent.** `docs/future/training-agent.md` — chapters/summaries/quizzes/flashcards from
  long-form video (new product surface, no rendering).
- **Memory system.** `docs/future/memory-system.md` — episodic/semantic/vector memory for
  per-creator personalization.
- **AI Learning OS.** `docs/future/ai-learning-os.md` — event-sourced microservices platform that
  turns saved content into a per-user knowledge graph + adaptive learning assets, built on the
  `core/kg` substrate. Umbrella spec composing training-agent/memory-system/gallery as services.

## Research

- **Hosted inference gateway.** Validate OpenRouter as the primary LLM path for the live SaaS
  (`docs/inference-hosting-cost-comparison.md`) vs the current Claude+Ollama+GLM abstraction.
- **Engagement prediction calibration.** Whether VLM engagement scores + real retention/CTR data
  can train a reliable "watchability" ranker (feeds `llm-judge` + `memory-system`).
- **Perceptual dedup at scale.** pHash + embedding near-dup thresholds that hold across providers
  and large local libraries (shared by video-sourcing + gallery).
- **Prompt/model auto-tuning.** Use the eval harness + episodic outcomes to auto-select prompts or
  models per channel.

## Cross-cutting engineering debt (tracked)

See the audit summary and `design-decisions.md`. Highlights: three coexisting graphs, dual config
reads, Windows-first media assumptions, `editor_engine.py` bare exceptions + duplication with
`tools/video_editing/`, the `eval`-based legacy trending LLM path, and stale root-level
`test_*.py`/`*_output.txt` artifacts.
