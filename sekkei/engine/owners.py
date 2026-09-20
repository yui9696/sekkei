"""Owners for requirements no pattern recognised: match an existing component, or synthesise one.

Order: (1) lexical overlap with existing components (score >= 2 shared tokens wins);
(2) a human actor with a view/manage verb -> the surface and the core; (3) a new
component from the verb class and the object of the sentence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..model import Component, Design, Interface, Operation, Param
from . import catalog as K
from . import text as T
from .analysis import ReqUnit

READ_VERBS = {"read", "poll", "fetch", "receive", "scan", "measure", "collect", "ingest", "import", "load", "listen", "sample", "record", "track"}
CONTROL_VERBS = {"open", "close", "switch", "adjust", "control", "drive", "actuate", "move", "set", "send", "write", "trigger", "run", "schedule", "enable", "disable", "print"}
COMPUTE_VERBS = {"compute", "calculate", "generate", "render", "convert", "transform", "aggregate", "trim", "filter", "parse", "validate", "verify", "process", "count", "sign", "archive", "purge"}
VIEW_VERBS = {"see", "view", "show", "get", "list", "search", "query", "inspect", "check", "download", "export", "manage", "update", "edit", "change", "configure", "create", "add", "delete", "remove", "save", "reuse", "register", "submit", "upload", "share", "invite", "assign", "approve", "reject", "book", "reserve", "order", "pay", "cancel", "choose", "subscribe", "confirm", "keep"}

_SURFACES = ("surface_api", "admin_api", "ingest_api", "cli", "ui", "push")
#: archetypes too generic to claim a requirement by word overlap
_GENERIC = {"core", "store", "observability", "config", "queue", "auth", *_SURFACES}


@dataclass
class Placement:
    requirement: str
    owners: list[str]
    how: str                       # matched (score n) | surface+core | synthesised
    detail: str = ""
    created: list[str] = field(default_factory=list)


def _tokens_of(c: Component, d: Design, exclude_unit: str = "") -> set[str]:
    words = set(T.tokens(c.name + " " + c.responsibility))
    for i in d.provided_by(c.id):
        for o in i.operations:
            if exclude_unit and f"from {exclude_unit}:" in o.description:
                continue  # an operation derived from this very sentence is not evidence of ownership
            words |= set(re.split(r"[_\s/]+", o.name.lower()))
    return {T._lemma(w) for w in words if w not in T.STOPWORDS and len(w) > 2}


def _sentence_tokens(u: ReqUnit) -> set[str]:
    return {T._lemma(w) for w in u.sentence.nouns + u.sentence.verbs if len(w) > 2}


_NON_HUMAN = {"tool", "command", "program", "script", "application", "app", "controller", "device", "bot", "job",
              "system", "service", "services", "team", "we", "truck", "trucks", "vehicle", "vehicles", "sensor", "sensors"}


def _human_subject(u: ReqUnit) -> bool:
    """True when a human actor is the grammatical subject: it appears before the first verb
    ("The grower adjusts ..." yes; "It opens the vents according to the grower's setpoints" no)."""
    words = u.sentence.words
    first_verb = next((i for i, w in enumerate(words) if T.verb_of(w)), len(words))
    head = set(words[:first_verb])
    for actor in u.sentence.actors:
        if actor in _NON_HUMAN:
            continue
        if actor.split()[0] in head:
            return True
    return False


def _archetype_of(c: Component) -> str:
    return next((t.split(":", 1)[1] for t in c.tags if t.startswith("archetype:")), "")


def _object_phrase(verb: str, u: ReqUnit) -> str:
    """Up to two object tokens after the verb ('reads temperature and humidity from four sensors' -> 'temperature')."""
    words = u.sentence.words
    for i, w in enumerate(words):
        if T.verb_of(w) == verb:
            run = []
            for w2 in words[i + 1: i + 7]:
                ok = (w2 not in T.STOPWORDS and not T.verb_of(w2) and w2 not in T.NON_OBJECTS and len(w2) > 2
                      and re.match(r"^[a-z][a-z_-]*$", w2) and not w2.endswith(("ly", "ing", "ed")))
                if ok:
                    run.append(w2)
                    if len(run) == 2:
                        break
                elif run:
                    break
            if run:
                return run[-1]
    return ""


def place(u: ReqUnit, d: Design, layout: K.Layout, cid: dict[str, str], iid: dict[str, str], requires: dict[str, list[str]]) -> Placement:
    """Choose or create the owner(s) of an unrecognised functional requirement. Mutates ``d`` when creating."""
    stoks = _sentence_tokens(u)
    internal = [c for c in d.components if c.kind != "external"]
    verbs = list(dict.fromkeys(u.sentence.verbs))
    human = _human_subject(u)
    surfaces = [k for k in _SURFACES if k in cid]
    if human:  # a use case: the surface takes it in, the core does it
        owners = [cid[surfaces[0]]] if surfaces else []
        if "core" in cid:
            owners.append(cid["core"])
        if owners:
            return Placement(u.id, owners, "surface+core", f"human actor {sorted(u.sentence.actors)[0]!r}: a use case")
    specific = [c for c in internal if _archetype_of(c) not in _GENERIC]
    scored = sorted(((len(stoks & _tokens_of(c, d, u.id)), c) for c in specific), key=lambda t: (-t[0], t[1].id))
    if scored and scored[0][0] >= 2:
        score, comp = scored[0]
        return Placement(u.id, [comp.id], f"matched (score {score})", f"shared tokens with {comp.name}: {', '.join(sorted(stoks & _tokens_of(comp, d, u.id)))}")
    # a prohibition, a statement without a verb, or one whose verbs only state a need: a rule the core enforces,
    # never a new component named after a stray noun ("Apac processor", "Slow processor")
    from .text import STATIVE_VERBS
    real_verbs = [v for v in verbs if v not in STATIVE_VERBS]
    if u.sentence.prohibition or not real_verbs:
        owners = [cid["core"]] if "core" in cid else ([cid[surfaces[0]]] if surfaces else [])
        if owners:
            why = "a prohibition: a rule the core enforces" if u.sentence.prohibition else "no operation-like verb: a rule/property the core carries"
            return Placement(u.id, owners, "core rule", why)
    # synthesise
    verb = next((v for v in verbs if v in READ_VERBS | CONTROL_VERBS | COMPUTE_VERBS), verbs[0] if verbs else "")
    obj = _object_phrase(verb, u) if verb else ""
    if not obj:
        obj = next((n for n in u.sentence.nouns if n not in T.NON_OBJECTS and n not in T.ACTORS and not n.endswith(("ly", "ing", "ed"))), "domain")
    if verb in READ_VERBS:
        role, layer, kind, verb_word = "reader", 1, "module", "read"
    elif verb in CONTROL_VERBS:
        role, layer, kind, verb_word = "controller", 1, "module", "apply"
    else:
        role, layer, kind, verb_word = "processor", 1, "module", "process"
    key = re.sub(r"[^a-z0-9]+", "_", f"{obj}_{role}")
    if key in cid:  # already synthesised for an earlier sentence
        comp = d.component(cid[key])
        iface = d.interface(iid[key])
        for v in verbs:
            o = _object_phrase(v, u)
            name = f"{v}_{o}" if o else v
            if name not in {x.name for x in iface.operations}:
                iface.operations.append(Operation(name, [Param(o or "input", "…")], "…", ["…"], description=f"from {u.id}: {u.sentence.text[:90]}"))
        comp.satisfies.append(u.id)
        return Placement(u.id, [comp.id], "synthesised", f"added to {comp.name}")
    n = len(d.components) + 1
    name = f"{obj.capitalize()} {role}"
    responsibility = {
        "reader": f"Reads {obj} from its source and hands validated readings to the core.",
        "controller": f"Applies the core's decisions to the {obj} and reports the actual state back.",
        "processor": f"Computes over {obj} on behalf of the core.",
    }[role]
    comp = Component(f"C-{n}", name, responsibility + f" Synthesised from {u.id}; no catalogue pattern matched.", kind,
                     layout.module.format(key=key, Key="".join(p.capitalize() for p in key.split("_"))),
                     requires=[], satisfies=[u.id], tags=[f"layer:{layer}", f"archetype:{key}", "synthesised"])
    ops = []
    for v in verbs:
        o = _object_phrase(v, u)
        opname = f"{v}_{o}" if o else v
        if opname not in {x.name for x in ops}:
            ops.append(Operation(opname, [Param(o or "input", "…")], "…", ["…"], description=f"from {u.id}: {u.sentence.text[:90]}"))
    if not ops:
        ops.append(Operation(f"{verb_word}_{obj}", [Param(obj, "…")], "…", ["…"], description=f"from {u.id}: {u.sentence.text[:90]}"))
    iface = Interface(f"I-{n}", f"{name} interface", comp.id, "module", ops, "draft",
                      f"Provided by {name}. Contract derived from {u.id}; fill in the types marked '…'.")
    d.components.append(comp)
    d.interfaces.append(iface)
    cid[key], iid[key] = comp.id, iface.id
    requires[key] = []
    # wire: the core uses readers/processors; controllers are used by the core too
    if "core" in cid:
        core = d.component(cid["core"])
        if iface.id not in core.requires:
            core.requires.append(iface.id)
        requires.setdefault("core", []).append(key)
    if "observability" in cid and iid["observability"] not in comp.requires:
        comp.requires.append(iid["observability"])
        requires[key].append("observability")
    return Placement(u.id, [comp.id], "synthesised", f"new component {name} ({role}) from verb {verb!r} and object {obj!r}", [comp.id, iface.id])


def placements_markdown(ps: list[Placement], d: Design) -> str:
    if not ps:
        return "Every functional requirement matched a catalogue pattern.\n"
    s = ["| requirement | owner(s) | how | detail |", "|---|---|---|---|"]
    for p in ps:
        names = ", ".join(f"{o} {d.component(o).name}" for o in p.owners if d.component(o))
        s.append(f"| {p.requirement} | {names} | {p.how} | {p.detail} |")
    return "\n".join(s) + "\n"
