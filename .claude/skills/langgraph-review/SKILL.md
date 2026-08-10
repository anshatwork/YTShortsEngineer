---
name: langgraph-review
description: Review LangGraph nodes and graph wiring in this repo (agents/long_to_shorts). Use when adding/changing a graph node, editing graph.py edges, or changing state flow. Checks node contract, state ownership, degrade-not-fail, caching, and instrumentation.
---

# LangGraph Review

Review changes to the **active** graph (`agents/long_to_shorts/graph.py` + `*_node.py`). Context:
`docs/claude/agents.md`, `state.md`, `architecture.md`.

## Checklist

**Node contract**
- [ ] Signature `def <name>_node(state) -> dict` returning a **partial** state dict (never mutate
      and return the whole state; never return `None`).
- [ ] Body wrapped in `with node_stage(state, "<name>"):` — no exceptions.
- [ ] Real logic in a private `_<name>_impl` (testable without the graph).
- [ ] Reads state with `.get()` + defaults (state is `total=False`).

**State ownership** (see `state.md` table)
- [ ] Writes only keys this node owns; doesn't overwrite another node's `ClipObject` fields.
- [ ] Clip artifacts written only under `state["clips_dir"]`.
- [ ] If a new state key is added, it's declared in `agents/state.py` with an owner comment.

**Degrade-not-fail** (optional post nodes)
- [ ] On a per-clip error: log + leave `clip["path"]` unchanged; never raise out of the node.
- [ ] Disabled (flag off) → returns a `*_skipped` `current_step`, clips untouched.
- [ ] Flag read state-first, env-var-second.

**LLM & caching**
- [ ] LLM via `get_llm()` only; structured output via `llm.parse(..., Schema, system=...)`.
- [ ] Completions wrapped in `cached_llm_text(operation, version, ...)`.
- [ ] **`version` bumped if the prompt's meaning changed.**

**Graph wiring**
- [ ] New edges keep the pipeline a DAG; post-node ordering respects the `path` suffix chain
      (`_noted → _sub → _final → _music`). Reordering requires re-checking suffix assumptions.
- [ ] No checkpointer/interrupt added to `long_to_shorts_app` (batch graph; HITL is API-layer).

**Concurrency**
- [ ] Per-clip parallelism uses a bounded `ThreadPoolExecutor` with a configurable worker count;
      no unbounded thread spawning.

## Red flags
- Importing `api/` or graph state into a node's helper that belongs in `tools/`.
- A node doing two unrelated transformations (split it, unless it's the documented content_gen case).
- Blocking `input()` or interactive prompts (CLI-only `hitl_select_video_node` is the exception).
