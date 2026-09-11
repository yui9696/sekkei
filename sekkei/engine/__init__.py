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
from ..model import Design
from .analysis import Analysis, analyse
from .evaluate import Review, review
from .gaps import Question, questions
from .repair import repair
from .report import REQUIREMENTS_TEMPLATE, Notes, notes
from .synthesis import synthesise
from .threats import inject_risks


@dataclass
class EngineResult:
    design: Design
    analysis: Analysis
    review: Review
    notes: Notes
    diagnostics: list[R.Diagnostic]
    trace: dict[str, dict[str, list]]
    log: list[str] = field(default_factory=list)

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


def design(text: str) -> EngineResult:
    an = analyse(text)
    syn = synthesise(an)
    added = inject_risks(syn.design)
    for k in syn.design.risks[len(syn.design.risks) - added:]:
        syn.trace[k.id] = {"sentences": [], "rules": ["threat:" + k.description.split("]")[0].strip("[")]}
    d, diags, log = repair(syn.design)
    rv = review(d, an, syn.generic)
    return EngineResult(d, an, rv, notes(d, an, rv), diags, syn.trace, syn.log + log)


def ask(text: str) -> list[Question]:
    """Only the questions an architect would ask about this text."""
    return questions(analyse(text))


__all__ = ["EngineResult", "REQUIREMENTS_TEMPLATE", "ask", "design", "analyse", "synthesise", "review", "repair"]
