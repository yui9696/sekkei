"""Work packages as deliverable slices.

Until this module existed a package was "the components of one layer that share a pattern,
three at a time". Every independent review scored the result 0/2 and said the same three
things: a package was a catalogue row rather than something a team could finish and show;
one requirement was claimed by four packages at once, so nobody delivered it; and the only
acceptance check a *functional* requirement ever got was "unit tests of <component> pass".

This module cuts the design the other way round — from the requirements:

* **One delivering package per requirement.** The component that actually carries the
  behaviour delivers it (`satisfies`); the other components it touches list it in their
  notes as a constraint, never as a second delivery. A non-functional requirement is
  platform work unless its own sentence names the things a domain slice owns.
* **A slice, not a layer.** A package is a capability or aggregate component with the
  entities it owns, the interfaces it provides, the routes its requirements produced (its
  own router file inside the surface's module namespace, so no two packages ever write the
  same file), and the requirements it delivers end to end. The generic layer (store, auth,
  observability, …) is batched into foundation packages that come first because the slices
  depend on them; the surface application that mounts the routers comes last.
* **Acceptance from the requirement's own sentence.** One check per delivered requirement:
  the operations it must expose, the values it stated, the transition the domain layer read,
  and for non-functional requirements the metric with the tactic's template.
* **A size that can be disputed.** The size is computed from what the package carries and
  the counts are printed in the notes, so a person can argue with the number instead of
  trusting a letter.

Deterministic: every iteration is over a sorted or insertion-ordered structure.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field

from .. import graph as G
from ..model import Acceptance, Component, Design, WorkPackage, metric_text
from . import catalog as K
from . import domain as DM
from . import text as T
from .analysis import Analysis, ReqUnit

#: archetypes that are infrastructure: they may share a foundation package with each other
INFRA = {"store", "queue", "observability", "config", "auth", "scheduler", "cache", "ratelimit", "secrets"}
HTTP_SURFACES = ("surface_api", "admin_api", "ingest_api")
ALL_SURFACES = (*HTTP_SURFACES, "cli", "push", "ui")

_FROM_REQ = re.compile(r"^(?:from|stated in) (R-\d+):")

_METRIC_QUALITY = (("latency", "performance"), ("sustained rate", "performance"), ("duplicate", "consistency"), ("concurrent", "consistency"),
                   ("lost", "durability"), ("availability", "availability"), ("ratio", "availability"), ("unauthenticated", "security"),
                   ("cross-tenant", "security"), ("metrics exposed", "operability"), ("retention", "compliance"), ("deletion", "compliance"),
                   ("instances", "scalability"))


def metric_quality(u: ReqUnit) -> list[str]:
    """The quality a metric measures, read from the metric's name — the acceptance template must
    match the metric, not the component family."""
    if not u.metric:
        return []
    name = u.metric[0].lower()
    if name.startswith("ratio") and not re.search(r"availab|uptime|of (?:requests|payments|days|the time|calls)|successful|error rate|success rate", u.sentence.lower):
        return []            # "CPU not exceeding 60 %", "400 % zoom": a percentage, not an availability target
    return [q for k, q in _METRIC_QUALITY if k in name][:1]


def _num(id_: str) -> int:
    try:
        return int(id_.split("-")[1])
    except (IndexError, ValueError):
        return 0


def _key(c: Component) -> str:
    for t in c.tags:
        if t.startswith("archetype:"):
            return t.split(":", 1)[1]
    return ""


def _fmt(template: str, key: str) -> str:
    return template.format(key=key, Key="".join(p.capitalize() for p in key.split("_")), test="").strip()


# --------------------------------------------------------------------------------------
# 1. who delivers a requirement
# --------------------------------------------------------------------------------------

def _entity_words(d: Design) -> dict[str, set[str]]:
    """component id -> the singular nouns of the entities it owns (its vocabulary)."""
    out: dict[str, set[str]] = {}
    for e in d.entities:
        if not e.owner:
            continue
        words = out.setdefault(e.owner, set())
        words |= {DM.singular(w.lower()) for w in re.split(r"[\s_]+", e.name) if len(w) > 2}
    return out


def delivery_owner(d: Design, an: Analysis) -> dict[str, str]:
    """requirement id -> the one component that delivers it.

    Functional behaviour belongs to the most specific thing that carries it (an aggregate
    before a synthesised owner before a capability before a surface before infrastructure);
    a quality or a constraint is platform work (infrastructure, then the surface) unless its
    own sentence speaks of the things a domain component owns.
    """
    unit_of = {u.id: u for u in an.requirements}
    vocab = _entity_words(d)
    owner: dict[str, str] = {}
    for r in d.requirements:
        cands = [c for c in d.components if r.id in c.satisfies and c.kind != "external"]
        if not cands:
            continue
        u = unit_of.get(r.id)
        sentence_words = {DM.singular(w.lower()) for w in (u.sentence.nouns if u else [])}

        def rank(c: Component) -> tuple[int, int, int]:
            key, domainish = _key(c), ("aggregate" in c.tags or "synthesised" in c.tags)
            speaks_of_it = bool(vocab.get(c.id, set()) & sentence_words)
            if r.kind == "functional":
                base = (0 if "aggregate" in c.tags else 1 if "synthesised" in c.tags
                        else 4 if key in INFRA else 3 if key in ALL_SURFACES else 2)
            elif domainish and speaks_of_it:
                base = 0          # "a claim decision must be recorded within 5 minutes": the claim slice
            else:
                base = 1 if key in INFRA else 2 if key in ALL_SURFACES else 3
            return (base, len(c.satisfies), _num(c.id))

        owner[r.id] = min(cands, key=rank).id
    return owner


# --------------------------------------------------------------------------------------
# 2. the groups
# --------------------------------------------------------------------------------------

@dataclass
class _Group:
    kind: str                    # foundation | slice | surface
    primary: str
    components: list[str]
    layer: int
    extra_files: list[str] = field(default_factory=list)


def _groups(d: Design, internal: list[Component], layer_of: dict[str, int], owned: dict[str, list[str]]) -> list[_Group]:
    foundations: list[_Group] = []
    slices: list[_Group] = []
    surfaces: list[_Group] = []
    infra_by_layer: "OrderedDict[int, list[str]]" = OrderedDict()
    for c in sorted(internal, key=lambda c: (layer_of.get(c.id, 0), _num(c.id))):
        key = _key(c)
        if key in INFRA:
            infra_by_layer.setdefault(layer_of.get(c.id, 0), []).append(c.id)
        elif key in ALL_SURFACES:
            surfaces.append(_Group("surface", c.id, [c.id], layer_of.get(c.id, 0)))
        else:
            slices.append(_Group("slice", c.id, [c.id], layer_of.get(c.id, 0)))
    for layer, ids in infra_by_layer.items():
        # infrastructure of one layer may be batched; three at a time keeps a brief small
        for i in range(0, len(ids), 3):
            chunk = ids[i:i + 3]
            foundations.append(_Group("foundation", chunk[0], chunk, layer))
    # a capability nobody's requirement reaches is support work: it may share a package with
    # the others of *its own layer* (components of one layer never depend on each other, so
    # batching inside a layer can never make a package cycle)
    plain_by_layer: "OrderedDict[int, list[_Group]]" = OrderedDict()
    for g in slices:
        if not owned.get(g.primary):
            plain_by_layer.setdefault(g.layer, []).append(g)
    if sum(len(v) for v in plain_by_layer.values()) > 1:
        merged: list[_Group] = []
        for layer, plain in plain_by_layer.items():
            for i in range(0, len(plain), 3):
                chunk = plain[i:i + 3]
                merged.append(_Group("slice", chunk[0].primary, [g.primary for g in chunk], layer))
        slices = [g for g in slices if owned.get(g.primary)] + merged
    slices.sort(key=lambda g: (g.layer, _num(g.primary)))
    return foundations + slices + surfaces


# --------------------------------------------------------------------------------------
# 3. acceptance
# --------------------------------------------------------------------------------------

def _ops_for(d: Design, req_id: str, comp_ids: set[str], u: ReqUnit | None) -> list[str]:
    """Operation names a requirement must produce: the ones derived from its sentence, plus the
    transitions of its own component whose verb the sentence uses."""
    out: list[str] = []
    for i in d.interfaces:
        for o in i.operations:
            m = _FROM_REQ.match(o.description or "")
            if m and m.group(1) == req_id and o.name not in out:
                out.append(o.name)
    if u is not None:
        verbs = {T._lemma(v) for v in u.sentence.verbs}
        for cid in sorted(comp_ids, key=_num):
            for i in d.provided_by(cid):
                for o in i.operations:
                    head = T._lemma(o.name.split("_")[0].lower())
                    if head in verbs and o.name not in out:
                        out.append(o.name)
    return out


def _stated_values(u: ReqUnit | None) -> list[str]:
    if u is None:
        return []
    return [q.raw for q in u.sentence.quantities if q.kind not in ("code", "number")][:3]


def _transition_note(d: Design, comp_ids: set[str], u: ReqUnit | None) -> str:
    """'leaving the record in the state the text names' — read from the aggregate's transition
    operations (their `pre` carries the allowed source states)."""
    if u is None:
        return ""
    verbs = {T._lemma(v) for v in u.sentence.verbs}
    for cid in sorted(comp_ids, key=_num):
        for i in d.provided_by(cid):
            for o in i.operations:
                if not o.pre.startswith("allowed source states"):
                    continue
                states = o.pre.split(":", 1)[1].strip() if ":" in o.pre else ""
                if states and T._lemma(o.name.split("_")[0].lower()) in verbs:
                    return f"`{o.name}` refuses any source state outside {states}"
    return ""


def _acceptance(d: Design, an: Analysis, wp_reqs: list[str], comp_ids: set[str],
                tests: list[str], layout: K.Layout, keys: list[str], counter: list[int]) -> list[Acceptance]:
    unit_of = {u.id: u for u in an.requirements}
    cmd = layout.test_command.format(test=" ".join(tests), key=keys[0] if keys else "app",
                                     Key="".join(p.capitalize() for p in (keys[0] if keys else "app").split("_")))
    acc: list[Acceptance] = []
    for rid in wp_reqs:
        req = d.requirement(rid)
        if req is None:
            continue
        u = unit_of.get(rid)
        if req.kind == "nonfunctional" and req.metric and req.metric.target != "review":
            mq = metric_quality(u) if u else []
            if req.metric.name.startswith(("value", "number of", "factor", "size", "time")) and not mq:
                continue          # a bare number is not an acceptance check
            if req.rationale.startswith("assumed") and not (mq and mq[0] in ("performance", "availability")
                                                            and ("latency" in req.metric.name or re.search(r"\b9\d(?:\.\d+)? ?%", req.metric.target))):
                continue          # engine assumptions become acceptance checks only for latency and availability
            counter[0] += 1
            tmpl = next((t.acceptance for t in K.TACTICS if mq and t.quality == mq[0] and t.acceptance), "")
            acc.append(Acceptance(f"A-{counter[0]}", f"{rid}: {metric_text(req.metric)}" + (f" — {tmpl}" if tmpl else ""),
                                  "metric", metric=rid))
            continue
        if req.kind == "constraint":
            continue              # constraints are checked by the conventions and the drift check, not by a test
        # functional: a test that exercises this requirement, named after the requirement itself
        statement = " ".join(req.statement.split())
        if len(statement) > 150:
            statement = statement[:147].rstrip() + "…"
        parts = [f"{rid} ({req.priority}): {statement}"]
        ops = _ops_for(d, rid, comp_ids, u)
        if ops:
            parts.append("exercised through " + ", ".join(f"`{o}`" for o in ops[:3]))
        values = _stated_values(u)
        if values:
            parts.append("with the stated values " + ", ".join(values))
        trans = _transition_note(d, comp_ids, u)
        if trans:
            parts.append(trans)
        counter[0] += 1
        acc.append(Acceptance(f"A-{counter[0]}", " — ".join(parts), "test", cmd))
    if not acc:
        counter[0] += 1
        names = ", ".join(d.component(c).name for c in sorted(comp_ids, key=_num) if d.component(c) is not None)
        acc.append(Acceptance(f"A-{counter[0]}", f"unit tests of {names} pass", "test", cmd))
    return acc


# --------------------------------------------------------------------------------------
# 4. size, from what the package carries
# --------------------------------------------------------------------------------------

def _size(d: Design, comp_ids: list[str], wp_reqs: list[str]) -> tuple[str, str]:
    comps = [d.component(c) for c in comp_ids]
    comps = [c for c in comps if c is not None]
    ops = sum(len(i.operations) for c in comps for i in d.provided_by(c.id))
    ents = [e for e in d.entities if e.owner in {c.id for c in comps}]
    fields_ = sum(len(e.fields) for e in ents)
    funcs = sum(1 for r in wp_reqs if (d.requirement(r) is not None and d.requirement(r).kind == "functional"))
    nfrs = sum(1 for r in wp_reqs if (d.requirement(r) is not None and d.requirement(r).kind == "nonfunctional"))
    externals = sum(1 for c in comps for iid in c.requires
                    if (d.interface(iid) is not None and d.component(d.interface(iid).owner) is not None
                        and d.component(d.interface(iid).owner).kind == "external"))
    score = funcs + 0.5 * nfrs + 0.5 * ops + len(ents) + 0.3 * fields_ + 1.5 * externals
    size = "L" if score >= 12 else "S" if score <= 5 else "M"
    why = (f"{funcs} functional + {nfrs} non-functional requirement(s), {ops} operation(s), "
           f"{len(ents)} entit{'y' if len(ents) == 1 else 'ies'} ({fields_} field(s)), {externals} external system(s) "
           f"→ weight {score:.1f} → {size}")
    return size, why


# --------------------------------------------------------------------------------------
# 5. the packages
# --------------------------------------------------------------------------------------

def build(d: Design, an: Analysis, layout: K.Layout, trace: dict, log: list[str]) -> None:
    """Fill ``d.work_packages`` (and ``trace``) with deliverable slices."""
    internal = [c for c in d.components if c.kind != "external"]
    if not internal:
        return
    try:
        layers = G.layers(d)
    except ValueError as exc:      # a cycle: lint reports it; keep one layer so packaging still runs
        log.append(f"component cycle: {exc}")
        layers = [[c.id for c in internal]]
    layer_of = {cid: n for n, L in enumerate(layers) for cid in L}

    owner = delivery_owner(d, an)
    owned: dict[str, list[str]] = {}
    for rid in sorted(owner, key=_num):
        owned.setdefault(owner[rid], []).append(rid)

    groups = _groups(d, internal, layer_of, owned)
    build_pkg = {cid: f"WP-{n}" for n, g in enumerate(groups, 1) for cid in g.components}
    implementer = {i.id: build_pkg[c.id] for c in internal for i in d.provided_by(c.id) if c.id in build_pkg}

    # the surface a slice's routes land on: the first HTTP/CLI surface that calls it
    surface_of: dict[str, tuple[str, str]] = {}      # slice component -> (surface component id, surface key)
    for g in groups:
        if g.kind != "surface":
            continue
        sc = d.component(g.primary)
        if sc is None:
            continue
        for iid in sc.requires:
            iface = d.interface(iid)
            if iface is not None and iface.owner not in surface_of and d.component(iface.owner) is not None:
                surface_of[iface.owner] = (sc.id, _key(sc))

    counter = [0]
    for n, g in enumerate(groups, 1):
        wp_id = f"WP-{n}"
        comps = [d.component(c) for c in g.components]
        comps = [c for c in comps if c is not None]
        keys = [_key(c) for c in comps]
        wp_reqs = sorted({r for c in comps for r in owned.get(c.id, [])}, key=_num)
        files: list[str] = []
        for k in keys:
            files += [_fmt(layout.module, k), _fmt(layout.test, k)]
        routes: list[str] = []
        if g.kind == "slice":
            for c in comps:
                if c.id not in surface_of:
                    continue
                s_id, s_key = surface_of[c.id]
                mine = [o.name for i in d.provided_by(s_id) for o in i.operations
                        if (_FROM_REQ.match(o.description or "") and _FROM_REQ.match(o.description).group(1) in wp_reqs)]
                if not mine:
                    continue
                router_key = f"{s_key}_{_key(c)}"
                files += [_fmt(layout.module, router_key), _fmt(layout.test, router_key)]
                routes += sorted(dict.fromkeys(mine))
        tests = [f for f in files if "test" in f]
        deps = sorted({implementer[i] for c in comps for i in c.requires
                       if i in implementer and implementer[i] != wp_id}, key=_num)
        acc = _acceptance(d, an, wp_reqs, {c.id for c in comps}, tests, layout, keys, counter)

        title = " + ".join(c.name for c in comps)
        goal = "Implement " + "; ".join(f"{c.name}: {c.responsibility.rstrip('.')}" for c in comps) + "."
        if wp_reqs:
            goal += f" Deliver {', '.join(wp_reqs)} end to end — nothing else in the design delivers them."
        if routes:
            s_id, s_key = surface_of[next(c.id for c in comps if c.id in surface_of)]
            surface = d.component(s_id)
            goal += (f" Expose {', '.join(routes[:6])} on the {surface.name if surface else s_key} as a router module"
                     f" of your own ({_fmt(layout.module, f'{s_key}_{keys[0]}')}); the application that mounts it is built by"
                     f" {build_pkg.get(s_id, '?')}.")
        # requirements this package's components touch but do not deliver
        also = sorted({r for c in comps for r in c.satisfies if r not in wp_reqs and owner.get(r)}, key=_num)
        size, why = _size(d, [c.id for c in comps], wp_reqs)
        notes = f"{g.kind}; {why}"
        if also:
            by = OrderedDict()
            for r in also:
                by.setdefault(build_pkg.get(owner[r], "?"), []).append(r)
            notes += ". Also constrained by " + "; ".join(f"{', '.join(v)} (delivered by {k})" for k, v in by.items())
        d.work_packages.append(WorkPackage(wp_id, title, goal, [c.id for c in comps],
                                           [i.id for c in comps for i in d.provided_by(c.id)],
                                           deps, wp_reqs, files, size, acc, notes=notes))
        trace[wp_id] = {"sentences": [], "rules": [f"package:{g.kind}:layer{g.layer}:{keys[0] if keys else '?'}"]}
