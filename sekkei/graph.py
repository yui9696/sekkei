"""Graph computations over a design: dependencies, cycles, waves, critical path, traceability.

Everything here is deterministic and uses only the standard library. Unresolved
references are skipped silently; ``sekkei.rules`` reports them (S004).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from .model import Design, WorkPackage

SIZE_WEIGHT = {"S": 1, "M": 2, "L": 4}

Graph = dict[str, set[str]]


def component_graph(design: Design) -> Graph:
    """``A -> B`` iff component A requires an interface owned by component B (A != B)."""
    owner = {i.id: i.owner for i in design.interfaces}
    g: Graph = {c.id: set() for c in design.components}
    for c in design.components:
        for iface in c.requires:
            b = owner.get(iface)
            if b is not None and b != c.id and b in g:
                g[c.id].add(b)
    return g


def package_graph(design: Design) -> Graph:
    """Explicit ``depends_on`` edges between work packages (unresolved targets dropped)."""
    ids = {w.id for w in design.work_packages}
    return {w.id: {d for d in w.depends_on if d in ids and d != w.id} for w in design.work_packages}


def implied_package_edges(design: Design) -> list[tuple[str, str, str]]:
    """Edges ``(A, B, interface)`` where a component of package A requires an interface
    implemented by package B, and A does not (transitively) depend on B already.

    Rule C007 asks the author to make these explicit; ``plan`` treats them as advisory.
    """
    implementer: dict[str, list[str]] = defaultdict(list)
    for w in design.work_packages:
        for i in w.implements:
            implementer[i].append(w.id)
    explicit = package_graph(design)
    closure = {w: transitive(explicit, w) for w in explicit}
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for w in design.work_packages:
        for cid in w.components:
            comp = design.component(cid)
            if comp is None:
                continue
            for iface in comp.requires:
                for other in implementer.get(iface, []):
                    if other == w.id or other in closure[w.id] or (w.id, other) in seen:
                        continue
                    seen.add((w.id, other))
                    out.append((w.id, other, iface))
    return out


def transitive(g: Graph, start: str) -> set[str]:
    seen: set[str] = set()
    stack = list(g.get(start, ()))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(g.get(n, ()))
    return seen


def find_cycle(g: Graph) -> Optional[list[str]]:
    """Return one cycle as ``[a, b, ..., a]`` or None. Deterministic (sorted traversal)."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in g}
    stack: list[str] = []

    def visit(n: str) -> Optional[list[str]]:
        colour[n] = GREY
        stack.append(n)
        for m in sorted(g.get(n, ())):
            if m not in colour:
                continue
            if colour[m] == GREY:
                return stack[stack.index(m) :] + [m]
            if colour[m] == WHITE:
                found = visit(m)
                if found:
                    return found
        stack.pop()
        colour[n] = BLACK
        return None

    for node in sorted(g):
        if colour[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None


def waves(g: Graph) -> list[list[str]]:
    """Kahn layers: wave *n* holds every node whose dependencies all lie in earlier waves.

    Nodes in one wave are mutually independent. Raises ``ValueError`` on a cycle.
    """
    remaining = {n: set(d for d in deps if d in g) for n, deps in g.items()}
    out: list[list[str]] = []
    placed: set[str] = set()
    while remaining:
        ready = sorted(n for n, deps in remaining.items() if deps <= placed)
        if not ready:
            cyc = find_cycle(remaining)
            raise ValueError("dependency cycle: " + " -> ".join(cyc or sorted(remaining)))
        out.append(ready)
        placed.update(ready)
        for n in ready:
            del remaining[n]
    return out


def topological_order(g: Graph) -> list[str]:
    return [n for wave in waves(g) for n in wave]


def critical_path(design: Design) -> tuple[int, list[str]]:
    """Longest path through the package DAG, weighted by size (S=1, M=2, L=4)."""
    g = package_graph(design)
    weight = {w.id: SIZE_WEIGHT.get(w.size, 2) for w in design.work_packages}
    best: dict[str, tuple[int, list[str]]] = {}
    for node in topological_order(g):
        deps = g[node]
        if deps:
            prev = max((best[d] for d in deps), key=lambda t: (t[0], t[1]))
            best[node] = (prev[0] + weight[node], prev[1] + [node])
        else:
            best[node] = (weight[node], [node])
    if not best:
        return 0, []
    return max(best.values(), key=lambda t: (t[0], t[1]))


def ready_packages(design: Design, done: Iterable[str]) -> list[str]:
    """Packages not yet done whose explicit dependencies are all done."""
    done_set = set(done)
    g = package_graph(design)
    return sorted(w for w, deps in g.items() if w not in done_set and deps <= done_set)


def traceability(design: Design) -> dict[str, dict[str, list[str]]]:
    """requirement id -> {components, packages, acceptance} that trace to it."""
    out: dict[str, dict[str, list[str]]] = {
        r.id: {"components": [], "packages": [], "acceptance": []} for r in design.requirements
    }
    for c in design.components:
        for r in c.satisfies:
            if r in out:
                out[r]["components"].append(c.id)
    for w in design.work_packages:
        for r in w.satisfies:
            if r in out:
                out[r]["packages"].append(w.id)
                out[r]["acceptance"].extend(a.id for a in w.acceptance)
        for a in w.acceptance:
            if a.kind == "metric" and a.metric in out and a.id not in out[a.metric]["acceptance"]:
                out[a.metric]["acceptance"].append(a.id)
    return out


def layers(design: Design) -> list[list[str]]:
    """Component layers: layer 0 depends on nothing; each later layer only on earlier ones."""
    return waves(component_graph(design))


def package_for_file(design: Design, path: str) -> list[WorkPackage]:
    """Work packages whose write scope covers ``path`` (exact match or directory prefix)."""
    return [w for w in design.work_packages if any(in_scope(path, f) for f in w.files)]


def in_scope(path: str, scope_entry: str) -> bool:
    p = path.strip("/")
    s = scope_entry.strip("/")
    return p == s or p.startswith(s + "/")
