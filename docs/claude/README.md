# Claude Knowledge Base

Concise, code-accurate documentation for developing this repo with Claude Code. Start with the
root `CLAUDE.md`, then dive here. If a doc conflicts with the code, the code wins — fix the doc
(or run `make docs` / the scripts in `scripts/`).

| File | What it answers |
|---|---|
| [architecture.md](architecture.md) | System map, the three graphs, request lifecycle, FastAPI/MCP/FFmpeg/storage, dependency graph |
| [agents.md](agents.md) | Per-node inputs/outputs/state mutations/tools/failure modes; edit workers; legacy nodes |
| [state.md](state.md) | `LongToShortsState`/`ClipObject` schema, ownership, lifecycle, persistence, checkpoints |
| [prompts.md](prompts.md) | Every LLM prompt: purpose, variables, output schema, caching, failures |
| [knowledge-graph.md](knowledge-graph.md) | Multimodal Knowledge Graph (`core/kg`, `tools/embeddings`, `agents/ingestion`): schema, ingestion, entity resolution, query engine, API |
| [publishing-agent.md](publishing-agent.md) | Autonomous Publishing Agent (`core/inference`, `agents/publishing`, `publishing_*`): inference scheduler, review sub-graph, durable human-gated state machine, two approval gates |
| [tools.md](tools.md) | `tools/` adapters: LLM/TTS/video-editing/assets/youtube/thumbnail interfaces, env vars, side effects |
| [coding-guidelines.md](coding-guidelines.md) | Repo conventions: layering, typing, async/threads, nodes, prompts, FFmpeg, logging, config |
| [design-decisions.md](design-decisions.md) | ADRs — the *why* behind non-obvious choices (+ documented debt) |
| [testing.md](testing.md) | Test layout, coverage, taxonomy, how to run, CI recommendation |
| [debugging.md](debugging.md) | Common failures → diagnosis → fix, with repro harnesses |
| [roadmap.md](roadmap.md) | Now / Next / Later / Research + tracked engineering debt |
| [repo-map.md](repo-map.md) | **Auto-generated** — source tree, graph nodes/edges, API routes, dependency graph (`make docs`) |

Related: the authoritative `docs/ARCHITECTURE.md`, deployment `docs/go-live-setup.md`, forward
design specs in `docs/future/`, and reusable review guides in `.claude/skills/`.
