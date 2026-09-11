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


def design(text: str, assume: bool = True, overrides: Overrides | None = None) -> EngineResult:
    """Design from a requirements text. With ``assume`` the engine answers its own open questions first;
    ``overrides`` carries owners and options a human chose in the interview."""
    overrides = overrides or Overrides()
    an = analyse(text)
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
            an = analyse(full, hints={b: a.patterns for a in ans for _, b in a.bullets})
    syn = synthesise(an, overrides.decisions, overrides.owners)
    _assumed_decisions(syn.design, ans)
    for x in syn.design.decisions:
        syn.trace.setdefault(x.id, {"sentences": [], "rules": ["assumed-answer"]})
    added = inject_risks(syn.design)
    for k in syn.design.risks[len(syn.design.risks) - added:]:
        syn.trace[k.id] = {"sentences": [], "rules": ["threat:" + k.description.split("]")[0].strip("[")]}
    d, diags, log = repair(syn.design)
    rv = review(d, an, syn.generic)
    nt = notes(d, an, rv, ans, syn.placements)
    return EngineResult(d, an, rv, nt, diags, syn.trace, syn.log + log, ans, syn.placements, full, syn.close_calls)


def ask(text: str) -> list[Question]:
    """Only the questions an architect would ask about this text."""
    return questions(analyse(text))


__all__ = ["EngineResult", "Overrides", "REQUIREMENTS_TEMPLATE", "ask", "design", "analyse", "synthesise", "review", "repair"]
