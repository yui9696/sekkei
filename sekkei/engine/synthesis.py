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
    Operation, Option, Param, Requirement, Risk, Step, WorkPackage, metric_text,
)
from . import catalog as K
from . import domain as DM
from . import text as T
from .analysis import Analysis, ReqUnit
from .evaluate import decide
from .owners import Placement, _human_subject, place

# archetype -> archetypes that call it (in addition to Archetype.needs), applied when both are active
CONSUMERS: dict[str, list[str]] = {
    "observability": ["surface_api", "admin_api", "ingest_api", "worker", "scheduler", "policy", "core", "cli", "batch", "push", "notifier", "dispatcher", "mqtt_consumer", "geo"],
    "geo": ["core"],
    "sms": ["notifier"],
    "chat": ["notifier"],
    "sftp_target": ["exporter", "batch"],
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
    "verifier": ["core"],
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
    "security": ["data_protection", "auth", "signer", "secrets", "dispatcher", "admin_api"],
    "operability": ["observability"],
    "scalability": ["surface_api", "ingest_api", "worker", "queue"],
    "availability": ["observability", "queue"],
    "compliance": ["data_protection", "audit", "store"],
    "simplicity": ["core"],
    "cost": ["store"],
    "usability": ["surface_api", "cli"],
}

#: archetypes that are infrastructure: they may share a work package with each other
_INFRA = {"store", "queue", "observability", "config", "auth", "scheduler", "cache", "ratelimit", "secrets"}
_HTTP_SURFACES = ("surface_api", "admin_api", "ingest_api")
_ALL_SURFACES = (*_HTTP_SURFACES, "cli", "push", "ui")
_HUMAN_SURFACES = ("surface_api", "admin_api", "cli", "ui")   # where a person's use case enters


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


def _peak_rate(an: Analysis) -> float:
    """The largest stated rate in items per second (0 when none)."""
    rates = [T.per_second(q) or 0.0 for u in an.requirements for q in u.sentence.quantities if q.kind == "rate" and not u.sentence.assumed]
    return max(rates, default=0.0)


_ENTITY_STOP = T.ENTITY_STOP


