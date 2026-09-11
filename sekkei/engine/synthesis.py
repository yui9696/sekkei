"""Synthesis: Analysis + catalogue -> Design.

Deterministic. Every element carries a trace (which sentences, which catalogue rules).
"""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field

from .. import graph as G
from ..model import (
    Acceptance, Component, Conventions, Decision, Design, Entity, FieldDef, Flow, Interface, Metric,
    Operation, Option, Param, Requirement, Risk, Step, WorkPackage,
)
from . import catalog as K
from . import text as T
from .analysis import Analysis, ReqUnit
from .evaluate import decide
from .owners import Placement, place

# archetype -> archetypes that call it (in addition to Archetype.needs), applied when both are active
CONSUMERS: dict[str, list[str]] = {
    "observability": ["surface_api", "admin_api", "ingest_api", "worker", "scheduler", "policy", "core", "cli", "batch", "push", "notifier", "dispatcher"],
    "dispatcher": ["worker"],
    "signer": ["worker"],
    "secrets": ["admin_api", "core"],
    "auth": ["surface_api", "ingest_api", "push"],
    "ratelimit": ["surface_api", "admin_api", "ingest_api"],
    "cache": ["core"],
    "search": ["surface_api", "admin_api", "cli"],
    "files": ["core"],
    "exporter": ["surface_api", "cli", "batch"],
    "bus": ["push", "core"],
    "payments": ["core"],
    "model": ["core"],
    "audit": ["core"],
    "notifier": ["core"],
    "queue": ["worker", "scheduler"],
    "config": ["cli", "surface_api", "admin_api", "ingest_api", "worker"],
    "scheduler": ["batch"],
    "policy": [],
    "core": ["policy", "worker", "batch"],
}

# entity template -> owning archetype (default: store)
ENTITY_OWNER = {"secret": "secrets", "work_item": "queue", "audit_entry": "audit", "file": "files"}

# pattern -> (archetype, operation name) whose contract receives the quantities of the pattern's sentences
QUANTITY_SINK = {
    "async_delivery": ("scheduler", "next_attempt"),
    "health_policy": ("policy", "evaluate"),
    "signing": ("secrets", "rotate"),
    "batch_pipeline": ("batch", "run"),
    "scheduler_jobs": ("scheduler", "promote_due"),
    "rate_limiting": ("ratelimit", "check"),
    "file_storage": ("files", "put"),
}

# quality -> archetypes that carry it (used to map non-functional requirements to components)
QUALITY_CARRIERS = {
    "durability": ["queue", "store", "ingest_api"],
    "consistency": ["store", "core"],
    "performance": ["surface_api", "admin_api", "ingest_api", "worker", "search", "cache", "cli"],
    "isolation": ["queue", "worker"],
    "security": ["auth", "signer", "secrets", "dispatcher", "admin_api"],
    "operability": ["observability"],
    "scalability": ["surface_api", "ingest_api", "worker", "queue"],
    "availability": ["observability", "queue"],
    "compliance": ["audit", "store"],
    "simplicity": ["core"],
    "cost": ["store"],
    "usability": ["surface_api", "cli"],
}

_HTTP_SURFACES = ("surface_api", "admin_api", "ingest_api")
_ALL_SURFACES = (*_HTTP_SURFACES, "cli", "push", "ui")


@dataclass
class Synthesis:
    design: Design
    trace: dict[str, dict[str, list]] = field(default_factory=dict)
    generic: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)
    #: (decision id, decision key, title, [(option name, score), (option name, score)]) where the top two are within CLOSE_MARGIN
    close_calls: list[tuple[str, str, str, list[tuple[str, float]]]] = field(default_factory=list)


CLOSE_MARGIN = 0.15


def _layout(an: Analysis) -> K.Layout:
    lang = an.languages[0] if an.languages else K.DEFAULT_LANGUAGE
    return K.LAYOUTS.get(lang, K.LAYOUTS[K.DEFAULT_LANGUAGE])


def _fmt(template: str, key: str) -> str:
    return template.format(key=key, Key="".join(p.capitalize() for p in key.split("_")), test="").strip()


