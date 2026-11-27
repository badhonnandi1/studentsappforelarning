"""Module boundary checks that import-linter cannot express compactly.

1. Only module X may import ``app.modules.X.internal``.
2. Every edge between module public packages must be listed in scripts/module_edges.toml,
   and the allowed edges must form an acyclic graph.
3. Inside ``internal``, ``fastapi`` may be imported only from ``routes`` and ``schemas``
   (and ``services/actor.py``-style dependency modules listed in ``fastapi_allowed``).
"""

from __future__ import annotations

import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

import grimp

ROOT = Path(__file__).resolve().parent.parent
EDGES_FILE = ROOT / "scripts" / "module_edges.toml"
FASTAPI_LAYERS = ("routes", "schemas")


def module_of(name: str) -> str | None:
    parts = name.split(".")
    if len(parts) >= 3 and parts[:2] == ["app", "modules"]:
        return parts[2]
    return None


def load_config(path: Path = EDGES_FILE) -> tuple[set[tuple[str, str]], set[str]]:
    data = tomllib.loads(path.read_text())
    edges = {(src, dst) for src, targets in data.get("edges", {}).items() for dst in targets}
    allowed = set(data.get("fastapi_allowed", {}).get("modules", []))
    return edges, allowed


def find_cycle(edges: Iterable[tuple[str, str]]) -> list[str] | None:
    graph: dict[str, set[str]] = {}
    for src, dst in edges:
        graph.setdefault(src, set()).add(dst)
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            if state.get(nxt) == 1:
                return [*stack[stack.index(nxt) :], nxt]
            if nxt not in state and (cycle := visit(nxt)):
                return cycle
        stack.pop()
        state[node] = 2
        return None

    for node in sorted(graph):
        if node not in state and (cycle := visit(node)):
            return cycle
    return None


def violations(
    graph: grimp.ImportGraph, edges: set[tuple[str, str]], allowed: set[str]
) -> list[str]:
    problems: list[str] = []
    for importer in sorted(graph.modules):
        src = module_of(importer)
        for imported in sorted(graph.find_modules_directly_imported_by(importer)):
            if imported == "fastapi" or imported.startswith("fastapi."):
                parts = importer.split(".")
                if (
                    src
                    and "internal" in parts
                    and not any(layer in parts for layer in FASTAPI_LAYERS)
                    and importer not in allowed
                ):
                    problems.append(f"{importer} imports fastapi outside routes/schemas")
                continue
            dst = module_of(imported)
            if dst is None or dst == src:
                continue
            if ".internal" in imported and not imported.startswith(f"app.modules.{src}."):
                problems.append(f"{importer} imports private {imported}")
            if src is not None and (src, dst) not in edges:
                problems.append(
                    f"{importer} -> {imported}: edge {src}->{dst} not in module_edges.toml"
                )
    return problems


def main() -> int:
    edges, allowed = load_config()
    problems: list[str] = []
    if cycle := find_cycle(edges):
        problems.append("module_edges.toml has a cycle: " + " -> ".join(cycle))
    graph = grimp.build_graph("app", include_external_packages=True)
    problems.extend(violations(graph, edges, allowed))
    for line in problems:
        print(line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
