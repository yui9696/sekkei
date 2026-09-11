"""The design engine: requirements text -> complete, lint-clean design. No model involved.

    from sekkei.engine import design
    result = design(open("requirements.md").read())
    result.design        # sekkei.model.Design, lint-clean or result.ok is False
    result.review        # what the engine could not decide on its own
    result.trace         # element id -> sentences and catalogue rules that produced it
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import rules as R
from ..model import Design
from .analysis import Analysis, analyse
from .evaluate import Review, review
from .repair import repair
from .synthesis import synthesise


@dataclass
class EngineResult:
    design: Design
    analysis: Analysis
    review: Review
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
    d, diags, log = repair(syn.design)
    rv = review(d, an, syn.generic)
    return EngineResult(d, an, rv, diags, syn.trace, syn.log + log)


__all__ = ["EngineResult", "design", "analyse", "synthesise", "review", "repair"]
