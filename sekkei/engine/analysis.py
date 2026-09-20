"""Requirements analysis: sentences -> requirement units, qualities, constraints, patterns.

The output (``Analysis``) is everything synthesis needs and everything the review must
be able to explain: which sentence produced which requirement, which signals activated
which pattern and quality, and which sentences nothing recognised.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import catalog as K
from . import ja
from . import structure as ST
from . import text as T


@dataclass
class ReqUnit:
    id: str
    sentence: T.Sentence
    kind: str                      # functional | nonfunctional | constraint
    priority: str                  # must | should | could
    patterns: list[str] = field(default_factory=list)
    qualities: list[str] = field(default_factory=list)
    metric: tuple[str, str, str] | None = None   # name, target, unit
    recognised: bool = True


DEFAULT_METRICS = {
    "durability": ("records lost across a process crash", "= 0", "records"),
    "consistency": ("lost or duplicate updates under concurrent writes to one record", "= 0", "updates"),
    "isolation": ("p95 latency of healthy targets while one target stalls", "within the stated latency target", ""),
    "security": ("unauthenticated or cross-tenant requests accepted", "= 0", "requests"),
    "operability": ("required metrics exposed", "= all listed", ""),
    "availability": ("monthly availability", "target to be agreed", "%"),
    "scalability": ("instances that can serve concurrently", ">= 2", "instances"),
    "compliance": ("retention/deletion rules exercised", "= all", ""),
}


@dataclass
class Analysis:
    title: str
    summary: str
    non_goals: list[str]
    sentences: list[T.Sentence]
    requirements: list[ReqUnit]
    patterns: dict[str, int]               # pattern id -> signal weight
    qualities: dict[str, float]            # quality -> weight (0..1)
    constraints: set[str]
    languages: list[str]
    team_size: int | None
    actors: list[str]
    unrecognised: list[ReqUnit]
    assumptions: list[str]
    normalisation: ja.Normalised | None = None   # set when the input was Japanese
    structure: ST.Canonical | None = None        # what the structure pass folded (tables, stories, labels, TODOs, deadline)
    dropped: list[tuple[str, str]] = field(default_factory=list)   # (sentence, why) read but not taken as a requirement
    stated_constraints: set[str] = field(default_factory=set)      # constraint tokens from the author's text only (no assumed bullets)


_TEAM_RE = re.compile(r"team of (\d+)(?=\s*(?:[.,;)(]|$|engineers?\b|developers?\b|devs?\b|people\b|persons?\b|for\b|plus\b|\+|\(|and\b))|(\d+)[- ]person team|\(?(\d+)\)? (?:platform |backend |frontend |data |software )?(?:engineers|developers)\b|team (?:is|=|:)\s*(\d+)\b", re.I)
_TEAM_NAMES_RE = re.compile(r"\bteam (?:is|=|:)\s*(?:me|myself|I)(?:\s*(?:\+|,|and|&)\s*[A-Z][a-z]+)+", re.I)


def _score(patterns_signals: list[tuple[str, int]], text: str) -> int:
    return sum(w for rx, w in patterns_signals if re.search(rx, text, re.I))


def _match_patterns(low: str) -> dict[str, int]:
    out = {}
    for p in K.PATTERNS:
        s = _score(p.signals, low)
        if s >= 2:
            out[p.id] = s
    return out


def _sentence_patterns(sentence: T.Sentence, active: dict[str, int]) -> list[str]:
    """Active patterns whose signals score at least 2 inside this sentence (weight-1 signals alone are too generic)."""
    scores = {p.id: _score(p.signals, sentence.lower) for p in K.PATTERNS if p.id in active}
    return [pid for pid, sc in scores.items() if sc >= 2]


def _sentence_qualities(sentence: T.Sentence) -> list[str]:
    return [t.quality for t in K.TACTICS if _score(t.signals, sentence.lower) >= 1]


def _kind(sentence: T.Sentence, qualities: list[str]) -> str:
    if sentence.section in ("functional", "nonfunctional", "constraint"):
        if sentence.section == "nonfunctional" and not qualities and not sentence.quantities:
            return "functional"
        return sentence.section
    low = sentence.lower
    if _TEAM_RE.search(sentence.text) and len(sentence.words) <= 6:
        return "constraint"       # "Team of 3." under any heading is a constraint, not a quality target
    if re.search(r"\b(python|typescript|golang|rust|java|postgres|redis|team of|must run|available|region|containers?)\b", low) and not sentence.verbs:
        return "constraint"
    if qualities and (sentence.quantities or not sentence.verbs):
        return "nonfunctional"
    return "functional"


def _metric(sentence: T.Sentence) -> tuple[str, str, str] | None:
    """Pick the quantity that best represents a non-functional target."""
    qs = [q for q in sentence.quantities if q.kind != "code"]
    if not qs:
        return None
    for q in qs:  # "under 5 s" / "p95 ... 300 ms": a bounded *short* duration is a latency target; "up to 3 days" is not
        short = q.unit.lower() in ("s", "sec", "secs", "second", "seconds", "min", "mins", "minute", "minutes", "ms")
        bounding = q.comparator.lower() in ("under", "below", "less than", "at most", "within", "<", "<=", "no more than") or q.comparator.lower().startswith("not ")
        if q.kind == "duration" and short and (bounding or q.percentile or any(o.percentile for o in qs)):
            q.kind = "latency"
    ranked = sorted(qs, key=lambda q: ({"latency": 0, "rate": 1, "percent": 2, "duration": 3, "size": 4, "count": 5, "factor": 6, "number": 7}[q.kind], -bool(q.comparator)))
    q = ranked[0]
    name_bits = []
    if q.percentile:
        name_bits.append(q.percentile)
    name_bits.append({"latency": "latency", "rate": "sustained rate", "percent": "ratio", "duration": "time",
                      "size": "size", "count": f"number of {q.noun}", "factor": "factor", "number": "value"}[q.kind])
    others = [o for o in qs if o is not q]
    if others:
        name_bits.append("at " + ", ".join(o.raw for o in others[:3]))
    return (" ".join(name_bits), q.target(), q.unit if q.kind != "count" else q.noun)


def _looks_like_requirement(s: T.Sentence) -> bool:
    """Prose that reads as a use case or a target: 'Traders submit orders …', 'Fills are booked within 500 ms'."""
    if any(q.comparator or q.percentile for q in s.quantities if q.kind in ("latency", "duration", "rate", "percent", "count", "size")):
        return True
    if any(q.kind in ("duration", "rate", "percent", "size", "count") for q in s.quantities) and \
            re.search(r"\bretain|\bretention|\bkept\b|\bkeep\b|\bmax\b|\blimit|\bbudget|\bsla\b|\bpeak|\bper (?:day|hour|second)|\bexpir|\bwindow\b|\bat least\b", s.lower):
        return True
    # "the matcher selects candidate tickets", "Tickets live in Redis", "Formed matches are persisted to PostgreSQL",
    # "Returns 202 with a ticket id": a component or a thing as subject with a verb, a stated path/status, a technology
    low = s.lower
    lead = re.sub(r"^[^,]{0,60},\s*", "", low)          # drop a leading adverbial ("Every 1 second per shard, …")
    m = re.match(r"^(?:the|a|an|each|every|all|formed|new|existing)?\s*((?:[a-z-]+\s+)?[a-z-]+)\s+(?:[a-z]+s|must|shall|will|is|are|live|lives)\b", lead)
    if m and s.verbs and not re.match(r"^(?:the|a|an)\s+(?:same|following|first|last|next|previous|other|only|full|whole|entire|rest)\b", lead):
        head = m.group(1).split()[-1]
        if (not T.verb_of(head) or head in ("matcher", "extractor", "scheduler", "worker", "orchestrator", "bootloader", "gateway", "bridge", "lock",
                                              "console", "engine", "service", "platform", "system", "pipeline", "job", "ticket", "tickets", "match", "matches")) \
                and head not in ("it", "this", "that", "there", "here", "which", "what", "who"):
            return True
    if re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/|\breturns? (?:a )?`?\d{3}\b|\b(?:persisted|stored|written|kept|held) (?:to|in) (?:postgres|redis|kafka|s3|the (?:database|store|queue|topic))", s.text):
        return True
    if s.actors and s.verbs:
        words = s.words
        first_verb = next((i for i, w in enumerate(words) if T.verb_of(w) and not (i > 0 and words[i - 1] in T._DETERMINERS)), len(words))
        actor_toks = {t.rstrip("s") for a in s.actors for t in a.split()}
        for a in sorted(s.actors, key=len, reverse=True):
            toks = a.split()
            for i in range(min(first_verb, len(words))):
                if [w.rstrip("s") for w in words[i: i + len(toks)]] == [t.rstrip("s") for t in toks]:
                    return not any(T.verb_of(w) for w in words[:i] if w.rstrip("s") not in actor_toks)
    return False


def _summary(sentences: list[T.Sentence]) -> str:
    prose = [s for s in sentences if not s.is_bullet and not s.modality and not s.section]
    return prose[0].text if prose else (sentences[0].text if sentences else "")


def analyse(text: str, hints: dict[str, list[str]] | None = None, structure: ST.Canonical | None = None) -> Analysis:
    """``hints`` maps the text of an engine-assumed bullet to the patterns it legitimately activates;
    assumed bullets never activate patterns by their wording (they are policy, not capability).
    ``structure`` is the result of the structure pass when the caller already ran it (design() does)."""
    hints = hints or {}
    if structure is None:
        structure = ST.canonicalise(text)
        text = structure.text
    tentative = set(structure.tentative)
    norm = None
    if ja.is_japanese(text, document=True):
        norm = ja.normalise(text)
        text = norm.text
    sentences = T.segment(text)
    low = " ".join(s.text for s in sentences if s.section != "nongoal").lower()
    active = _match_patterns(" ".join(s.text for s in sentences if s.section != "nongoal" and not s.assumed).lower())
    for pats in hints.values():
        for p in pats:
            active[p] = max(active.get(p, 0), 2)
    # qualities: weight from signal strength across the document, normalised
    qw: dict[str, float] = {}
    for t in K.TACTICS:
        s = _score(t.signals, low)
        if s >= 2:
            qw[t.quality] = s
    top = max(qw.values(), default=1)
    qualities = {q: round(min(1.0, 0.4 + 0.6 * w / top), 2) for q, w in qw.items()}
    h1 = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("# ")), "")
    low_env = low + " " + h1.lower() + " " + " ".join(s.text for s in sentences if s.section == "nongoal").lower()
    constraints = {tok for rx, tok in K.CONSTRAINT_TOKENS if re.search(rx, low_env)}
    low_stated = (h1 + " " + " ".join(s.text for s in sentences if not s.assumed)).lower()
    stated_constraints = {tok for rx, tok in K.CONSTRAINT_TOKENS if re.search(rx, low_stated)}
    # a CLI is the system only when no web/API surface is described; an admin CLI next to a web service is a side tool
    cli_dominant = "cli_tool" in active and not any(p in active for p in ("crud_api", "admin_api", "event_ingest", "realtime", "mobile_offline", "file_storage", "search", "workflow", "payments", "notification"))
    if cli_dominant:
        stated_constraints.add("cli_tool")
    else:
        stated_constraints.discard("cli_tool")
        constraints.discard("cli_tool")
    # derived tokens: a stated durability/consistency need or an availability target rules out volatile options
    if "durability" in qualities or "consistency" in qualities or re.search(r"\b99\.\d+\s*%", low) or re.search(r"never (?:be )?lost|must never|double[- ]pay|exactly once|at[- ]least[- ]once", low):
        constraints.add("durable_required")
    languages = [tok for rx, tok in K.LANGUAGE_TOKENS if re.search(rx, low)]
    if len(languages) > 1:
        # "Tokyo (server): Go. Berlin (tools): TypeScript" — the server's language leads the conventions
        server = [tok for rx, tok in K.LANGUAGE_TOKENS if tok in languages and re.search(r"(?:server|backend|service|api)[^.。]{0,40}" + rx + r"|" + rx + r"[^.。]{0,40}(?:server|backend|services?|api)\b", low)]
        if server:
            languages = server + [t for t in languages if t not in server]
    if "go" not in languages and re.search(r"(?<![A-Za-z])Go(?=[,./)]|\s+(?:\d|backend|service|services|binary|module|\+|and\b|for (?:services|the backend|apis|microservices)\b|on\b|$))", text, re.M) \
            and not re.search(r"\bGo (?:to|through|live|back|ahead|down|up|into|out|over|with|the|a|an)\b", text) \
            and not re.search(r"\bGo for (?:it|the|a|an)\b", text) or re.search(r"\bGo for (?:services|the backend|apis|microservices|the api|everything)\b", text):
        languages.append("go")
    ms = [x for x in _TEAM_RE.finditer(text) if not text[max(0, x.start() - 1):x.start()] == "("]   # "(team of 45)" describes a user segment
    m = next((x for x in ms if text[x.end():x.end() + 1] == "."), ms[0] if ms else None)   # the structure pass writes "Team of N."
    team = int(next(g for g in m.groups() if g)) if m else None
    if team is None:
        mn = _TEAM_NAMES_RE.search(text)
        if mn:
            team = 1 + len(re.findall(r"(?:\+|,|\band\b|&)\s*[A-Z][a-z]+", mn.group(0)))
    team_bad = None
    if team is not None and not (1 <= team <= 500):
        team_bad, team = team, None
    if team and team <= 4:
        qualities["simplicity"] = max(qualities.get("simplicity", 0), 0.8)
    actors = sorted({a for s in sentences for a in s.actors})

    reqs: list[ReqUnit] = []
    unrec: list[ReqUnit] = []
    non_goals = [s.text for s in sentences if s.section == "nongoal"]
    candidates = [s for s in sentences if s.section != "nongoal" and not s.assumed]
    structured = any(s.is_bullet or s.section in ("functional", "nonfunctional", "constraint") for s in candidates)
    # a one-liner or a paragraph with no bullets and no modal words: every sentence is a requirement
    prose_only = not structured and bool(candidates)
    n = 0
    dropped: list[tuple[str, str]] = []
    for s in sentences:
        if s.section == "nongoal":
            continue
        strong_modal = bool(s.modality) and not (s.intro and s.modality == "should")   # "needs" in an introduction is scene-setting
        is_req = s.is_bullet or strong_modal or s.section in ("functional", "nonfunctional", "constraint") or (prose_only and not s.assumed) or s.assumed
        if s.section == "background" and not s.assumed and not (s.modality in ("must",) and not s.is_bullet):
            is_req = False          # a timeline entry, a root cause, "what went well": read, listed, not designed
        if not is_req and s.section != "background" and not s.intro:
            # prose in a structured document: a use case (actor as subject + verb) or a stated target (bounded number) is a requirement
            if len(s.words) >= 5 and _looks_like_requirement(s):
                is_req = True
        if is_req and not s.is_bullet and not s.assumed and len(s.words) < 5 and not s.quantities:
            is_req = False          # "Today we agree scope." — too short to be a requirement
        if not is_req:
            why = "background/summary prose" if s.section == "background" else "introduction before the first heading" if s.intro else "prose without an actor-verb shape, a number target or a modal word"
            if len(s.words) >= 3:
                dropped.append((s.text, why))
            continue
        sq = _sentence_qualities(s)
        kind = _kind(s, sq)
        if s.prohibition and kind == "functional":
            kind = "nonfunctional"          # "shall not delete alarms": a rule to enforce and test, not a use case
        if kind == "constraint" and s.section != "constraint" and (s.verbs and s.modality != "must"):
            kind = "functional"
        prio = s.modality or ("should" if kind == "nonfunctional" and not any(q.comparator or q.kind in ("latency", "percent", "rate") for q in s.quantities) else "must")
        if kind == "constraint":
            prio = "must"
        if s.text in tentative or (norm and norm.sources.get(s.text, "") in tentative):
            prio = "could"       # "maybe", "TBD", "later maybe", a trailing question mark
        n += 1
        pats = hints.get(s.text, []) if s.assumed else _sentence_patterns(s, active)
        # a latency/percentage target keeps its metric even when the author filed the sentence under "functional"
        has_target = any(q.kind in ("latency", "percent") and (q.comparator or q.percentile) for q in s.quantities)
        unit = ReqUnit(f"R-{n}", s, kind, prio, pats, sq, _metric(s) if kind == "nonfunctional" or (kind == "functional" and has_target) else None)
        if kind == "nonfunctional" and unit.metric is None:
            # a quality statement without a number: a default metric for the quality, else a review-visible target
            order = (["compliance"] if "compliance_data" in pats else []) + sq
            unit.metric = next((DEFAULT_METRICS[q] for q in order if q in DEFAULT_METRICS), ("target to be agreed", "review", ""))
            if s.prohibition:
                unit.metric = (f"occurrences of the forbidden action ({', '.join(s.negated_verbs[:2])})", "= 0", "occurrences")
        if kind == "functional" and not unit.patterns:
            unit.recognised = False
            unrec.append(unit)
        reqs.append(unit)

    assumptions: list[str] = []
    if team_bad is not None:
        assumptions.append(f"Stated team size {team_bad} is not usable (must be 1–500); the effort estimate assumes 2.")
    if not languages:
        assumptions.append(f"No implementation language stated; assumed {K.DEFAULT_LANGUAGE}.")
    if "postgres" not in constraints and "mysql" not in constraints and "sqlite" not in constraints:
        assumptions.append("No database stated; the store decision is scored without a database constraint.")
    if not any(u.kind == "nonfunctional" for u in reqs):
        assumptions.append("No non-functional requirements found; performance and availability targets are unset.")
    if norm and norm.untranslated:
        assumptions.append("Japanese words the glossary does not know were dropped: " + ", ".join(f"「{w}」" for w in sorted(set(norm.untranslated))) + ".")
    if prose_only:
        assumptions.append("No bullets, headings or modal words: every sentence of the text was taken as a requirement.")
    if dropped:
        assumptions.append(f"{len(dropped)} sentence(s) were read but not taken as requirements (listed in the notes §6b); if one of them is a requirement, make it a bullet.")
    for n in structure.notes:
        if n.startswith(("table with", "user story", "ticket heading", "DECIDED", "inline 'out of scope", "team size", "heading without")):
            assumptions.append("Structure: " + n + ".")
    an = Analysis(T.title_of(text), _summary(sentences), non_goals, sentences, reqs, active, qualities, constraints,
                  languages, team, actors, unrec, assumptions, norm, structure)
    an.dropped = dropped
    an.stated_constraints = stated_constraints | {c for c in constraints if c == "durable_required"}
    return an