def _active_archetypes(an: Analysis) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """Active archetype keys in a stable order, the generic ones, and archetype -> reasons (trace)."""
    reasons: dict[str, list[str]] = {}
    active: "OrderedDict[str, None]" = OrderedDict()
    pats = [p for p in K.PATTERNS if p.id in an.patterns]
    # crud_api is redundant when every API sentence is a management or ingest sentence
    if "crud_api" in an.patterns and any(p in an.patterns for p in ("admin_api", "event_ingest", "cli_tool")):
        crud_only = [u for u in an.requirements if "crud_api" in u.patterns
                     and not set(u.patterns) & {"admin_api", "event_ingest", "cli_tool"}
                     and any(T.VERBS.get(v, ("",))[0] for v in u.sentence.verbs)]
        if not crud_only:
            pats = [p for p in pats if p.id != "crud_api"]
    for p in pats:
        for a in p.archetypes:
            active.setdefault(a, None)
            reasons.setdefault(a, []).append(f"pattern:{p.id}")
    for t in K.TACTICS:
        if t.quality in an.qualities:
            for a in t.archetypes:
                active.setdefault(a, None)
                reasons.setdefault(a, []).append(f"tactic:{t.quality}")
    generic: list[str] = []
    human = {"staff", "manager", "managers", "grower", "owner", "owners", "member", "members", "employee", "employees",
             "customer", "customers", "user", "users", "admin", "admins", "administrator", "operator", "operators",
             "visitor", "visitors", "client", "clients", "subscriber", "subscribers", "anyone", "people", "developer", "developers"}
    if pats and not any(a in active for a in _ALL_SURFACES) \
            and any(set(u.sentence.actors) & human for u in an.requirements if u.kind == "functional"):
        active.setdefault("surface_api", None)
        reasons.setdefault("surface_api", []).append("inference:human-actors-need-a-surface")
    if not pats:
        low = " ".join(s.lower for s in an.sentences)
        surface = ("cli" if re.search(r"\bcli\b|command[- ]line|\bstdin\b|\bterminal\b", low)
                   else "ui" if "no_network" in an.constraints or re.search(r"\bpanel\b|\bscreen\b|\bdisplay\b", low)
                   else "surface_api")
        for a in (surface, "core", "store", "config"):
            active.setdefault(a, None)
            reasons.setdefault(a, []).append("fallback:layered")
            generic.append(a)
    elif an.unrecognised:
        # unrecognised functional sentences need a home: the core (and a surface if none exists)
        active.setdefault("core", None)
        reasons.setdefault("core", []).append("fallback:unrecognised")
        if not any(a in active for a in (*_HTTP_SURFACES, "cli", "push", "ui")) \
                and any(u.sentence.actors for u in an.unrecognised):
            key = "ui" if "no_network" in an.constraints else "surface_api"
            active.setdefault(key, None)
            reasons.setdefault(key, []).append("fallback:unrecognised")
            generic.append(key)
    # close under needs
    changed = True
    while changed:
        changed = False
        for a in list(active):
            for n in K.ARCHETYPES[a].needs:
                if n not in active:
                    active[n] = None
                    reasons.setdefault(n, []).append(f"needed-by:{a}")
                    changed = True
    order = sorted(active, key=lambda a: (K.ARCHETYPES[a].layer, list(K.ARCHETYPES).index(a)))
    return order, generic, reasons


def _requires(active: list[str]) -> dict[str, list[str]]:
    req: dict[str, list[str]] = {a: [] for a in active}
    for a in active:
        for n in K.ARCHETYPES[a].needs:
            if n in req and n != a and n not in req[a]:
                req[a].append(n)
    for provider, consumers in CONSUMERS.items():
        if provider in req:
            for c in consumers:
                if c in req and c != provider and provider not in req[c]:
                    req[c].append(provider)
    return req


def _is_object(w: str) -> bool:
    return (w not in T.STOPWORDS and not T.verb_of(w) and w not in T.NON_OBJECTS and len(w) > 2
            and re.match(r"^[a-z][a-z_-]*$", w) is not None and not w.endswith(("ly", "ing", "ed")))


