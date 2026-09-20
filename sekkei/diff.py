"""Compare two versions of a design and say which work packages the change affects.

A brief is generated from the design; if the design changes afterwards, the brief the
agent is working from is stale. ``diff`` lists the changes by id; ``affected_packages``
maps them to the packages whose briefs no longer match.
"""
from __future__ import annotations

import re
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


#: the field that identifies an element across regenerations (ids are positional and renumber)
NATURAL_KEY = {"requirements": "statement", "components": "name", "interfaces": "name", "entities": "name",
               "flows": "name", "decisions": "title", "risks": "description", "work_packages": "title"}


def _natural(coll: str, obj: dict[str, Any]) -> str:
    return " ".join(str(obj.get(NATURAL_KEY[coll], "")).split()).lower()


def id_map(old: Design, new: Design) -> dict[str, str]:
    """old id -> new id for elements that are the same thing under a different number (matched by their natural key;
    a key that occurs more than once on either side is matched in order)."""
    out: dict[str, str] = {}
    for coll in COLLECTIONS:
        a = to_dict(getattr(old, coll))
        b = to_dict(getattr(new, coll))
        b_by_key: dict[str, list[dict[str, Any]]] = {}
        for o in b:
            b_by_key.setdefault(_natural(coll, o), []).append(o)
        for o in a:
            cands = b_by_key.get(_natural(coll, o))
            if cands:
                out[o["id"]] = cands.pop(0)["id"]
    # acceptance checks: matched by their description with requirement ids already mapped
    def acc_key(desc: str) -> str:
        return " ".join(_ID_IN_TEXT.sub(lambda m: out.get(m.group(0), m.group(0)), desc).split()).lower()
    new_acc: dict[str, list[str]] = {}
    for w in new.work_packages:
        for acc in w.acceptance:
            new_acc.setdefault(" ".join(acc.description.split()).lower(), []).append(acc.id)
    for w in old.work_packages:
        for acc in w.acceptance:
            cands = new_acc.get(acc_key(acc.description))
            if cands:
                out[acc.id] = cands.pop(0)
    return out


_ID_IN_TEXT = re.compile(r"\b(?:R|C|I|E|F|D|K|WP|A)-\d+\b")


def _remap(obj: Any, mapping: dict[str, str]) -> Any:
    """Replace every id string in ``obj`` according to ``mapping`` (ids only appear as whole strings)."""
    if isinstance(obj, dict):
        return {k: _remap(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_remap(v, mapping) for v in obj]
    if isinstance(obj, str):
        if obj in mapping:
            return mapping[obj]
        if _ID_IN_TEXT.search(obj):
            return _ID_IN_TEXT.sub(lambda m: mapping.get(m.group(0), m.group(0)), obj)
    return obj


def diff(old: Design, new: Design) -> list[Change]:
    """Element-level changes between two designs. Elements are matched by content (a requirement by its statement,
    a component by its name, a package by its title), so a design regenerated after one bullet was added reports
    the new element and the packages it touched — not every element that was renumbered. Renumberings are
    reported as ``renumbered`` changes carrying ``old-id -> new-id``; they do not by themselves affect briefs."""
    mapping = id_map(old, new)
    out: list[Change] = []
    for coll in COLLECTIONS:
        a_objs = to_dict(getattr(old, coll))
        b = _by_id(new, coll)
        seen_new: set[str] = set()
        for o in a_objs:
            new_id = mapping.get(o["id"])
            if new_id is None:
                out.append(Change(coll, o["id"], "removed"))
                continue
            seen_new.add(new_id)
            remapped = _remap(o, mapping)
            remapped["id"] = new_id
            target = b[new_id]
            fields = [k for k in target if remapped.get(k) != target.get(k)]
            if fields:
                out.append(Change(coll, new_id, "changed", fields))
            if new_id != o["id"]:
                out.append(Change(coll, new_id, "renumbered", [f"{o['id']} -> {new_id}"]))
        for id_ in sorted(set(b) - seen_new):
            out.append(Change(coll, id_, "added"))
    for name in ("conventions", "goals", "non_goals", "name", "version", "summary"):
        if _remap(to_dict(getattr(old, name)), mapping) != to_dict(getattr(new, name)):
            out.append(Change("$", name, "changed"))
    return out


def affected_packages(new: Design, changes: list[Change]) -> dict[str, list[str]]:
    """Work package id -> reasons its brief is affected by ``changes`` (evaluated on ``new``)."""
    out: dict[str, list[str]] = {}
    changed = {(c.collection, c.id): c for c in changes if c.kind != "renumbered"}

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
    real = [c for c in changes if c.kind != "renumbered"]
    renum = [c for c in changes if c.kind == "renumbered"]
    lines = [f"{c.kind:8} {c.collection}/{c.id}" + (f" ({', '.join(c.fields)})" if c.fields else "") for c in real]
    if renum:
        lines.append(f"renumbered (same content, new id; briefs not affected): " + ", ".join(c.fields[0] for c in renum))
    if not real:
        lines.insert(0, "no content changes")
    if affected:
        lines.append("affected work packages (their briefs are stale):")
        for wp, reasons in affected.items():
            lines.append(f"  {wp}: " + "; ".join(reasons))
    return "\n".join(lines) + "\n"
