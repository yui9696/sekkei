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


_TEAM_RE = re.compile(r"team of (\d+)|(\d+)[- ]person team|(\d+) (?:engineers|developers)", re.I)


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
    for q in qs:  # "under 5 s" / "p95 ... 300 ms": a bounded duration is a latency target
        if q.kind == "duration" and (q.comparator or q.percentile or any(o.percentile for o in qs)):
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


def _summary(sentences: list[T.Sentence]) -> str:
    prose = [s for s in sentences if not s.is_bullet and not s.modality and not s.section]
    return prose[0].text if prose else (sentences[0].text if sentences else "")


def analyse(text: str, hints: dict[str, list[str]] | None = None) -> Analysis:
    """``hints`` maps the text of an engine-assumed bullet to the patterns it legitimately activates;
    assumed bullets never activate patterns by their wording (they are policy, not capability)."""
    hints = hints or {}
    norm = None
    if ja.is_japanese(text):
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
    constraints = {tok for rx, tok in K.CONSTRAINT_TOKENS if re.search(rx, low)}
    languages = [tok for rx, tok in K.LANGUAGE_TOKENS if re.search(rx, low)]
    m = _TEAM_RE.search(text)
    team = int(next(g for g in m.groups() if g)) if m else None
    if team and team <= 4:
        qualities["simplicity"] = max(qualities.get("simplicity", 0), 0.8)
    actors = sorted({a for s in sentences for a in s.actors})

    reqs: list[ReqUnit] = []
    unrec: list[ReqUnit] = []
    non_goals = [s.text for s in sentences if s.section == "nongoal"]
    n = 0
    for s in sentences:
        if s.section == "nongoal":
            continue
        is_req = s.is_bullet or bool(s.modality) or s.section in ("functional", "nonfunctional", "constraint")
        if not is_req:
            continue
        sq = _sentence_qualities(s)
        kind = _kind(s, sq)
        if kind == "constraint" and s.section != "constraint" and (s.verbs and s.modality != "must"):
            kind = "functional"
        prio = s.modality or ("should" if kind == "nonfunctional" and not any(q.comparator or q.kind in ("latency", "percent", "rate") for q in s.quantities) else "must")
        if kind == "constraint":
            prio = "must"
        n += 1
        pats = hints.get(s.text, []) if s.assumed else _sentence_patterns(s, active)
        # a latency/percentage target keeps its metric even when the author filed the sentence under "functional"
        has_target = any(q.kind in ("latency", "percent") and (q.comparator or q.percentile) for q in s.quantities)
        unit = ReqUnit(f"R-{n}", s, kind, prio, pats, sq, _metric(s) if kind == "nonfunctional" or (kind == "functional" and has_target) else None)
        if kind == "nonfunctional" and unit.metric is None:
            # a quality statement without a number: a default metric for the quality, else a review-visible target
            order = (["compliance"] if "compliance_data" in pats else []) + sq
            unit.metric = next((DEFAULT_METRICS[q] for q in order if q in DEFAULT_METRICS), ("target to be agreed", "review", ""))
        if kind == "functional" and not unit.patterns:
            unit.recognised = False
            unrec.append(unit)
        reqs.append(unit)

    assumptions: list[str] = []
    if not languages:
        assumptions.append(f"No implementation language stated; assumed {K.DEFAULT_LANGUAGE}.")
    if "postgres" not in constraints and "mysql" not in constraints and "sqlite" not in constraints:
        assumptions.append("No database stated; the store decision is scored without a database constraint.")
    if not any(u.kind == "nonfunctional" for u in reqs):
        assumptions.append("No non-functional requirements found; performance and availability targets are unset.")
    if norm and norm.untranslated:
        assumptions.append("Japanese words the glossary does not know were dropped: " + ", ".join(f"「{w}」" for w in sorted(set(norm.untranslated))) + ".")
    return Analysis(T.title_of(text), _summary(sentences), non_goals, sentences, reqs, active, qualities, constraints,
                    languages, team, actors, unrec, assumptions, norm)