def _object_after(verb: str, sentence: T.Sentence) -> str:
    """The noun that follows a verb ('rotate the signing secret' -> 'secret'); else the nearest noun before it."""
    words = sentence.words
    for i, w in enumerate(words):
        if T.verb_of(w) == verb:
            # forward: the head of the first noun run after the verb ("add stock items" -> "items");
            # verbs and fillers before the run are skipped, the run is at most two tokens long
            run: list[str] = []
            for w2 in words[i + 1: i + 7]:
                if _is_object(w2):
                    run.append(w2)
                    if len(run) == 2:
                        break
                elif run:
                    break
            forward = [run[-1]] if run else []
            backward = [w2 for w2 in reversed(words[max(0, i - 6): i]) if _is_object(w2)]
            passive = w.endswith("ed") and i > 0 and words[i - 1] in T._PASSIVE_AUX
            order = (backward + forward) if passive else (forward + backward)
            if order:
                return order[0]
    return ""


#: verbs that describe what the system does internally, never a surface operation
_INTERNAL_VERBS = {"deliver", "sign", "notify", "persist", "process", "write", "log", "record", "track",
                   "measure", "store", "validate", "verify", "compute", "generate", "render", "convert", "parse",
                   "schedule", "aggregate", "archive", "authenticate", "authorize", "transform", "send", "read", "receive"}
_HTTP_ONLY_INTERNAL = {"run", "print"}  # entry points for a CLI, never HTTP operations


def _plural(noun: str) -> str:
    if noun.endswith("s"):
        return noun
    if noun.endswith("y") and not noun.endswith(("ay", "ey", "oy")):
        return noun[:-1] + "ies"
    return noun + "s"


def _derived_ops(units: list[ReqUnit], surface_kind: str) -> list[Operation]:
    """Operations for a surface/core from the verbs and objects of its functional sentences."""
    seen: dict[str, Operation] = {}
    for u in units:
        if not u.sentence.actors:
            continue  # behaviour statements ("each event is delivered ...") are contracts, not use cases
        for v in dict.fromkeys(u.sentence.verbs):
            method, iverb = T.VERBS.get(v, ("", v))
            obj = _object_after(v, u.sentence)
            if not obj:
                continue
            if surface_kind in ("http", "cli") and v in _INTERNAL_VERBS:
                continue
            if surface_kind == "http" and v in _HTTP_ONLY_INTERNAL:
                continue
            if surface_kind == "http":
                if not method:
                    continue
                coll = _plural(obj)
                if iverb in ("create", "register", "add", "publish", "submit", "upload", "send"):
                    name, inputs, out = f"POST /{coll}", [("body", f"{obj} fields")], f"201 {{{obj} id}}"
                    errs = ["400 invalid body", "401 unauthenticated", "409 conflict"]
                elif iverb in ("list", "search", "query", "export"):
                    name, inputs, out = f"GET /{coll}", [("filter", "query"), ("page", "cursor")], f"200 [{obj}], next cursor"
                    errs = ["401 unauthenticated"]
                elif iverb in ("get", "download", "check"):
                    name, inputs, out = f"GET /{coll}/{{id}}", [("id", "str")], f"200 {obj}"
                    errs = ["401 unauthenticated", "404 unknown id"]
                elif iverb in ("delete", "revoke", "purge"):
                    name, inputs, out = f"DELETE /{coll}/{{id}}", [("id", "str")], "204"
                    errs = ["401 unauthenticated", "404 unknown id"]
                elif iverb in ("update", "set", "configure"):
                    name, inputs, out = f"PUT /{coll}/{{id}}", [("id", "str"), ("body", f"{obj} fields")], f"200 {obj}"
                    errs = ["400 invalid body", "401 unauthenticated", "404 unknown id"]
                else:  # an action on a resource: rotate, redeliver, disable, enable, retry, run, trigger, cancel
                    name, inputs, out = f"POST /{coll}/{{id}}/{iverb}", [("id", "str")], f"202 {iverb} accepted"
                    errs = ["401 unauthenticated", "404 unknown id", "409 not applicable in current state"]
            elif surface_kind == "cli":
                name, inputs, out, errs = f"{iverb} {obj}", [("args", "parsed flags")], "exit 0; result on stdout", ["exit 2 on invalid input"]
            else:
                name, inputs, out, errs = f"{iverb}_{obj}", [(obj, f"{obj.capitalize()} | id")], f"{obj.capitalize()} | None", ["ValidationError", "NotFound"]
            if name not in seen:
                seen[name] = Operation(name, [Param(n, t) for n, t in inputs], out, errs,
                                       description=f"from {u.id}: {u.sentence.text[:90].rstrip()}")
    return list(seen.values())