def _domain_entities(an: Analysis, functional_units: list[ReqUnit]) -> list[tuple[str, list[str]]]:
    """Candidate domain entities: objects of create/register/upload/request/send verbs and frequent plural nouns,
    with attributes taken from a parenthesis right after the noun ('readings (speed, fuel level, ...)')."""
    counts: dict[str, int] = {}
    attrs: dict[str, list[str]] = {}
    for u in functional_units:
        if u.sentence.assumed:
            continue
        text = u.sentence.text
        for v in u.sentence.verbs:
            if v in ("create", "register", "upload", "request", "send", "publish", "submit", "add", "store", "record", "rate", "book", "order", "accept", "offer", "charge", "tag"):
                o = _object_after(v, u.sentence)
                if o:
                    counts[o] = counts.get(o, 0) + 2
        words = u.sentence.words
        for i, n in enumerate(u.sentence.nouns):
            if n.endswith("s") and len(n) > 4 and not T.verb_of(n):
                counts[n] = counts.get(n, 0) + 1
        for i, w in enumerate(words[:-1]):
            if w in ("a", "an", "the", "each", "every", "per") and _is_object(words[i + 1]):
                counts[words[i + 1]] = counts.get(words[i + 1], 0) + 1
        for m in re.finditer(r"\b([a-z]+) \(([^)]{3,80})\)", text.lower()):
            noun, inside = m.group(1), m.group(2)
            fields = [f.strip() for f in inside.split(",") if f.strip() and len(f.strip().split()) <= 3]
            if fields:
                attrs[noun] = fields
    merged: dict[str, int] = {}
    for n, c in counts.items():
        base = _singular(n)
        if base in _ENTITY_STOP or n in _ENTITY_STOP or base in T.ACTORS or n in T.ACTORS or len(base) < 3:
            continue
        merged[base] = merged.get(base, 0) + c
    top = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    out = []
    for base, c in top:
        if c < 2:
            continue
        out.append((base, attrs.get(base) or attrs.get(base + "s") or []))
    return out


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
    human = T.HUMAN_ACTORS
    if "mqtt_ingest" in an.patterns and "ingest_api" in active and not re.search(r"\bhttp\b|\brest\b|\bapi\b", " ".join(s.lower for s in an.sentences if not s.assumed)):
        del active["ingest_api"]  # devices publish over MQTT; an HTTP ingest surface would be redundant
    if pats and not any(a in active for a in _HUMAN_SURFACES) \
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
    # punctuation kept as tokens so that a parenthesis or a comma ends a noun run:
    # "create an application (amount, term)" -> application, not amount
    words: list[str] = []
    for m in re.finditer(r"([a-zA-Z][a-zA-Z0-9_-]*)(\.(?=\s|$))?|\d[\d,.:]*|[(),;:]", sentence.text.lower()):
        if m.group(1):
            words.append(m.group(1).rstrip("-"))
            if m.group(2):
                words.append(".")          # a sentence end stops a noun run
        else:
            words.append(m.group(0) if m.group(0) in "(),;:" else "#")   # a number stops a noun run too
    actor_words = {t for a in sentence.actors for t in a.split()} | {a + "s" for a in sentence.actors} | {a.rstrip("s") for a in sentence.actors}
    for i, w in enumerate(words):
        if T.verb_of(w) == verb and not (i > 0 and words[i - 1] in T._DETERMINERS):
            # forward: the head of the first noun run after the verb ("add stock items" -> "items");
            # verbs and fillers before the run are skipped, the run is at most two tokens long
            run: list[str] = []
            prev = w
            for w2 in words[i + 1: i + 9]:
                if w2 in ("(", ")", ",", ";", ":", ".", "#"):
                    if run:
                        break
                    if w2 in ("(", ".", "#"):
                        break
                    prev = w2
                    continue
                after_det = prev in T._DETERMINERS
                prev = w2
                # "an offer", "the order": a lexicon verb after a determiner is the object
                if _is_object(w2) or (after_det and T.verb_of(w2) and w2 not in T.STOPWORDS and len(w2) > 2) \
                        or (run and T.verb_of(w2) and w2.endswith("s") and len(w2) > 3):
                    run.append(w2)
                    if len(run) == 2:
                        break
                elif run:
                    break
            forward = [run[-1]] if run else []
            backward = [w2 for w2 in reversed(words[max(0, i - 6): i]) if _is_object(w2) and w2 not in actor_words and w2 not in ("(", ")", ".", "#")]
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


_NOT_PLURAL = {"redis", "kubernetes", "previous", "status", "analysis", "basis", "bus", "campus", "census", "chassis", "corpus", "crisis",
               "diagnosis", "focus", "gas", "lens", "news", "series", "species", "virus", "plus", "minus", "bonus", "canvas", "atlas", "alias",
               "https", "sms", "dns", "tls", "ops", "aws", "gcs", "ios", "macos", "class", "process", "access", "address", "business", "success",
               "always", "sometimes", "various", "serious", "obvious", "continuous", "anonymous", "famous", "less", "unless", "us", "this", "yes"}


def _singular(n: str) -> str:
    """'orders' -> 'order', 'entries' -> 'entry'; words that only look plural (redis, status, previous) stay."""
    if n in _NOT_PLURAL or n.endswith(("ss", "us", "is", "ous", "ess", "ness")) or len(n) < 4:
        return n
    if n.endswith("ies") and len(n) > 4:
        return n[:-3] + "y"
    if n.endswith(("ches", "shes", "xes", "sses")):
        return n[:-2]
    if n.endswith("s"):
        return n[:-1]
    return n


def _plural(noun: str) -> str:
    if noun.endswith("s"):
        return noun
    if noun.endswith("y") and not noun.endswith(("ay", "ey", "oy")):
        return noun[:-1] + "ies"
    return noun + "s"


