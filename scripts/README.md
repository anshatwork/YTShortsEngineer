# scripts/

Repository tooling. Run from the repo root.

| Script | Purpose | Invoke |
|---|---|---|
| `gen_repo_map.py` | Regenerate `docs/claude/repo-map.md` — source tree, LangGraph nodes/edges (Mermaid), FastAPI route map, and the top-level module dependency graph (Mermaid). Stdlib only, no deps. | `python scripts/gen_repo_map.py` or `make repo-map` / `make docs` |

## Keeping docs current as the repo evolves

`docs/claude/repo-map.md` is **auto-generated** — don't hand-edit it. Regenerate it whenever you
add/rename a graph node, an API route, or a package:

```bash
make docs        # regenerates the repo map
```

The narrative knowledge base (`docs/claude/*.md`) is hand-written and should be updated in the same
PR as the code it describes (see the Definition of Done in the root `CLAUDE.md`).

### Suggested automation
Add `make docs` to a pre-commit hook or CI step so the map never drifts. The dependency graph also
doubles as a lint: an edge like `tools --> agents` means a layering violation (`tools/` must import
only `core/`) — see `docs/claude/coding-guidelines.md`.