def _metric_of(u: ReqUnit) -> Metric | None:
    if u.metric is None:
        return None
    name, target, unit = u.metric
    return Metric(name, target, unit)


def _satisfiers(u: ReqUnit, active: list[str], surfaces: list[str]) -> list[str]:
    """Archetype keys that satisfy a requirement unit."""
    out: list[str] = []
    if u.kind == "functional":
        for pid in u.patterns:
            pat = next(p for p in K.PATTERNS if p.id == pid)
            for a in pat.archetypes:
                if a in active and a not in ("store",) and a not in out:
                    out.append(a)
        if not out:
            out = [a for a in ("core",) if a in active] + surfaces[:1]
    elif u.kind == "nonfunctional":
        for q in u.qualities:
            for a in QUALITY_CARRIERS.get(q, []):
                if a in active and a not in out:
                    out.append(a)
        if not out:
            out = surfaces[:1] or (["core"] if "core" in active else [])
    else:  # constraint
        low = u.sentence.lower
        if re.search(r"postgres|mysql|sqlite|database|redis", low) and "store" in active:
            out.append("store")
        if re.search(r"container|stateless|deploy|ingress|instances?|kubernetes|serverless", low):
            out.extend(s for s in surfaces if s not in out)
            if "worker" in active:
                out.append("worker")
        if re.search(r"\b(python|typescript|node|go|rust|java|kotlin|ruby|elixir|c#)\b|standard library|dependenc|team of|region", low) and "core" in active:
            out.append("core")
        if re.search(r"auth|oidc|identity|token|sso", low) and "auth" in active:
            out.append("auth")
        if not out:
            out = ["core"] if "core" in active else active[:1]
    return out


