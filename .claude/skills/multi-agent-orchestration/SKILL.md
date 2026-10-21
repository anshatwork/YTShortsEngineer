---
name: multi-agent-orchestration
description: Guide for orchestrating multiple agents/sub-graphs in this repo — LangGraph sub-graphs, the task queue, SSE progress, credits, and how to add a new agent product (e.g. training agent). Use when composing pipelines or adding a new sub-graph.
---

# Multi-Agent Orchestration

How this repo composes agents, and how to add a new one consistently. Context:
`docs/claude/architecture.md`, `agents.md`, `state.md`.

## How orchestration actually works here
- Each "agent"/product is a **LangGraph sub-graph** with its own `State` TypedDict and a compiled
  app (e.g. `long_to_shorts_app`). Nodes are composed functions, not a class hierarchy.
- A **runner** (`api/runner.py`, `edit_runner.py`) builds `initial_state`, calls `app.invoke()` on a
  **worker thread** (task queue), and persists results. Runners never touch state mid-run.
- **Progress** is emitted automatically: every `*_store.update()` goes through `EventEmittingStore`
  → event bus → SSE. Nodes emit progress via `node_stage` + stage store, not by calling the bus.
- **Credits/quota** are enforced at the API boundary before enqueue; refunded idempotently on failure.
- **MCP** exposes the same operations by wrapping REST in-process — one implementation.

## Patterns
- **Sequential sub-graph** (default): linear nodes, no checkpointer (long_to_shorts). Batch work;
  HITL handled at the API layer (submit → poll), not LangGraph interrupts.
- **HITL via interrupts**: only the legacy graphs use `interrupt_before` + `MemorySaver`. Avoid for
  new work unless you truly need mid-graph human input.
- **Fan-out/Map-Reduce**: analyze_video maps over transcript chunks; content_gen reduces per clip.
  Use bounded `ThreadPoolExecutor` inside a node for per-item parallelism.
- **Independent workers**: edit operations are separate runners off the same queue — good model for
  new one-shot operations.

## Adding a new agent/sub-graph (e.g. `docs/future/training-agent.md`)
1. `agents/<name>/state.py` (`TypedDict, total=False`) + `graph.py` (compile `<name>_app`) +
   `*_node.py` nodes following the node contract (see `langgraph-review`).
2. `api/<name>_runner.py`: build `initial_state`, `<name>_app.invoke` inside
   `llm_credential_context(byok)`, map outputs, persist via a store (wrap in `EventEmittingStore`
   for SSE).
3. `api/<name>_routes.py`: `POST` submits (meter credits → `store.create` → `task_queue.enqueue` →
   `202`), `GET` polls, `GET .../events` streams. Register the router in `app.py`.
4. Add a credit op in `credits.py`; add an MCP tool in `mcp_server.py` wrapping the new route.
5. Reuse `get_llm()`, `cached_llm_text`, `core/cache`, transcript tools — don't duplicate.
6. Docs: `docs/claude/agents.md` + a `docs/future/` spec if design-first.

## Anti-patterns
- Calling `app.invoke()` on the event loop, or from inside another node.
- Reaching into another sub-graph's state.
- A new agent that reimplements sourcing/LLM/FFmpeg instead of using `tools/`.
