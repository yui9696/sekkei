"""The design engine: requirements text -> complete, lint-clean design + the architect's notes. No model involved.

    from sekkei.engine import design
    result = design(open("requirements.md").read())
    result.design        # sekkei.model.Design, lint-clean or result.ok is False
    result.notes         # questions, capacity, effort, threat model, self-review (to_markdown())
    result.trace         # element id -> sentences and catalogue rules that produced it
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import rules as R
from ..model import Decision, Design, Option
from . import ja, structure
from .analysis import Analysis, analyse
from .answers import Answer, augment
from .answers import answers as _answers
from .evaluate import Review, review
from .gaps import Question, questions
from .owners import Placement
from .repair import repair
from .report import REQUIREMENTS_TEMPLATE, Notes, notes
from .synthesis import synthesise
from .threats import inject_risks


@dataclass
class Overrides:
    """Decisions a human made in the interview: requirement statement -> owner component name/id;
    decision key or title -> option name (or prefix)."""
    owners: dict[str, str] = field(default_factory=dict)
    decisions: dict[str, str] = field(default_factory=dict)


@dataclass
class EngineResult:
    design: Design
    analysis: Analysis
    review: Review
    notes: Notes
    diagnostics: list[R.Diagnostic]
    trace: dict[str, dict[str, list]]
    log: list[str] = field(default_factory=list)
    answers: list[Answer] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)
    augmented_text: str = ""
    close_calls: list[tuple[str, str, str, list[tuple[str, float]]]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not R.has_errors(self.diagnostics)

    def trace_json(self) -> dict[str, Any]:
        return {
            "patterns": self.analysis.patterns,
            "qualities": self.analysis.qualities,
            "constraints": sorted(self.analysis.constraints),
            "languages": self.analysis.languages,
            "elements": self.trace,
            "sentences": [{"index": s.index, "text": s.text, "section": s.section, "modality": s.modality}
                          for s in self.analysis.sentences],
            "repairs": self.log,
        }


#: constraint tokens the author wrote that already decide a point (the answer must not override them)
_DECIDING_TOKENS = {"auth_scheme": {"idp", "no_account_auth", "email_auth", "game_client", "mtls"}, "store_tech": {"postgres", "mysql", "sqlite", "redis_primary", "no_database"}}
_ANSWER_DECISIONS = {
    "Q-auth": ("auth_scheme", {"OIDC": "OAuth2 / OIDC", "API keys": "API keys", "mTLS": "Mutual TLS", "none": "", "No account": "No account"}),
    "Q-store": ("store_tech", {"SQLite": "SQLite", "PostgreSQL": "PostgreSQL", "MySQL": "MySQL"}),
}


def _decision_of_answer(a: Answer) -> tuple[str, str]:
    """(decision key, option prefix) named by an engine answer, or ('', '')."""
    key, table = _ANSWER_DECISIONS.get(a.question_id, ("", {}))
    if not key:
        return "", ""
    chosen = a.options[0] if a.options else ""
    for k, prefix in table.items():
        if k.lower() in chosen.lower() and prefix:
            return key, prefix
    return "", ""


def _assumed_decisions(d: Design, ans: list[Answer]) -> None:
    """One proposed decision per engine answer, so a human can override it in the design."""
    n = len(d.decisions)
    key_to_cid = {t.split(":", 1)[1]: c.id for c in d.components for t in c.tags if t.startswith("archetype:")}
    for a in ans:
        n += 1
        affects = [key_to_cid[k] for k in a.affects if k in key_to_cid]
        d.decisions.append(Decision(
            f"D-{n}", f"Assumed answer: {a.topic} ({a.question_id})",
            f"The requirements do not say. Question: {a.question_id}. " + ("Evidence: " + a.evidence + "." if a.evidence else "No evidence in the text; engine default."),
            [Option(o, [], []) for o in a.options], a.options[0], a.rationale, "If the real answer differs: " + a.if_wrong, affects, "proposed"))


def _alternatives(d: Design, can: structure.Canonical) -> None:
    """'Alternatives considered' in the input become rejected decisions, so the record survives the rewrite."""
    n = len(d.decisions)
    for alt in can.alternatives:
        n += 1
        head = alt.split(":")[0].strip()[:60]
        d.decisions.append(Decision(f"D-{n}", f"Alternative considered: {head}", alt, [Option(head, [], ["rejected in the requirements text"])], "",
                                    "Rejected in the requirements text: " + alt, "The design does not include it.", [], "rejected"))


def design(text: str, assume: bool = True, overrides: Overrides | None = None) -> EngineResult:
    """Design from a requirements text. With ``assume`` the engine answers its own open questions first;
    ``overrides`` carries owners and options a human chose in the interview."""
    overrides = overrides or Overrides()
    # document structure first (tables, numbered headings, stories, labels), then the language is
    # decided once, on the original text: the augmented text (original + English assumed bullets)
    # may fall under the Japanese-detection threshold and must not be re-read raw
    can = structure.canonicalise(text)
    text = can.text
    norm = ja.normalise(text) if ja.is_japanese(text, document=True) else None
    if norm:
        text = norm.text
    an = analyse(text, structure=can)
    an.normalisation = norm
    ans: list[Answer] = []
    full = text
    if not an.requirements:
        # nothing to design: refuse rather than produce a design made only of assumptions
        empty = Design(name=an.title and an.title.lower().replace(" ", "-") or "empty")
        diags = [R.Diagnostic("S008", "error", "no requirements in the input: write at least one bullet or a sentence with must/should/may", "$",
                              "See `sekkei template` for the expected shape.")]
        rv = Review(assumptions=["No requirements found; nothing was designed."])
        return EngineResult(empty, an, rv, notes(empty, an, rv), diags, {}, [], [], [], text)
    if assume:
        for _ in range(3):  # answers can raise new questions (e.g. records -> retention); converge
            new = [a for a in _answers(questions(an), an) if a.question_id not in {x.question_id for x in ans}]
            if not new:
                break
            ans += new
            full = augment(text, ans)
            an = analyse(full, hints={b: a.patterns for a in ans for _, b in a.bullets}, structure=can)
            an.normalisation = norm
    # an assumed answer that names an option of a decision point *is* that decision: never assume OIDC and then choose API keys
    forced = dict(overrides.decisions)
    stated = an.stated_constraints
    for a in ans:
        key, opt = _decision_of_answer(a)
        if key and key not in forced and not any(k.lower() == key for k in forced) and not (stated & _DECIDING_TOKENS.get(key, set())):
            forced[key] = opt
    syn = synthesise(an, forced, overrides.owners)
    _assumed_decisions(syn.design, ans)
    for x in syn.design.decisions:
        syn.trace.setdefault(x.id, {"sentences": [], "rules": ["assumed-answer"]})
    added = inject_risks(syn.design)
    for k in syn.design.risks[len(syn.design.risks) - added:]:
        syn.trace[k.id] = {"sentences": [], "rules": ["threat:" + k.description.split("]")[0].strip("[")]}
    d, diags, log = repair(syn.design)
    _alternatives(d, can)
    rv = review(d, an, syn.generic)
    nt = notes(d, an, rv, ans, syn.placements)
    return EngineResult(d, an, rv, nt, diags, syn.trace, syn.log + log, ans, syn.placements, full, syn.close_calls)


def ask(text: str) -> list[Question]:
    """Only the questions an architect would ask about this text."""
    can = structure.canonicalise(text)
    return questions(analyse(can.text, structure=can))


__all__ = ["EngineResult", "Overrides", "REQUIREMENTS_TEMPLATE", "ask", "design", "analyse", "synthesise", "review", "repair"]