def _actor_is_subject(s: T.Sentence) -> bool:
    """True when an actor word comes before the first verb of the sentence (it is the subject)."""
    words = s.words
    first_verb = next((i for i, w in enumerate(words) if T.verb_of(w) in s.verbs and not (i > 0 and words[i - 1] in T._DETERMINERS)), len(words))
    actor_toks = {t.rstrip("s") for a in s.actors for t in a.split()}
    for a in sorted(s.actors, key=len, reverse=True):
        toks = a.split()
        for i in range(min(first_verb, len(words))):
            if [w.rstrip("s") for w in words[i: i + len(toks)]] == [t.rstrip("s") for t in toks]:
                # everything before the actor must be a determiner or a plain modifier — not an imperative
                # ("Email the customer …", "Notify operators …") and not a lexicon verb
                before = [w for w in words[:i] if w.rstrip("s") not in actor_toks]
                if any(T.verb_of(w) or w in _IMPERATIVES for w in before):
                    return False
                return True
    return False


_IMPERATIVES = {"email", "notify", "alert", "slack", "page", "text", "message", "ping", "sms", "call", "tell", "inform", "remind", "warn", "escalate", "show", "give", "let", "allow", "ask"}


_ATTRIBUTE_WORDS = {"price", "prices", "notional", "status", "state", "priority", "threshold", "thresholds", "name", "limit", "limits", "quantity",
                    "amount", "expiry", "date", "dates", "time", "settings", "setting", "level", "levels", "address", "email", "phone", "role",
                    "roles", "permission", "permissions", "schedule", "schedules", "description", "title", "tag", "tags", "flag", "flags",
                    "value", "values", "field", "fields", "detail", "details", "point", "points", "score", "rate", "fee", "bps", "window"}


def _resource_for(obj: str, sentence: T.Sentence, dents: list) -> str:
    """The REST resource behind an object word: 'amend the limit price of a working order' → order (price is a field of
    Order, and the sentence speaks of orders); an attribute word without a known entity in the sentence stays as it is."""
    if not dents:
        return obj
    words = {DM.singular(w) for w in sentence.words}
    base = DM.singular(obj)
    for e in dents:
        if e.name in words and e.name != base and (base in {f[0] for f in e.fields} or base.replace("-", "_") in {f[0] for f in e.fields} or (base in _ATTRIBUTE_WORDS and obj in _ATTRIBUTE_WORDS)
                                                    or base in T.TECH_WORDS or base in T.NON_OBJECTS):
            return e.name          # "upload PDF and Markdown documents": the resource is documents, PDF is a format
    return obj


_BAD_RESOURCES = {"another", "anothers", "urgent", "urgents", "ask", "asks", "past", "pasts", "fail", "fails", "number", "numbers", "laptop", "laptops",
                  "history", "histories", "ble", "bles", "full", "fulls", "previous", "matchs", "completes", "mobiles", "multiples", "cannots", "same",
                  "own", "other", "others", "first", "last", "next", "new", "old", "current", "time", "times", "way", "ways", "case", "cases"}
_res_text_cache: dict = {}


def _resource_ok(obj: str, u: ReqUnit, dents: list, units: list[ReqUnit]) -> bool:
    """A REST resource is a thing the text keeps: a domain entity, or a noun that occurs determined/plural somewhere and is not
    an adjective, participle, person or technology word."""
    base = DM.singular(obj)
    if base in {e.name for e in dents}:
        return True
    if obj in _BAD_RESOURCES or base in _BAD_RESOURCES or base in T.TECH_WORDS or base.endswith(("ly", "ed", "ing")) or base in T.NON_OBJECTS:
        return False
    if base in T.ACTORS or obj in T.ACTORS or any(base == a.split()[-1] for a in u.sentence.actors):
        return False
    key = id(units)
    if key not in _res_text_cache:
        _res_text_cache.clear()
        _res_text_cache[key] = " ".join(x.sentence.text for x in units).lower()
    low = _res_text_cache[key]
    return bool(re.search(r"\b(?:a|an|the|each|every|its|their|per|one|\d+)\s+(?:[a-z-]+\s+)?" + re.escape(base) + r"s?\b", low)
                or re.search(r"\b" + re.escape(base) + r"(?:s|es)\b", low) and base + "s" != obj or obj.endswith("s") and low.count(obj) >= 2)