def synthesise(an: Analysis, forced_decisions: dict[str, str] | None = None,
               owner_overrides: dict[str, str] | None = None) -> Synthesis:
    """``forced_decisions``: decision key or title -> option name (or prefix). ``owner_overrides``:
    requirement statement -> component name (or id) that must own it instead of the engine's choice."""
    forced_decisions = forced_decisions or {}
    owner_overrides = owner_overrides or {}
    layout = _layout(an)
    active, generic_keys, reasons = _active_archetypes(an)
    requires = _requires(active)
    trace: dict[str, dict[str, list]] = {}
    log: list[str] = []
    d = Design(name=T.slug(an.title), version="0.1.0", summary=an.summary or an.title)
    d.goals = [K_p.summary for K_p in K.PATTERNS if K_p.id in an.patterns and K_p.summary]
    d.non_goals = list(an.non_goals)

    # --- requirements ------------------------------------------------------
    for u in an.requirements:
        rationale = "assumed by the engine; confirm or override" if u.sentence.assumed else ""
        if not u.recognised:
            rationale = (rationale + "; " if rationale else "") + "no catalogue pattern matched; owner chosen by the engine (see the notes)"
        d.requirements.append(Requirement(u.id, u.sentence.text, u.kind, u.priority, _metric_of(u), rationale=rationale))
        trace[u.id] = {"sentences": [u.sentence.index], "rules": [f"pattern:{p}" for p in u.patterns] + [f"quality:{q}" for q in u.qualities]}

    # --- components + interfaces ---------------------------------------------
    cid: dict[str, str] = {}
    iid: dict[str, str] = {}
    for n, key in enumerate(active, 1):
        cid[key] = f"C-{n}"
        iid[key] = f"I-{n}"
    surfaces = [a for a in active if a in _ALL_SURFACES]
    functional_units = [u for u in an.requirements if u.kind == "functional"]

    for key in active:
        at = K.ARCHETYPES[key]
        path = "" if at.kind == "external" else _fmt(layout.module, key)
        comp = Component(cid[key], at.name, at.responsibility, at.kind, path,
                         requires=[iid[n] for n in requires[key]], tags=[f"layer:{at.layer}", f"archetype:{key}"])
        if key in generic_keys:
            comp.tags.append("generic")
            comp.responsibility += " (generic: no pattern recognised; refine)"
        d.components.append(comp)
        trace[comp.id] = {"sentences": [], "rules": reasons.get(key, [])}
        ops = [Operation(o.name, [Param(nm, tp) for nm, tp in o.inputs], o.output, list(o.errors), o.pre, o.post, o.description) for o in at.ops]
        # derived operations from the sentences this archetype's patterns own
        my_patterns = {p.id for p in K.PATTERNS if key in p.archetypes and p.id in an.patterns}
        if key in _HTTP_SURFACES or key in ("cli", "core"):
            mine = [u for u in functional_units if set(u.patterns) & my_patterns or (not u.recognised and key in ("core", *surfaces[:1]))]
            if key == "core":
                mine = functional_units
            derived = _derived_ops(mine, "http" if key in _HTTP_SURFACES else ("cli" if key == "cli" else "module"))
            names = {o.name for o in ops}
            ops += [o for o in derived if o.name not in names]
        if key == "core" and not ops:
            ops.append(Operation("validate", [Param("record", "dict")], "None", ["ValidationError listing every invalid field"]))
        iface = Interface(iid[key], f"{at.name} interface", cid[key], at.iface_kind, ops,
                          "stable" if at.kind in ("datastore", "external") else "draft",
                          description=f"Provided by {at.name}. " + ("External; contract is theirs." if at.kind == "external" else ""))
        d.interfaces.append(iface)
        trace[iface.id] = {"sentences": sorted({u.sentence.index for u in functional_units if set(u.patterns) & my_patterns}), "rules": reasons.get(key, [])}

    # quantities from pattern sentences flow into the contract that consumes them
    for pid, (akey, opname) in QUANTITY_SINK.items():
        if pid in an.patterns and akey in cid:
            qs = [(u.id, q) for u in an.requirements for q in u.sentence.quantities
                  if pid in u.patterns and u.kind == "functional" and q.kind not in ("code", "number")]
            if qs:
                iface = d.interface(iid[akey])
                op = next((o for o in iface.operations if o.name == opname), None)
                if op is not None:
                    note = "; ".join(f"{q.raw}{(' ' + q.noun) if q.kind == 'count' and q.noun and q.noun not in q.raw else ''} ({rid})" for rid, q in qs)
                    op.pre = (op.pre + "; " if op.pre else "") + "stated values: " + note
                    trace[iface.id]["rules"].append(f"quantities:{pid}")

    # --- owners for requirements no pattern recognised ------------------------
    placements: list[Placement] = []
    for u in an.unrecognised:
        chosen = owner_overrides.get(u.sentence.text)
        target = None
        if chosen:
            target = d.component(chosen) or next((c for c in d.components if c.name.lower() == chosen.lower()), None)
        if target is not None:
            p = Placement(u.id, [target.id], "chosen in the interview", f"owner {target.name} named by the human")
        else:
            p = place(u, d, layout, cid, iid, requires)
        placements.append(p)
        for owner in p.owners:
            comp = d.component(owner)
            if comp is not None and u.id not in comp.satisfies:
                comp.satisfies.append(u.id)
        for created in p.created:
            trace[created] = {"sentences": [u.sentence.index], "rules": ["owner:synthesised"]}
        trace[u.id]["rules"].append(f"owner:{p.how}")

    # --- requirement -> component mapping ------------------------------------
    for u in an.requirements:
        if not u.recognised:
            continue
        for key in _satisfiers(u, active, surfaces):
            comp = d.component(cid[key])
            if comp is not None and u.id not in comp.satisfies:
                comp.satisfies.append(u.id)
                trace[comp.id]["sentences"].append(u.sentence.index)

    # --- entities ------------------------------------------------------------
    ekeys: list[str] = []
    for p in K.PATTERNS:
        if p.id in an.patterns:
            for e in p.entities:
                if e not in ekeys and (ENTITY_OWNER.get(e, "store") in cid):
                    ekeys.append(e)
    if not ekeys and "store" in cid:
        nouns = [n for u in functional_units for n in u.sentence.nouns]
        top = max(set(nouns), key=lambda n: (nouns.count(n), -nouns.index(n))) if nouns else "record"
        tmpl = K.ENTITIES["record"]
        d.entities.append(Entity("E-1", top.capitalize().rstrip("s") or "Record", cid["store"],
                                 [FieldDef(n, t, c) for n, t, c in tmpl.fields], f"Generic record named after the most frequent noun ('{top}'); refine the fields."))
        trace["E-1"] = {"sentences": [], "rules": ["fallback:top-noun"]}
    for n, e in enumerate(ekeys, 1):
        tmpl = K.ENTITIES[e]
        owner = cid[ENTITY_OWNER.get(e, "store")]
        d.entities.append(Entity(f"E-{n}", tmpl.name, owner, [FieldDef(nm, tp, c) for nm, tp, c in tmpl.fields], tmpl.description))
        trace[f"E-{n}"] = {"sentences": [], "rules": [f"entity:{e}"]}

    # --- flows -----------------------------------------------------------------
    fkeys: list[str] = []
    for p in K.PATTERNS:
        if p.id in an.patterns:
            for f in p.flows:
                if f not in fkeys:
                    fkeys.append(f)
    if not fkeys:
        fkeys = ["cli_run" if "cli" in cid else "request"]
    n = 0
    for fk in fkeys:
        ft = K.FLOWS[fk]
        if not all(a in cid and b in cid for a, b, _ in ft.steps):
            continue
        n += 1
        steps = []
        for a, b, desc in ft.steps:
            steps.append(Step(cid[a], cid[b], iid[b], desc))
            comp = d.component(cid[a])
            if iid[b] not in comp.requires and a != b:
                comp.requires.append(iid[b])
        d.flows.append(Flow(f"F-{n}", ft.name, ft.trigger, steps))
        trace[f"F-{n}"] = {"sentences": [], "rules": [f"flow:{fk}"]}

    # --- decisions (scored) ------------------------------------------------------
    dkeys: list[str] = []
    for p in K.PATTERNS:
        if p.id in an.patterns:
            dkeys += [x for x in p.decisions if x not in dkeys]
    for t in K.TACTICS:
        if t.quality in an.qualities:
            dkeys += [x for x in t.decisions if x not in dkeys]
    for dk, dp in K.DECISIONS.items():
        if "*" in dp.trigger and dk not in dkeys:
            dkeys.append(dk)
    n = 0
    chosen: dict[str, str] = {}
    close_calls: list[tuple[str, str, str, list[tuple[str, float]]]] = []
    for dk in dkeys:
        dp = K.DECISIONS[dk]
        affects = [cid[a] for a in dp.affects if a in cid]
        if not affects:
            continue
        forced = forced_decisions.get(dk) or forced_decisions.get(dp.title)
        best, ranked, rationale, consequences = decide(dp, an.qualities, an.constraints, forced)
        n += 1
        chosen[dk] = best.option.name
        avail = [s for s in ranked if s.available]
        if not forced and len(avail) >= 2 and avail[0].score - avail[1].score < CLOSE_MARGIN:
            close_calls.append((f"D-{n}", dk, dp.title, [(s.option.name, s.score) for s in avail[:2]]))
        d.decisions.append(Decision(f"D-{n}", dp.title, dp.context, [Option(o.name, list(o.pros), list(o.cons)) for o in dp.options],
                                    best.option.name, rationale, consequences, affects, "accepted"))
        trace[f"D-{n}"] = {"sentences": [], "rules": [f"decision:{dk}"] + [f"quality:{q}" for q in an.qualities]}

    # --- risks ---------------------------------------------------------------------
    rkeys: list[str] = []
    for p in K.PATTERNS:
        if p.id in an.patterns:
            rkeys += [x for x in p.risks if x not in rkeys]
    for t in K.TACTICS:
        if t.quality in an.qualities:
            rkeys += [x for x in t.risks if x not in rkeys]
    if an.unrecognised or generic_keys:
        rkeys.append("unrecognised")
    if chosen.get("store_tech", "").startswith("SQLite"):
        rkeys.append("single_writer")
    n = 0
    for rk in rkeys:
        rt = K.RISKS[rk]
        affects = [cid[a] for a in rt.affects if a in cid]
        if not affects and rk != "unrecognised":
            continue
        n += 1
        d.risks.append(Risk(f"K-{n}", rt.description, rt.likelihood, rt.impact, rt.mitigation, affects))
        trace[f"K-{n}"] = {"sentences": [], "rules": [f"risk:{rk}"]}

    # --- conventions ------------------------------------------------------------------
    rules = list(layout.rules)
    for t in K.TACTICS:
        if t.quality in an.qualities and t.convention and t.convention not in rules:
            rules.append(t.convention)
    full = " ".join(s.text for s in an.sentences)
    m = re.search(r"\b(python|node|typescript|go|rust|java)\s*(\d+(?:\.\d+)?)", full, re.I)
    if m:
        rules.append(f"{m.group(1).capitalize()} {m.group(2)} as stated in the constraints.")
    if re.search(r"standard library only|no (?:third[- ]party|external) dependenc", full, re.I):
        rules.append("Standard library only; no third-party runtime dependencies.")
    if "containers" in an.constraints or "multi_instance" in an.constraints:
        rules.append("Stateless processes: configuration from the environment, no local files that a second instance would not see.")
    d.conventions = Conventions(layout.language, layout.test_all, layout.lint_command, rules,
                                ["Acceptance checks of the package pass.", "No file outside the write scope changed.",
                                 "Every public operation of the implemented interfaces exists with the declared inputs."])

    # --- work packages ------------------------------------------------------------------
    internal = [c for c in d.components if c.kind != "external"]
    try:
        layers = G.layers(d)
    except ValueError as exc:  # a cycle: fall back to archetype layers (repair/lint will report it)
        log.append(f"component cycle: {exc}")
        layers = [[c.id for c in internal]]
    family_of: dict[str, str] = {}
    for c in internal:
        key = c.tags[1].split(":")[1]
        fam = next((p.id for p in K.PATTERNS if p.id in an.patterns and key in p.archetypes), "infra")
        family_of[c.id] = fam
    groups: list[list[str]] = []
    for layer in layers:
        ids = [c for c in layer if d.component(c).kind != "external"]
        ids.sort(key=lambda c: (family_of[c], int(c.split("-")[1])))
        for i in range(0, len(ids), 3):
            groups.append(ids[i:i + 3])
    implementer: dict[str, str] = {}
    for n, ids in enumerate(groups, 1):
        for c in ids:
            for i in d.provided_by(c):
                implementer[i.id] = f"WP-{n}"
    acc_n = 0
    for n, ids in enumerate(groups, 1):
        comps = [d.component(c) for c in ids]
        wp_id = f"WP-{n}"
        deps = sorted({implementer[i] for c in comps for i in c.requires if i in implementer and implementer[i] != wp_id},
                      key=lambda w: int(w.split("-")[1]))
        satisfies = sorted({r for c in comps for r in c.satisfies}, key=lambda r: int(r.split("-")[1]))
        keys = [c.tags[1].split(":")[1] for c in comps]
        files = []
        for k in keys:
            files += [_fmt(layout.module, k), _fmt(layout.test, k)]
        tests = [f for f in files if "test" in f]
        acc: list[Acceptance] = []
        acc_n += 1
        acc.append(Acceptance(f"A-{acc_n}", f"unit tests of {', '.join(c.name for c in comps)} pass",
                              "test", layout.test_command.format(test=" ".join(tests), key=keys[0], Key=keys[0].capitalize())))
        for r in satisfies:
            req = d.requirement(r)
            if req is not None and req.kind == "nonfunctional":
                acc_n += 1
                unit = next((u for u in an.requirements if u.id == r), None)
                tmpl = next((t.acceptance for t in K.TACTICS if unit and t.quality in unit.qualities and t.acceptance), "")
                acc.append(Acceptance(f"A-{acc_n}", f"{r}: {req.metric.name} {req.metric.target} {req.metric.unit}".strip()
                                      + (f" — {tmpl}" if tmpl else ""), "metric", metric=r))
        title = " + ".join(c.name for c in comps)
        goal = "Implement " + "; ".join(f"{c.name}: {c.responsibility.rstrip('.')}" for c in comps) + "."
        d.work_packages.append(WorkPackage(wp_id, title, goal, ids, [i.id for c in comps for i in d.provided_by(c.id)],
                                           deps, satisfies, files, "S" if len(ids) == 1 else "M", acc,
                                           notes=f"family: {family_of[ids[0]]}"))
        trace[wp_id] = {"sentences": [], "rules": [f"package:layer{[i for i, L in enumerate(layers) if ids[0] in L][0]}:{family_of[ids[0]]}"]}
    return Synthesis(d, trace, [cid[k] for k in generic_keys if k in cid], log, placements, close_calls)
