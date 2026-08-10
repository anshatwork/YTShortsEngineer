---
name: architecture-review
description: Review a change for architectural fit in this repo — layering, dependency direction, no-duplication, backward compatibility. Use when adding a module, a new integration, an API route, or anything that crosses layers.
---

# Architecture Review

Context: `docs/claude/architecture.md`, `design-decisions.md`, root `CLAUDE.md`.

## Layering (the core rule)

Dependencies point **downward only**: `frontend → api → nodes → tools → core`.

- [ ] `core/` imports nothing from repo layers above it.
- [ ] `tools/` imports only `core/` — NEVER graph state, nodes, or `api/`.
- [ ] Nodes import `tools/`, `core/`, `agents/state.py` — not `api/`.
- [ ] New shared logic lives at the lowest layer that needs it.

## No duplication
- [ ] MCP tools wrap `/api/v1` routes in-process (`mcp_client.call_api`) — not a reimplementation.
- [ ] New provider/source added behind the existing registry (`tools/assets/`, `tools/llm/`), not a
      bespoke path.
- [ ] Not re-implementing something the legacy graphs already do — but also not extending legacy
      (ADR-001: legacy is frozen; build on `long_to_shorts`).

## Backward compatibility
- [ ] REST response shapes are additive (no renamed/removed fields; frontend + MCP depend on them).
- [ ] `/static` and `/library` URL contracts preserved; URLs come from the blob store's `url()`.
- [ ] New behavior behind a flag with a safe default.

## Execution model
- [ ] Heavy work runs on the task queue (worker thread), not the event loop.
- [ ] Swappable backends respected: don't hardcode local blob store / sqlite index / in-process bus
      if the ABC seam exists (ADR-002/003) — read the backend from config.
- [ ] Cross-thread → loop only via the event bus.

## Config & secrets
- [ ] New env vars in `core/config.py` (default) + `.env.example` (+ `docs/go-live-setup.md` if
      deploy-only). Prefer `settings` over ad-hoc `os.getenv` in new modules (ADR-006).
- [ ] Secrets never logged; entitlement derived from JWT/signed webhook, not request bodies.

## Output
Summarize: does the change fit the layering? Any upward imports, duplication, or contract breaks?
If it introduces a new pattern, is it justified vs an existing one (cite the ADR it challenges)?
