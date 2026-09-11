"""The architect's notes: everything the engine hands over besides the design itself."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Design
from .analysis import Analysis
from .evaluate import Review
from .gaps import Question, questions, questions_markdown
from .sizing import Capacity, Effort, capacity, capacity_markdown, effort, effort_markdown
from .threats import threats_markdown


REQUIREMENTS_TEMPLATE = """\
# <System name>

<One or two sentences: who uses it and what problem it solves.>

## Functional
- <Actor> can <verb> <object> ... (one requirement per bullet; verbs such as create/list/delete/search/export/rotate become operations)
- <What the system does>; numbers in the sentence (retry schedule, limits, windows) become contract preconditions.

## Non-functional
- <Rate>: 1,000 requests/s sustained; 5,000 endpoints; 200,000 items.
- <Latency>: p95 under 300 ms for <operation>.
- <Durability / consistency>: no <thing> lost on crash; never double-applied.
- <Isolation / availability>: one slow <thing> must not delay others; 99.9 % monthly.
- <Operations>: metrics for Prometheus; structured logs; alert on <condition>.

## Constraints
- <Language and version>; <database / queue available>; <deployment: containers behind ingress | single binary | on-prem>.
- Team of <N>. <Single region>. <Standard library only>. <Authentication via the OIDC provider>.

## Out of scope
- <What the design must not cover.>
"""


@dataclass
class Notes:
    review: Review
    questions: list[Question]
    capacity: Capacity
    effort: Effort
    threats_md: str
    analysis_md: str = ""
    sections: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        s = ["# Architect's notes (engine)\n",
             "Everything a solution architect hands over besides the design: the questions still open, the\n"
             "assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.\n"]
        s.append("## 1. Questions to answer before committing\n")
        s.append("Answer by adding bullets to the requirements and running `sekkei design` again; each answer changes only what its last column names.\n")
        s.append(questions_markdown(self.questions))
        s.append("## 2. Capacity estimates\n")
        s.append(capacity_markdown(self.capacity))
        s.append("## 3. Effort and schedule\n")
        s.append(effort_markdown(self.effort))
        s.append("## 4. Threat model (STRIDE-lite)\n")
        s.append("Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.\n")
        s.append(self.threats_md)
        s.append("## 5. What the engine could not decide\n")
        rv = self.review.to_markdown().split("\n", 3)[3] if self.review.to_markdown().count("\n") > 3 else self.review.to_markdown()
        s.append(rv.replace("\n## ", "\n### ").lstrip("\n"))
        if self.analysis_md:
            s.append("## 6. How the text was read\n")
            s.append(self.analysis_md)
        return "\n".join(s).rstrip() + "\n"


def analysis_markdown(an: Analysis) -> str:
    s = [f"- Patterns recognised: {', '.join(an.patterns) or '(none; layered fallback)'}",
         f"- Quality attributes (weight): {', '.join(f'{q} {w}' for q, w in an.qualities.items()) or '(none)'}",
         f"- Constraint tokens: {', '.join(sorted(an.constraints)) or '(none)'}; languages: {', '.join(an.languages) or '(none)'}; team: {an.team_size or 'unknown'}",
         "", "| id | kind | priority | patterns | qualities | metric |", "|---|---|---|---|---|---|"]
    for u in an.requirements:
        m = f"{u.metric[0]} {u.metric[1]} {u.metric[2]}".strip() if u.metric else "—"
        s.append(f"| {u.id} | {u.kind} | {u.priority} | {', '.join(u.patterns) or ('—' if u.kind != 'functional' else '**none**')} | {', '.join(u.qualities) or '—'} | {m} |")
    return "\n".join(s) + "\n"


def notes(design: Design, an: Analysis, review: Review) -> Notes:
    return Notes(review, questions(an), capacity(an), effort(design, an), threats_markdown(design), analysis_markdown(an))
