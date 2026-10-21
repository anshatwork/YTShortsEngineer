#!/usr/bin/env python3
"""
scripts/gen_repo_map.py
~~~~~~~~~~~~~~~~~~~~~~~~
Regenerate `docs/claude/repo-map.md` — an auto-generated map of the repository so the
Claude knowledge base stays current as the code evolves.

It derives, using only the standard library (no third-party deps):

  * a pruned folder tree of the source packages,
  * the LangGraph nodes + edges of every `graph.py` (parsed from add_node/add_edge calls),
  * the FastAPI route map (METHOD + path per router, from decorators + include_router prefixes),
  * a top-level module dependency graph (which package imports which), as Mermaid.

Run:  python scripts/gen_repo_map.py       (or: make repo-map)

This file is DATA, not prose. The hand-written narrative lives in docs/claude/*.md; this
map is regenerated and should not be edited by hand.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "claude" / "repo-map.md"

# Source packages we care about (skip venv, node_modules, caches, assets, output …)
SRC_DIRS = ["agents", "tools", "core", "workflows", "supabase/migrations"]
PRUNE = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".codegraph", "assets", "cache", "output", "logs", ".next", ".cursor", ".gemini",
}
TOP_PACKAGES = ["agents", "agents.long_to_shorts", "agents.long_to_shorts.api",
                "tools", "core", "workflows"]


# --------------------------------------------------------------------------- tree
def folder_tree(base: Path, prefix: str = "", depth: int = 0, max_depth: int = 3) -> list[str]:
    if depth > max_depth:
        return []
    entries = sorted(
        [p for p in base.iterdir()
         if p.name not in PRUNE and not p.name.startswith(".")],
        key=lambda p: (p.is_file(), p.name),
    )
    dirs = [p for p in entries if p.is_dir()]
    lines: list[str] = []
    for i, p in enumerate(dirs):
        last = i == len(dirs) - 1
        py = len(list(p.rglob("*.py"))) if p.is_dir() else 0
        connector = "└── " if last else "├── "
        suffix = f"  ({py} .py)" if py else ""
        lines.append(f"{prefix}{connector}{p.name}/{suffix}")
        ext = "    " if last else "│   "
        lines += folder_tree(p, prefix + ext, depth + 1, max_depth)
    return lines


# --------------------------------------------------------------------------- graphs
def parse_graphs() -> list[tuple[str, list[str], list[tuple[str, str]]]]:
    """Return [(rel_path, nodes, edges)] for every graph.py."""
    results = []
    for gp in ROOT.rglob("graph.py"):
        if any(part in PRUNE for part in gp.parts):
            continue
        text = gp.read_text(encoding="utf-8", errors="ignore")
        nodes = re.findall(r'add_node\(\s*["\']([^"\']+)["\']', text)
        raw_edges = re.findall(
            r'add_edge\(\s*([A-Za-z_"\'][^,]*?)\s*,\s*([^)]+?)\)', text)
        edges = []
        for a, b in raw_edges:
            edges.append((_clean(a), _clean(b)))
        if nodes or edges:
            results.append((str(gp.relative_to(ROOT)).replace("\\", "/"), nodes, edges))
    return results


def _clean(tok: str) -> str:
    tok = tok.strip()
    if tok in ("START", "END"):
        return tok
    return tok.strip("\"'")


# --------------------------------------------------------------------------- routes
def parse_routes() -> list[tuple[str, str, str]]:
    """Return [(prefix, METHOD, path)] across api routers using include_router prefixes."""
    api_dir = ROOT / "agents" / "long_to_shorts" / "api"
    if not api_dir.exists():
        return []
    app_text = (api_dir / "app.py").read_text(encoding="utf-8", errors="ignore")
    # map router variable -> prefix from include_router(router, prefix="…")
    prefixes: dict[str, str] = {}
    for m in re.finditer(
        r'include_router\(\s*(\w+).*?prefix\s*=\s*["\']([^"\']*)["\']', app_text, re.S):
        prefixes[m.group(1)] = m.group(2)
    # map router variable -> module from `from … import router as X`
    var_to_module: dict[str, str] = {}
    for m in re.finditer(
        r'from\s+agents\.long_to_shorts\.api\.(\w+)\s+import\s+router(?:\s+as\s+(\w+))?',
        app_text):
        mod, alias = m.group(1), m.group(2) or "router"
        var_to_module[alias] = mod

    rows: list[tuple[str, str, str]] = []
    for alias, prefix in prefixes.items():
        mod = var_to_module.get(alias)
        if not mod:
            continue
        f = api_dir / f"{mod}.py"
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']',
                             text):
            method, path = m.group(1).upper(), m.group(2)
            full = (prefix + path) or "/"
            rows.append((f"{mod}.py", method, full))
    return sorted(rows, key=lambda r: (r[2], r[1]))


# --------------------------------------------------------------------------- deps
def module_of(path: Path) -> str | None:
    rel = path.relative_to(ROOT).as_posix()
    for pkg in sorted(TOP_PACKAGES, key=len, reverse=True):
        if rel.startswith(pkg.replace(".", "/") + "/"):
            return pkg
    return None


def parse_deps() -> dict[str, set[str]]:
    edges: dict[str, set[str]] = defaultdict(set)
    for py in ROOT.rglob("*.py"):
        if any(part in PRUNE for part in py.parts):
            continue
        src = module_of(py)
        if not src:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            mod = None
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
            elif isinstance(node, ast.Import):
                for n in node.names:
                    _add_dep(edges, src, n.name)
                continue
            if mod:
                _add_dep(edges, src, mod)
    return edges


def _add_dep(edges: dict[str, set[str]], src: str, mod: str) -> None:
    for pkg in sorted(TOP_PACKAGES, key=len, reverse=True):
        if mod == pkg or mod.startswith(pkg + "."):
            if pkg != src:
                edges[src].add(pkg)
            return


# --------------------------------------------------------------------------- render
def render() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "# Repository Map (auto-generated)",
        "",
        f"> Generated by `scripts/gen_repo_map.py` on {ts}. **Do not edit by hand** — "
        "run `make repo-map` (or `python scripts/gen_repo_map.py`). Narrative docs live in "
        "the other `docs/claude/*.md` files.",
        "",
        "## Source tree",
        "",
        "```",
    ]
    for d in SRC_DIRS:
        base = ROOT / d
        if base.exists() and base.is_dir():
            out.append(f"{d}/")
            out += folder_tree(base)
    out.append("```")

    out += ["", "## LangGraph graphs", ""]
    for path, nodes, edges in parse_graphs():
        out.append(f"### `{path}`")
        out.append("")
        out.append(f"- **Nodes ({len(nodes)}):** " + (", ".join(f"`{n}`" for n in nodes) or "—"))
        if edges:
            out.append("- **Edges:**")
            out.append("")
            out.append("```mermaid")
            out.append("graph TD")
            for a, b in edges:
                out.append(f"    {a} --> {b}")
            out.append("```")
        out.append("")

    out += ["## API route map", ""]
    rows = parse_routes()
    if rows:
        out.append("| Router | Method | Path |")
        out.append("|---|---|---|")
        for mod, method, path in rows:
            out.append(f"| `{mod}` | {method} | `{path}` |")
    else:
        out.append("_No routes parsed._")
    out.append("")

    out += ["## Module dependency graph", "",
            "Top-level package imports (should point downward: "
            "api → nodes → tools → core).", "", "```mermaid", "graph LR"]
    deps = parse_deps()
    for src in sorted(deps):
        for dst in sorted(deps[src]):
            out.append(f'    {_mid(src)}["{src}"] --> {_mid(dst)}["{dst}"]')
    out.append("```")
    out.append("")
    return "\n".join(out)


def _mid(pkg: str) -> str:
    return pkg.replace(".", "_")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
