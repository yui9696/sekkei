"""The architect's review: deterministic lint rules over a design.

Every rule has a stable id, a fixed severity, a message and a fix hint. Rules are
registered with ``@rule`` and enumerated by ``RULES``; ``tests/test_rules.py`` requires
a planted defect for each of them.

Groups: S structure, C consistency, V coverage, A agent-fitness, Q wording (heuristic).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Optional, Union

from . import graph as G
from .model import (
    ACCEPTANCE_KINDS,
    COLLECTIONS,
    COMPONENT_KINDS,
    DECISION_STATUSES,
    ID_PREFIXES,
    INTERFACE_KINDS,
    LEVELS,
    PRIORITIES,
    REQUIREMENT_KINDS,
    SIZES,
    STABILITIES,
    Design,
)

SEVERITIES = ("error", "warning", "info")
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


@dataclass
class Diagnostic:
    rule: str
    severity: str
    message: str
    where: str = ""
    hint: str = ""

    def __str__(self) -> str:  # pragma: no cover - formatting only
        loc = f" [{self.where}]" if self.where else ""
        return f"{self.severity:7} {self.rule}{loc}: {self.message}"


@dataclass
class Rule:
    id: str
    severity: str
    title: str
    hint: str
    fn: Callable[[Design], Iterator[Union[Diagnostic, tuple[str, str]]]] = field(repr=False)

    @property
    def group(self) -> str:
        return self.id[0]


RULES: dict[str, Rule] = {}

_Yield = Union[Diagnostic, tuple[str, str]]


def rule(id_: str, severity: str, title: str, hint: str) -> Callable:
    assert severity in SEVERITIES and id_ not in RULES

    def deco(fn: Callable[[Design], Iterator[_Yield]]) -> Callable:
        RULES[id_] = Rule(id_, severity, title, hint, fn)
        return fn

    return deco


def lint(
    design: Design,
    disable: Iterable[str] = (),
    strict: bool = False,
) -> list[Diagnostic]:
    """Run every rule. ``disable`` takes rule ids or group letters. ``strict`` makes warnings errors."""
    off = set(disable)
    out: list[Diagnostic] = []
    for rid, r in RULES.items():
        if rid in off or r.group in off:
            continue
        for item in r.fn(design):
            if isinstance(item, Diagnostic):
                d = item
                d.rule, d.hint = rid, d.hint or r.hint
            else:
                where, message = item
                d = Diagnostic(rid, r.severity, message, where, r.hint)
            if strict and d.severity == "warning":
                d.severity = "error"
            out.append(d)
    order = {s: i for i, s in enumerate(SEVERITIES)}
    out.sort(key=lambda d: (order[d.severity], d.rule, d.where))
    return out


def has_errors(diags: Iterable[Diagnostic]) -> bool:
    return any(d.severity == "error" for d in diags)


def summary(diags: Iterable[Diagnostic]) -> dict[str, int]:
    counts = {s: 0 for s in SEVERITIES}
    for d in diags:
        counts[d.severity] += 1
    return counts


def format_text(diags: list[Diagnostic], hints: bool = True) -> str:
    if not diags:
        return "OK: no diagnostics\n"
    lines = []
    for d in diags:
        loc = f" [{d.where}]" if d.where else ""
        lines.append(f"{d.severity.upper():7} {d.rule}{loc}: {d.message}")
        if hints and d.hint:
            lines.append(f"        hint: {d.hint}")
    c = summary(diags)
    lines.append(f"{c['error']} error(s), {c['warning']} warning(s), {c['info']} info")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _all_ids(d: Design) -> list[tuple[str, str]]:
    """(collection, id) for every id-bearing object, including acceptance checks."""
    out = [(coll, o.id) for coll in COLLECTIONS for o in getattr(d, coll)]
    out += [("acceptance", a.id) for w in d.work_packages for a in w.acceptance]
    return out


def _references(d: Design) -> Iterator[tuple[str, str, str, str]]:
    """(where, field, target id, expected collection or '*')."""
    for c in d.components:
        for i in c.requires:
            yield c.id, "requires", i, "interfaces"
        for r in c.satisfies:
            yield c.id, "satisfies", r, "requirements"
    for i in d.interfaces:
        yield i.id, "owner", i.owner, "components"
    for e in d.entities:
        yield e.id, "owner", e.owner, "components"
    for f in d.flows:
        for n, s in enumerate(f.steps):
            yield f"{f.id}.steps[{n}]", "from", s.from_, "components"
            yield f"{f.id}.steps[{n}]", "to", s.to, "components"
            yield f"{f.id}.steps[{n}]", "via", s.via, "interfaces"
    for dec in d.decisions:
        for a in dec.affects:
            yield dec.id, "affects", a, "*"
    for k in d.risks:
        for a in k.affects:
            yield k.id, "affects", a, "*"
    for w in d.work_packages:
        for c in w.components:
            yield w.id, "components", c, "components"
        for i in w.implements:
            yield w.id, "implements", i, "interfaces"
        for dep in w.depends_on:
            yield w.id, "depends_on", dep, "work_packages"
        for r in w.satisfies:
            yield w.id, "satisfies", r, "requirements"
        for a in w.acceptance:
            if a.metric:
                yield a.id, "metric", a.metric, "requirements"


_VAGUE = (
    "fast", "quick", "quickly", "easy", "easily", "simple", "scalable", "robust", "efficient",
    "efficiently", "performant", "secure", "user-friendly", "reliable", "flexible", "intuitive",
    "seamless", "etc", "etc.", "and so on", "as needed", "appropriate", "reasonable", "properly",
)
_VAGUE_RE = re.compile(r"(?<![\w-])(" + "|".join(re.escape(v) for v in _VAGUE) + r")(?![\w-])", re.I)

# ---------------------------------------------------------------------------
# S — structure
# ---------------------------------------------------------------------------


@rule("S001", "error", "duplicate id", "Ids must be unique across the whole design; rename one of them.")
def _s001(d: Design) -> Iterator[_Yield]:
    seen: dict[str, str] = {}
    for coll, id_ in _all_ids(d):
        if id_ in seen:
            yield id_, f"id {id_!r} is used by both {seen[id_]} and {coll}"
        else:
            seen[id_] = coll


@rule("S002", "error", "invalid id", "Use letters, digits, '-', '_' or '.', starting with a letter, e.g. WP-3.")
def _s002(d: Design) -> Iterator[_Yield]:
    for coll, id_ in _all_ids(d):
        if not id_:
            yield coll, f"an element of {coll} has no id"
        elif not ID_RE.match(id_):
            yield id_, f"id {id_!r} in {coll} is not a valid identifier"


@rule("S003", "warning", "id prefix convention", "Use the conventional prefix so agents and humans can tell what an id refers to.")
def _s003(d: Design) -> Iterator[_Yield]:
    for coll, id_ in _all_ids(d):
        prefix = ID_PREFIXES[coll]
        if id_ and ID_RE.match(id_) and not id_.startswith(prefix):
            yield id_, f"{coll} ids conventionally start with {prefix!r}"


@rule("S004", "error", "dangling reference", "Every reference must name an existing id of the right kind; add the element or fix the id.")
def _s004(d: Design) -> Iterator[_Yield]:
    index = d.index()
    for where, fld, target, expected in _references(d):
        hit = index.get(target)
        if hit is None:
            yield where, f"{fld} refers to unknown id {target!r}"
        elif expected != "*" and hit[0] != expected:
            yield where, f"{fld} refers to {target!r}, which is a {hit[0]} entry, not {expected}"


@rule("S005", "error", "invalid enumeration value", "Use one of the listed values (see `sekkei schema`).")
def _s005(d: Design) -> Iterator[_Yield]:
    def chk(where: str, fld: str, value: str, allowed: tuple[str, ...]) -> Iterator[_Yield]:
        if value not in allowed:
            yield where, f"{fld}={value!r} is not one of {list(allowed)}"

    for r in d.requirements:
        yield from chk(r.id, "kind", r.kind, REQUIREMENT_KINDS)
        yield from chk(r.id, "priority", r.priority, PRIORITIES)
    for c in d.components:
        yield from chk(c.id, "kind", c.kind, COMPONENT_KINDS)
    for i in d.interfaces:
        yield from chk(i.id, "kind", i.kind, INTERFACE_KINDS)
        yield from chk(i.id, "stability", i.stability, STABILITIES)
    for dec in d.decisions:
        yield from chk(dec.id, "status", dec.status, DECISION_STATUSES)
    for k in d.risks:
        yield from chk(k.id, "likelihood", k.likelihood, LEVELS)
        yield from chk(k.id, "impact", k.impact, LEVELS)
    for w in d.work_packages:
        yield from chk(w.id, "size", w.size, SIZES)
        for a in w.acceptance:
            yield from chk(a.id, "kind", a.kind, ACCEPTANCE_KINDS)


@rule("S006", "warning", "unknown key", "Probably a typo; run `sekkei schema` for the accepted keys.")
def _s006(d: Design) -> Iterator[_Yield]:
    for path, key in d.unknown_keys:
        yield path, f"unknown key {key!r}"


@rule("S007", "error", "missing required text", "Fill in the field; an element without it cannot be briefed.")
def _s007(d: Design) -> Iterator[_Yield]:
    if not d.name.strip():
        yield "$", "the design has no name"
    if d.schema_version != "1":
        yield "$", f"unsupported schema version {d.schema_version!r} (expected '1' in the top-level key 'sekkei')"
    for r in d.requirements:
        if not r.statement.strip():
            yield r.id, "requirement has no statement"
    for c in d.components:
        if not c.name.strip():
            yield c.id, "component has no name"
        if not c.responsibility.strip():
            yield c.id, "component has no responsibility"
    for i in d.interfaces:
        if not i.name.strip():
            yield i.id, "interface has no name"
    for e in d.entities:
        if not e.name.strip():
            yield e.id, "entity has no name"
    for f in d.flows:
        if not f.name.strip():
            yield f.id, "flow has no name"
    for dec in d.decisions:
        if not dec.title.strip():
            yield dec.id, "decision has no title"
    for k in d.risks:
        if not k.description.strip():
            yield k.id, "risk has no description"
    for w in d.work_packages:
        if not w.title.strip():
            yield w.id, "work package has no title"
        for a in w.acceptance:
            if not a.description.strip():
                yield a.id, "acceptance check has no description"


@rule("S008", "error", "empty design", "A design needs at least one requirement, one component and one work package.")
def _s008(d: Design) -> Iterator[_Yield]:
    for coll in ("requirements", "components", "work_packages"):
        if not getattr(d, coll):
            yield "$", f"no {coll}"


# ---------------------------------------------------------------------------
# C — consistency
# ---------------------------------------------------------------------------


@rule("C001", "error", "component requires its own interface", "A component does not call itself through an interface; drop it from `requires`.")
def _c001(d: Design) -> Iterator[_Yield]:
    for c in d.components:
        for i in c.requires:
            iface = d.interface(i)
            if iface is not None and iface.owner == c.id:
                yield c.id, f"requires {i}, which it owns"


@rule("C002", "error", "component dependency cycle", "Break the cycle: extract a shared interface, or turn one edge into an event.")
def _c002(d: Design) -> Iterator[_Yield]:
    cyc = G.find_cycle(G.component_graph(d))
    if cyc:
        yield cyc[0], "cycle: " + " -> ".join(cyc)


@rule("C003", "error", "flow step via an interface the target does not own", "`via` must be an interface owned by `to`.")
def _c003(d: Design) -> Iterator[_Yield]:
    for f in d.flows:
        for n, s in enumerate(f.steps):
            iface = d.interface(s.via)
            if iface is not None and d.component(s.to) is not None and iface.owner != s.to:
                yield f"{f.id}.steps[{n}]", f"{s.via} is owned by {iface.owner}, not by {s.to}"


@rule("C004", "error", "flow step uses an undeclared dependency", "Add the interface to the calling component's `requires`.")
def _c004(d: Design) -> Iterator[_Yield]:
    for f in d.flows:
        for n, s in enumerate(f.steps):
            comp = d.component(s.from_)
            if comp is not None and d.interface(s.via) is not None and s.via not in comp.requires:
                yield f"{f.id}.steps[{n}]", f"{s.from_} calls {s.via} but does not require it"


@rule("C005", "error", "work-package dependency cycle", "Packages must form a DAG; split or reorder them.")
def _c005(d: Design) -> Iterator[_Yield]:
    cyc = G.find_cycle(G.package_graph(d))
    if cyc:
        yield cyc[0], "cycle: " + " -> ".join(cyc)


@rule("C006", "error", "package implements an interface whose owner it does not build", "Add the owning component to the package's `components`, or move the interface.")
def _c006(d: Design) -> Iterator[_Yield]:
    for w in d.work_packages:
        for i in w.implements:
            iface = d.interface(i)
            if iface is not None and iface.owner and iface.owner not in w.components:
                yield w.id, f"implements {i} but {iface.owner} (its owner) is not in components"


@rule("C007", "warning", "implicit package dependency", "Add the target package to `depends_on` (or stub the interface and say so in notes).")
def _c007(d: Design) -> Iterator[_Yield]:
    for a, b, iface in G.implied_package_edges(d):
        yield a, f"uses {iface}, implemented by {b}, without depending on {b}"


@rule("C008", "error", "decision choice is not one of its options", "Set `choice` to the name of one of the listed options.")
def _c008(d: Design) -> Iterator[_Yield]:
    for dec in d.decisions:
        names = [o.name for o in dec.options]
        if dec.choice and dec.choice not in names:
            yield dec.id, f"choice {dec.choice!r} is not among options {names}"


@rule("C009", "error", "package depends on itself", "Remove the self-reference from `depends_on`.")
def _c009(d: Design) -> Iterator[_Yield]:
    for w in d.work_packages:
        if w.id in w.depends_on:
            yield w.id, "depends_on contains the package itself"


# ---------------------------------------------------------------------------
# V — coverage
# ---------------------------------------------------------------------------

_PRIORITY_SEVERITY = {"must": "error", "should": "warning", "could": "info"}


@rule("V001", "error", "requirement satisfied by no component", "Name the component(s) that satisfy it in their `satisfies`, or drop the requirement.")
def _v001(d: Design) -> Iterator[_Yield]:
    tr = G.traceability(d)
    for r in d.requirements:
        if not tr[r.id]["components"]:
            sev = _PRIORITY_SEVERITY.get(r.priority, "error")
            yield Diagnostic("", sev, f"{r.priority} requirement is satisfied by no component", r.id)


@rule("V002", "error", "requirement delivered by no work package", "Add it to the `satisfies` of the package that delivers it.")
def _v002(d: Design) -> Iterator[_Yield]:
    tr = G.traceability(d)
    for r in d.requirements:
        if not tr[r.id]["packages"]:
            sev = _PRIORITY_SEVERITY.get(r.priority, "error")
            yield Diagnostic("", sev, f"{r.priority} requirement is delivered by no work package", r.id)


@rule("V003", "error", "component built by no work package", "Every component must appear in the `components` of at least one package.")
def _v003(d: Design) -> Iterator[_Yield]:
    for c in d.components:
        if c.kind != "external" and not d.packages_building(c.id):
            yield c.id, "component is in no work package, so it will never be built"


@rule("V004", "error", "interface implemented by no work package", "Add it to the `implements` of the package that builds its owner.")
def _v004(d: Design) -> Iterator[_Yield]:
    for i in d.interfaces:
        owner = d.component(i.owner)
        if owner is not None and owner.kind == "external":
            continue
        if not d.packages_implementing(i.id):
            yield i.id, "interface is implemented by no work package"


@rule("V005", "error", "work package without acceptance checks", "Add at least one check; a package with no way to pass cannot be accepted.")
def _v005(d: Design) -> Iterator[_Yield]:
    for w in d.work_packages:
        if not w.acceptance:
            yield w.id, "no acceptance checks"


@rule("V006", "error", "non-functional requirement without a measurable metric", "Give it a metric with a name and a target (e.g. p95 latency, <= 200 ms).")
def _v006(d: Design) -> Iterator[_Yield]:
    for r in d.requirements:
        if r.kind == "nonfunctional" and (r.metric is None or not r.metric.name.strip() or not r.metric.target.strip()):
            yield r.id, "nonfunctional requirement has no metric name/target"


@rule("V007", "warning", "risk without mitigation", "State what is done about it, or accept it explicitly in the mitigation text.")
def _v007(d: Design) -> Iterator[_Yield]:
    for k in d.risks:
        if not k.mitigation.strip():
            yield k.id, "risk has no mitigation"


@rule("V008", "info", "orphan interface", "Nobody requires it and no flow uses it; remove it or declare its consumer.")
def _v008(d: Design) -> Iterator[_Yield]:
    used = {i for c in d.components for i in c.requires}
    used |= {s.via for f in d.flows for s in f.steps}
    for i in d.interfaces:
        owner = d.component(i.owner)
        if owner is not None and owner.kind in ("job", "ui", "cli"):
            continue  # an entry point (job, screen, command line) is invoked by the runtime or a person, not by a component
        if i.id not in used and i.kind not in ("cli", "http", "file"):
            yield i.id, "interface is required by no component and used in no flow"


@rule("V009", "warning", "component satisfies no requirement", "If it is needed, some requirement needs it; add it to `satisfies` or remove the component.")
def _v009(d: Design) -> Iterator[_Yield]:
    for c in d.components:
        if not c.satisfies and c.kind != "external":
            yield c.id, "component satisfies no requirement"


@rule("V010", "warning", "test/command acceptance check without a command", "Give the exact shell command that must exit 0.")
def _v010(d: Design) -> Iterator[_Yield]:
    for w in d.work_packages:
        for a in w.acceptance:
            if a.kind in ("test", "command") and not a.command.strip():
                yield a.id, f"{a.kind} check has no command"


@rule("V011", "warning", "decision with fewer than two options", "A decision with one option is a statement; record what else was considered.")
def _v011(d: Design) -> Iterator[_Yield]:
    for dec in d.decisions:
        if len(dec.options) < 2:
            yield dec.id, f"only {len(dec.options)} option(s) recorded"


# ---------------------------------------------------------------------------
# A — agent-fitness
# ---------------------------------------------------------------------------


@rule("A001", "error", "work package without a write scope", "List the files/directories the agent may change in `files`.")
def _a001(d: Design) -> Iterator[_Yield]:
    for w in d.work_packages:
        if not w.files:
            yield w.id, "no files listed; an agent would have no bounded write scope"


@rule("A002", "error", "unordered packages share a write scope", "Order them with `depends_on`, or split the shared file between them.")
def _a002(d: Design) -> Iterator[_Yield]:
    g = G.package_graph(d)
    closure = {w: G.transitive(g, w) for w in g}
    wps = d.work_packages
    for x in range(len(wps)):
        for y in range(x + 1, len(wps)):
            a, b = wps[x], wps[y]
            if b.id in closure.get(a.id, set()) or a.id in closure.get(b.id, set()):
                continue
            shared = sorted(
                {fa for fa in a.files for fb in b.files if G.in_scope(fa, fb) or G.in_scope(fb, fa)}
                | {fb for fa in a.files for fb in b.files if G.in_scope(fa, fb) or G.in_scope(fb, fa)}
            )
            if shared:
                yield a.id, f"may run in parallel with {b.id} but both may write {shared}"


@rule("A003", "warning", "work package too large for one agent session", "Split it: at most 4 components / 6 interfaces per package keeps a brief within one context.")
def _a003(d: Design) -> Iterator[_Yield]:
    for w in d.work_packages:
        if len(w.components) > 4 or len(w.implements) > 6:
            yield w.id, f"{len(w.components)} components and {len(w.implements)} interfaces"


@rule("A004", "error", "metric acceptance check not tied to a non-functional requirement", "Set `metric` to the id of a nonfunctional requirement with a target.")
def _a004(d: Design) -> Iterator[_Yield]:
    for w in d.work_packages:
        for a in w.acceptance:
            if a.kind != "metric":
                continue
            r = d.requirement(a.metric)
            if r is None or r.kind != "nonfunctional":
                yield a.id, f"metric check must name a nonfunctional requirement (got {a.metric!r})"


@rule("A005", "warning", "no test command in conventions", "Set conventions.test_command so every brief tells the agent how to run the tests.")
def _a005(d: Design) -> Iterator[_Yield]:
    if not d.conventions.test_command.strip():
        yield "$.conventions", "test_command is empty"


# ---------------------------------------------------------------------------
# Q — wording (heuristic)
# ---------------------------------------------------------------------------


@rule("Q001", "warning", "vague wording without a metric", "Replace the adjective with a number, or add a metric to the requirement.")
def _q001(d: Design) -> Iterator[_Yield]:
    for r in d.requirements:
        if r.metric is not None and r.metric.target.strip():
            continue
        hits = sorted({m.group(1).lower() for m in _VAGUE_RE.finditer(r.statement)})
        if hits:
            yield r.id, f"vague word(s) {hits} with no metric"


@rule("Q002", "warning", "requirement statement too short", "A requirement should say who needs what and under which condition.")
def _q002(d: Design) -> Iterator[_Yield]:
    for r in d.requirements:
        if 0 < len(r.statement.strip()) < 20:
            yield r.id, f"statement is {len(r.statement.strip())} characters"


@rule("Q003", "warning", "work-package goal too short", "State the outcome the agent must produce, not just a title.")
def _q003(d: Design) -> Iterator[_Yield]:
    for w in d.work_packages:
        if len(w.goal.strip()) < 20:
            yield w.id, f"goal is {len(w.goal.strip())} characters"


def rule_table() -> str:
    lines = ["| id | severity | rule | hint |", "|---|---|---|---|"]
    for r in RULES.values():
        lines.append(f"| {r.id} | {r.severity} | {r.title} | {r.hint} |")
    return "\n".join(lines) + "\n"
