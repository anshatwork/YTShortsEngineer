---
name: code-review
description: General code review for this repo's Python backend — typing, async/threads, error handling, logging, config, money paths, tests. Use before committing backend changes or when reviewing a diff.
---

# Code Review

Repo-specific review. Full conventions in `docs/claude/coding-guidelines.md`. For graph-specific or
architectural changes, also run the `langgraph-review` / `architecture-review` skills.

## Checklist

**Typing & models**
- [ ] Pydantic for API I/O (`api/models.py`) and LLM structured output; `TypedDict` for graph state.
- [ ] `.get()` + defaults on `total=False` state.

**Async / threads**
- [ ] Route handlers `async`, only enqueue + return `202`. No FFmpeg/Whisper/`graph.invoke` inline.
- [ ] Runners are synchronous; no ad-hoc threads inside them (queue owns concurrency).
- [ ] `asyncio` primitives touched only on the loop; cross-thread via the event bus.

**Errors**
- [ ] Typed exceptions from `core/exceptions.py` (not bare `RuntimeError`).
- [ ] Instrumentation/store writes are best-effort (swallow+log); business writes are not.
- [ ] Meters fail open on transient store errors; `402` only on real shortfall.

**Logging**
- [ ] `logging.getLogger(__name__)`; no custom handlers; no manual contextvar setting.
- [ ] No secrets in logs (follow `redact_key`; OAuth callback logs exception type only).

**Config**
- [ ] New env vars in `core/config.py` + `.env.example`; one config-read style per module.

**Money paths** (credits/quota/webhooks)
- [ ] Debit before enqueue; refund idempotent (`refund:{id}`).
- [ ] Webhook signatures verified; grants idempotent on period key; entitlement from JWT/webhook.

**FFmpeg** (if touched)
- [ ] Final outputs set `-pix_fmt yuv420p` + `-movflags +faststart`.
- [ ] Reuses an existing invocation style; copies video (`-c:v copy`) when only audio changes.
- [ ] Run the `ffmpeg-best-practices` skill.

**Tests**
- [ ] Added/updated in `tests/`; mock at boundaries; in-memory stores + `AUTH_DISABLED=1`.
- [ ] Cover degrade-not-fail, status codes, idempotency/fail-open. Validate per-file.

**Hygiene**
- [ ] No new root-level `test_*.py` demo scripts or committed `*_output.txt`.
- [ ] No large binaries/artifacts added (check `.gitignore`).

## Output
List findings by severity. Distinguish must-fix (correctness, contract break, money-path,
security) from nits. Cite `file:line`.
