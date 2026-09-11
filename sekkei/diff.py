"""Compare two versions of a design and say which work packages the change affects.

A brief is generated from the design; if the design changes afterwards, the brief the
agent is working from is stale. ``diff`` lists the changes by id; ``affected_packages``
maps them to the packages whose briefs no longer match.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import COLLECTIONS, Design, to_dict


@dataclass
class Change:
    collection: str
    id: str
    kind: str  # added | removed | changed
    fields: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover
        extra = f" ({', '.join(self.fields)})" if self.fields else ""
        return f"{self.kind:8} {self.collection}/{self.id}{extra}"


def _by_id(design: Design, coll: str) -> dict[str, dict[str, Any]]:
    return {o["id"]: o for o in to_dict(getattr(design, coll))}


def diff(old: Design, new: Design) -> list[Change]:
    """Element-level changes between two designs, in collection order then by id."""
    out: list[Change] = []
    for coll in COLLECTIONS:
        a, b = _by_id(old, coll), _by_id(new, coll)
        for id_ in sorted(set(a) | set(b)):
            if id_ not in b:
                out.append(Change(coll, id_, "removed"))
            elif id_ not in a:
                out.append(Change(coll, id_, "added"))
            elif a[id_] != b[id_]:
                out.append(Change(coll, id_, "changed", [k for k in b[id_] if a[id_].get(k) != b[id_].get(k)]))
    for name in ("conventions", "goals", "non_goals", "name", "version", "summary"):
        if to_dict(getattr(old, name)) != to_dict(getattr(new, name)):
            out.append(Change("$", name, "changed"))
    return out


def affected_packages(new: Design, changes: list[Change]) -> dict[str, list[str]]:
    """Work package id -> reasons its brief is affected by ``changes`` (evaluated on ``new``)."""
    out: dict[str, list[str]] = {}
    changed = {(c.collection, c.id): c for c in changes}

    def hit(wp_id: str, reason: str) -> None:
        out.setdefault(wp_id, []).append(reason)

    for c in changes:
        if c.collection == "$" and c.id == "conventions":
            for w in new.work_packages:
                hit(w.id, "conventions changed")
    for w in new.work_packages:
        if ("work_packages", w.id) in changed:
            hit(w.id, f"package {w.id} {changed[('work_packages', w.id)].kind}")
        for cid in w.components:
            if ("components", cid) in changed:
                hit(w.id, f"component {cid} {changed[('components', cid)].kind}")
            comp = new.component(cid)
            for iid in (comp.requires if comp else []):
                if ("interfaces", iid) in changed:
                    hit(w.id, f"consumed interface {iid} {changed[('interfaces', iid)].kind}")
        for iid in w.implements:
            if ("interfaces", iid) in changed:
                hit(w.id, f"implemented interface {iid} {changed[('interfaces', iid)].kind}")
        for rid in w.satisfies:
            if ("requirements", rid) in changed:
                hit(w.id, f"requirement {rid} {changed[('requirements', rid)].kind}")
        for e in new.entities:
            if e.owner in w.components and ("entities", e.id) in changed:
                hit(w.id, f"entity {e.id} {changed[('entities', e.id)].kind}")
        for dec in new.decisions:
            if ("decisions", dec.id) in changed and set(dec.affects) & (set(w.components) | set(w.implements)):
                hit(w.id, f"decision {dec.id} {changed[('decisions', dec.id)].kind}")
    for c in changes:
        if c.collection == "work_packages" and c.kind == "removed":
            out.setdefault(c.id, []).append("package removed")
    return dict(sorted(out.items()))


def format_diff(changes: list[Change], affected: dict[str, list[str]]) -> str:
    if not changes:
        return "no changes\n"
    lines = [f"{c.kind:8} {c.collection}/{c.id}" + (f" ({', '.join(c.fields)})" if c.fields else "") for c in changes]
    if affected:
        lines.append("affected work packages (their briefs are stale):")
        for wp, reasons in affected.items():
            lines.append(f"  {wp}: " + "; ".join(reasons))
    return "\n".join(lines) + "\n"