def _derived_ops(units: list[ReqUnit], surface_kind: str, dents: list | None = None) -> list[Operation]:
    """Operations for a surface/core from the verbs and objects of its functional sentences."""
    seen: dict[str, Operation] = {}
    dents = dents or []
    for u in units:
        if not u.sentence.actors:
            continue  # behaviour statements ("each event is delivered ...") are contracts, not use cases
        if not _actor_is_subject(u.sentence):
            continue  # "Email the customer …": the actor is the object; a notification, not a use case
        stated = re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_{}/.-]+)", u.sentence.text)
        if stated and surface_kind == "http":
            for method_, path_ in stated:
                name = f"{method_} {path_}"
                if name not in seen:
                    seen[name] = Operation(name, [Param("id", "str")] if "{" in path_ else [Param("body", "json")], "200" if method_ == "GET" else "202 accepted",
                                           ["401 unauthenticated", "404 unknown id"] if "{" in path_ else ["400 invalid body", "401 unauthenticated"],
                                           description=f"stated in {u.id}: {u.sentence.text[:90].rstrip()}")
            continue          # the author named the routes; do not invent others from the same sentence
        for v in dict.fromkeys(u.sentence.verbs):
            if v in T.STATIVE_VERBS:
                continue
            method, iverb = T.VERBS.get(v, ("", v))
            obj = _object_after(v, u.sentence)
            if not obj:
                continue
            obj = _resource_for(obj, u.sentence, dents)
            if surface_kind == "http" and not _resource_ok(obj, u, dents, units):
                continue
            if surface_kind in ("http", "cli") and v in _INTERNAL_VERBS:
                continue
            if surface_kind == "http" and v in _HTTP_ONLY_INTERNAL:
                continue
            if surface_kind == "http":
                if not method:
                    continue
                coll = _plural(obj)
                plural_obj = obj.endswith("s") and not obj.endswith(("ss", "us", "is")) and len(obj) > 3
                if iverb in ("get", "view", "check") and plural_obj:
                    iverb = "list"          # "see all returns", "view their orders": a listing, not one resource
                if iverb in ("create", "register", "add", "publish", "submit", "upload", "send", "request", "book", "order", "reserve", "invite", "place", "enter", "raise", "open", "file", "log", "issue"):
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
                stated = [q for q in u.sentence.quantities if q.kind not in ("code", "number")]
                pre = ("stated values: " + "; ".join(f"{q.raw}{(' ' + q.noun) if q.kind == 'count' and q.noun and q.noun not in q.raw else ''} ({u.id})" for q in stated)) if stated else ""
                seen[name] = Operation(name, [Param(n, t) for n, t in inputs], out, errs, pre=pre,
                                       description=f"from {u.id}: {u.sentence.text[:90].rstrip()}")
    return list(seen.values())


def _size_of(comps, d: Design, satisfies: list[str]) -> str:
    """Package size from what it carries: operations to implement, entities to model, functional requirements to satisfy."""
    ops = sum(len(i.operations) for c in comps for i in d.provided_by(c.id))
    ents = sum(1 for e in d.entities if e.owner in {c.id for c in comps})
    reqs = sum(1 for r in satisfies if (d.requirement(r) is not None and d.requirement(r).kind == "functional"))
    if ops >= 8 or reqs >= 8 or ents >= 3 or (ops >= 5 and reqs >= 5):
        return "L"
    if ops <= 3 and reqs <= 3 and ents <= 1:
        return "S"
    return "M"


def _metric_of(u: ReqUnit) -> Metric | None:
    if u.metric is None:
        return None
    name, target, unit = u.metric
    return Metric(name, target, unit)


_METRIC_QUALITY = (("latency", "performance"), ("sustained rate", "performance"), ("duplicate", "consistency"), ("concurrent", "consistency"),
                   ("lost", "durability"), ("availability", "availability"), ("ratio", "availability"), ("unauthenticated", "security"),
                   ("cross-tenant", "security"), ("metrics exposed", "operability"), ("retention", "compliance"), ("deletion", "compliance"),
                   ("instances", "scalability"))


def _metric_quality(u: ReqUnit) -> list[str]:
    """The quality a metric measures, read from the metric's name — the acceptance template must match the metric, not the component family."""
    if not u.metric:
        return []
    name = u.metric[0].lower()
    if name.startswith("ratio") and not re.search(r"availab|uptime|of (?:requests|payments|days|the time|calls)|successful|error rate|success rate", u.sentence.lower):
        return []            # "CPU not exceeding 60 %", "400 % zoom": a percentage, not an availability target
    return [q for k, q in _METRIC_QUALITY if k in name][:1]


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
        # the sentence's own patterns first (「個人情報は暗号化して保存」 belongs to data protection, not to auth)
        for pid in u.patterns:
            pat = next(p for p in K.PATTERNS if p.id == pid)
            for a in pat.archetypes:
                if a in active and a not in ("store", "core") and a not in out:
                    out.append(a)
        for q in _metric_quality(u) or u.qualities:
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
        if an.structure and u.sentence.text in an.structure.rationales:
            rationale = (rationale + "; " if rationale else "") + "so that " + an.structure.rationales[u.sentence.text]
        if u.sentence.row_id:
            rationale = (rationale + "; " if rationale else "") + f"source id {u.sentence.row_id}"
        if an.normalisation and u.sentence.text in an.normalisation.sources:
            rationale = (rationale + "; " if rationale else "") + "source (ja): " + an.normalisation.sources[u.sentence.text]
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
    # the domain model reads every stated sentence: a use case with a latency target is filed as non-functional but still names its things
    early_dents = DM.extract(an, [u for u in an.requirements if u.kind != "constraint"]) if "store" in active else []

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
            elif key in _HUMAN_SURFACES and key == next((a for a in active if a in _HUMAN_SURFACES), None):
                mine = [u for u in functional_units if _human_subject(u) and not u.sentence.assumed] + [u for u in mine if u not in functional_units or not _human_subject(u)]
            derived = _derived_ops(mine, "http" if key in _HTTP_SURFACES else ("cli" if key == "cli" else "module"), early_dents)
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

    # --- domain aggregates: one component per cluster of related entities -------
    dents = early_dents if "store" in cid else []
    agg_of_entity: dict[str, str] = {}      # entity name -> archetype key of its aggregate component
    for group in DM.aggregates(dents):
        top = next((e for e in group if any(k == "has_many" for k, _, _ in e.relations)), group[0])   # the root owns the aggregate
        if not (top.kept or any(e.kept for e in group)) or (top.score < 4 and len(group) < 2):
            continue
        key = "domain_" + re.sub(r"[^a-z0-9]+", "_", top.name)
        if key in cid:
            continue
        n = len(d.components) + 1
        name = f"{top.display} domain"
        ents_txt = ", ".join(e.display for e in group)
        bits = []
        for e in group:
            if e.states:
                bits.append(f"{e.display} states: " + ", ".join(e.states) + ("; transitions " + ", ".join(f"{a}→{b}" for a, b, _ in e.edges) if e.edges else "; transitions not stated"))
            for txt, ev in e.invariants:
                bits.append(f"invariant ({ev}): {txt}")
        responsibility = (f"Owns the {ents_txt} aggregate: creation, changes and state transitions of these records, and the rules that hold across them. "
                          + ("; ".join(bits) + ". " if bits else "") + f"Read from {', '.join(list(dict.fromkeys(r for e in group for r in e.evidence))[:8])}.")
        comp = Component(f"C-{n}", name, responsibility, "module", layout.module.format(key=key, Key="".join(p.capitalize() for p in key.split("_"))),
                         requires=[iid["store"]] if "store" in iid else [], satisfies=[], tags=["layer:1", f"archetype:{key}", "aggregate"])
        ops: list[Operation] = []
        seen_ops: set[str] = set()
        for e in group:
            # states reached only through a prose sequence ("placed, then confirmed") get the verb that leads to them
            state_to_verb = {st: v for v, st in DM.STATE_VERBS.items()}
            extra = [(state_to_verb[b], b, ev) for a, b, ev in e.edges if b in state_to_verb and not any(t[1] == b for t in e.transitions)]
            for verb, state, ev in e.transitions + list(dict.fromkeys(extra)):
                if "→" in verb:
                    continue
                opname = f"{verb}_{e.name}"
                if opname not in seen_ops:
                    seen_ops.add(opname)
                    froms = sorted({a for a, b, _ in e.edges if b == state})
                    pre = ("status in (" + ", ".join(froms) + ")") if froms else "allowed source states not stated in the text"
                    ops.append(Operation(opname, [Param(f"{e.name}_id", "ref")], f"{e.display} (status = {state})",
                                         ["NotFound", "InvalidTransition (source status not allowed)"], pre=pre, post=f"status = {state}", description=f"from {ev}"))
            if not any(o.name.startswith(("create_", "register_", "submit_")) and o.name.endswith(e.name) for o in ops):
                opname = f"create_{e.name}"
                if opname not in seen_ops:
                    seen_ops.add(opname)
                    ops.append(Operation(opname, [Param(e.name, e.display)], e.display + " (id assigned)", ["ValidationError listing every invalid field"],
                                         post="; ".join(t for t, _ in e.invariants) or "record is durable before return", description="creation of the aggregate root" if e is top else "creation of a member of the aggregate"))
            opname = f"get_{e.name}"
            if opname not in seen_ops:
                seen_ops.add(opname)
                ops.append(Operation(opname, [Param(f"{e.name}_id", "ref")], f"{e.display} | None"))
        iface = Interface(f"I-{n}", f"{name} interface", comp.id, "module", ops, "draft",
                          f"Provided by {name}. Operations are the state transitions and creations the requirements name; add queries as the surfaces need them.")
        d.components.append(comp)
        d.interfaces.append(iface)
        cid[key], iid[key] = comp.id, iface.id
        requires[key] = ["store"] if "store" in cid else []
        for e in group:
            agg_of_entity[e.name] = key
        # the surfaces and the core use the aggregate; the aggregate is the only writer of its records
        for sk in list(surfaces) + (["core"] if "core" in cid else []):
            if sk in cid:
                sc = d.component(cid[sk])
                if sc is not None and iface.id not in sc.requires:
                    sc.requires.append(iface.id)
                    requires.setdefault(sk, []).append(key)
        # requirements whose evidence built the aggregate (the entity is created, changed, moved between states or constrained
        # there) are satisfied by it — not every sentence that happens to contain the word
        evid = {r for e in group for r in e.strong}
        for u in an.requirements:
            if u.sentence.assumed or u.kind == "constraint":
                continue
            if u.id in evid and u.id not in comp.satisfies:
                comp.satisfies.append(u.id)
        if not comp.satisfies:
            comp.satisfies = [r for e in group for r in e.evidence][:1]
        trace[comp.id] = {"sentences": sorted({u.sentence.index for u in functional_units if u.id in comp.satisfies}), "rules": [f"aggregate:{top.name}"]}
        trace[iface.id] = {"sentences": [], "rules": [f"aggregate:{top.name}"]}

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
            words = {DM.singular(w) for w in u.sentence.words}
            agg = next((agg_of_entity[e] for e in agg_of_entity if e in words and u.id in next(x.strong for x in dents if x.name == e)), None)
            if agg and agg in cid:
                p = Placement(u.id, [cid[agg]], "aggregate", f"the sentence speaks of {[e for e in agg_of_entity if e in words][0]}, owned by {d.component(cid[agg]).name}")
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
        d.entities.append(Entity("E-1", _singular(top).capitalize() or "Record", cid["store"],
                                 [FieldDef(n, t, c) for n, t, c in tmpl.fields], f"Generic record named after the most frequent noun ('{top}'); refine the fields."))
        trace["E-1"] = {"sentences": [], "rules": ["fallback:top-noun"]}
    if dents and "record" in ekeys:
        ekeys.remove("record")            # the text names its own records; the generic one is noise
    for n, e in enumerate(ekeys, 1):
        tmpl = K.ENTITIES[e]
        owner = cid[ENTITY_OWNER.get(e, "store")]
        d.entities.append(Entity(f"E-{n}", tmpl.name, owner, [FieldDef(nm, tp, c) for nm, tp, c in tmpl.fields], tmpl.description))
        trace[f"E-{n}"] = {"sentences": [], "rules": [f"entity:{e}"]}
    # domain entities read from the text: typed fields, relations, state machines, invariants (engine/domain.py)
    if "store" in cid:
        existing = {e.name.lower() for e in d.entities}
        n = len(d.entities)
        for de in dents:
            if de.name in existing or de.display.lower() in existing:
                # a catalogue entity of the same name: enrich it instead of duplicating
                tgt = next(e for e in d.entities if e.name.lower() in (de.name, de.display.lower()))
                have = {f.name for f in tgt.fields}
                for fn, ft, ev in de.fields:
                    if fn not in have:
                        tgt.fields.append(FieldDef(fn, ft, f"from {ev}"))
                if de.states and "status" not in have:
                    src = list(dict.fromkeys([r for _, _, r in de.edges] + [r for _, _, r in de.transitions])) or de.evidence[:3]
                    tgt.fields.append(FieldDef("status", "enum(" + ", ".join(de.states) + ")", "states read from " + ", ".join(src)))
                for txt, ev in de.invariants:
                    tgt.description = (tgt.description.rstrip(".") + f". Invariant ({ev}): {txt}.").lstrip(". ")
                continue
            n += 1
            fds = [FieldDef("id", "uuid", "primary key")]
            fds += [FieldDef(fn, ft, f"from {ev}") for fn, ft, ev in de.fields]
            for kind, target, ev in de.relations:
                if kind == "belongs_to":
                    fds.append(FieldDef(f"{target}_id", "ref", f"belongs to one {target} ({ev})"))
            if de.states:
                src = list(dict.fromkeys([r for _, _, r in de.edges] + [r for _, _, r in de.transitions])) or de.evidence[:3]
                trans = ("; transitions: " + ", ".join(f"{a}→{b}" for a, b, _ in de.edges)) if de.edges else "; transitions not stated in the text"
                fds.append(FieldDef("status", "enum(" + ", ".join(de.states) + ")", "states read from " + ", ".join(src) + trans))
            fds.append(FieldDef("created_at", "timestamp", ""))
            desc = f"Domain entity read from {', '.join(de.evidence[:6])}."
            if not de.fields:
                desc += " No fields are stated in the text beyond its name; add them."
            for txt, ev in de.invariants:
                desc += f" Invariant ({ev}): {txt}."
            has_many = [t for k, t, _ in de.relations if k == "has_many"]
            if has_many:
                desc += " Has many: " + ", ".join(has_many) + "."
            d.entities.append(Entity(f"E-{n}", de.display, cid.get(agg_of_entity.get(de.name, ""), cid["store"]), fds, desc))
            trace[f"E-{n}"] = {"sentences": [], "rules": ["entity:from-text"] + [f"entity:{ev}" for ev in de.evidence[:6]]}

    # synthesised contracts: give parameters the entity type when the name matches an entity
    ent_by_name = {e.name.lower(): e.name for e in d.entities}
    for c in d.components:
        if "synthesised" not in c.tags:
            continue
        for i in d.provided_by(c.id):
            for o in i.operations:
                for p in o.inputs:
                    if p.type == "…":
                        base = _singular(p.name)
                        if base in ent_by_name:
                            p.type = f"list[{ent_by_name[base]}]" if p.name.endswith("s") else ent_by_name[base]
                if o.output == "…" and o.inputs and o.inputs[0].type != "…":
                    o.output = o.inputs[0].type + " (validated)" if "valid" in o.name else o.output

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
            # a reply (the reverse of an earlier step in the same flow) is a response, not a call
            is_reply = any(x == b and y == a for x, y, _ in ft.steps[:len(steps) - 1])
            if iid[b] not in comp.requires and a != b and not is_reply:
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
        if dk not in dkeys and ("*" in dp.trigger or any(t in an.constraints for t in dp.trigger)):
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
        best, ranked, rationale, consequences = decide(dp, an.qualities, an.constraints, forced, _peak_rate(an), an.stated_constraints)
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
        if key in _INFRA:
            fam = "infra"
        elif "aggregate" in c.tags:
            fam = "aggregate:" + key           # one package per domain aggregate
        elif "synthesised" in c.tags:
            fam = "synthesised:" + key
        else:
            fam = next((p.id for p in K.PATTERNS if p.id in an.patterns and key in p.archetypes), "infra")
        family_of[c.id] = fam
    groups: list[list[str]] = []
    for layer in layers:
        ids = [c for c in layer if d.component(c).kind != "external"]
        by_family: "OrderedDict[str, list[str]]" = OrderedDict()
        for c in sorted(ids, key=lambda c: (family_of[c], int(c.split("-")[1]))):
            by_family.setdefault(family_of[c], []).append(c)
        # infrastructure of one layer may be batched; domain families stay separate
        for fam, members in by_family.items():
            for i in range(0, len(members), 3):
                groups.append(members[i:i + 3])
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
                              "test", layout.test_command.format(test=" ".join(tests), key=keys[0], Key="".join(p.capitalize() for p in keys[0].split("_")))))
        for r in satisfies:
            req = d.requirement(r)
            if req is not None and req.kind == "nonfunctional" and req.metric and req.metric.target != "review":
                unit = next((u for u in an.requirements if u.id == r), None)
                mq = _metric_quality(unit) if unit else []
                if req.metric.name.startswith(("value", "number of", "factor", "size", "time")) and not mq:
                    continue          # a bare number is not an acceptance check
                if req.rationale.startswith("assumed") and not (mq and mq[0] in ("performance", "availability") and ("latency" in req.metric.name or re.search(r"\b9\d(?:\.\d+)? ?%", req.metric.target))):
                    continue          # engine assumptions become acceptance checks only for the latency and availability targets
                acc_n += 1
                tmpl = next((t.acceptance for t in K.TACTICS if mq and t.quality == mq[0] and t.acceptance), "")
                acc.append(Acceptance(f"A-{acc_n}", f"{r}: {metric_text(req.metric)}"
                                      + (f" — {tmpl}" if tmpl else ""), "metric", metric=r))
        title = " + ".join(c.name for c in comps)
        goal = "Implement " + "; ".join(f"{c.name}: {c.responsibility.rstrip('.')}" for c in comps) + "."
        d.work_packages.append(WorkPackage(wp_id, title, goal, ids, [i.id for c in comps for i in d.provided_by(c.id)],
                                           deps, satisfies, files, _size_of(comps, d, satisfies), acc,
                                           notes=f"family: {family_of[ids[0]]}"))
        trace[wp_id] = {"sentences": [], "rules": [f"package:layer{[i for i, L in enumerate(layers) if ids[0] in L][0]}:{family_of[ids[0]]}"]}
    return Synthesis(d, trace, [cid[k] for k in generic_keys if k in cid], log, placements, close_calls)
