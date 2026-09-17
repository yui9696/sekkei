"""The architect's notes: everything the engine hands over besides the design itself."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Design
from .analysis import Analysis
from .answers import Answer, answers_markdown
from .evaluate import Review
from .gaps import Question, questions, questions_markdown
from .owners import Placement, placements_markdown
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
    normalisation_md: str = ""
    sections: list[str] = field(default_factory=list)
    answers: list[Answer] = field(default_factory=list)
    placements_md: str = ""

    def machine(self) -> dict:
        """Machine-readable notes: every estimate as expression + inputs + value; effort as its DAG and waves; SLOs."""
        return {
            "capacity": {"estimates": [e.machine() for e in self.capacity.estimates], "assumptions": self.capacity.assumptions, "missing": self.capacity.missing},
            "effort": self.effort.machine(),
            "questions": [q.__dict__ for q in self.questions],
            "answers": [{"question_id": a.question_id, "answer": a.answer, "evidence": a.evidence} for a in self.answers],
            "unaddressed": self.review.unaddressed,
            "unrecognised": self.review.unrecognised,
        }

    def to_markdown(self) -> str:
        s = ["# Architect's notes (engine)\n",
             "Everything a solution architect hands over besides the design: the questions still open, the\n"
             "assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.\n"]
        if self.answers:
            s.append("## 1. Questions the engine answered for you (confirm or override)\n")
            s.append("Each answer is a proposed decision in the design and a bullet in the augmented requirements. "
                     "To override, state the real answer in your requirements and run again.\n")
            s.append(answers_markdown(self.answers))
            answered = {a.question_id for a in self.answers}
            left = [q for q in self.questions if q.id not in answered]
            if left:
                s.append("Still open:\n")
                s.append(questions_markdown(left))
        else:
            s.append("## 1. Questions to answer before committing\n")
            s.append("Answer by adding bullets to the requirements and running `sekkei design` again; each answer changes only what its last column names.\n")
            s.append(questions_markdown(self.questions))
        if self.placements_md:
            s.append("## 1b. Requirements placed without a catalogue pattern\n")
            s.append(self.placements_md)
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
        if self.normalisation_md:
            s.append(self.normalisation_md.replace("## ", "### ", 1).replace("### Input", "## 7. Input", 1))
        return "\n".join(s).rstrip() + "\n"


def analysis_markdown(an: Analysis) -> str:
    s = [f"- Patterns recognised: {', '.join(an.patterns) or '(none; layered fallback)'}",
         f"- Quality attributes (weight): {', '.join(f'{q} {w}' for q, w in an.qualities.items()) or '(none)'}",
         f"- Constraint tokens: {', '.join(sorted(an.constraints)) or '(none)'}; languages: {', '.join(an.languages) or '(none)'}; team: {an.team_size or 'unknown'}",
         "", "| id | kind | priority | patterns | qualities | metric |", "|---|---|---|---|---|---|"]
    for u in an.requirements:
        m = (f"{u.metric[0]} {u.metric[1]}" + ("" if not u.metric[2] or u.metric[2] in u.metric[1] else " " + u.metric[2])).strip() if u.metric else "—"
        s.append(f"| {u.id} | {u.kind} | {u.priority} | {', '.join(u.patterns) or ('—' if u.kind != 'functional' else '**none**')} | {', '.join(u.qualities) or '—'} | {m} |")
    return "\n".join(s) + "\n"


def notes(design: Design, an: Analysis, review: Review, answers: list[Answer] | None = None,
          placements: list[Placement] | None = None) -> Notes:
    return Notes(review, questions(an), capacity(an), effort(design, an), threats_markdown(design), analysis_markdown(an),
                 normalisation_md=an.normalisation.to_markdown() if an.normalisation else "",
                 answers=list(answers or []), placements_md=placements_markdown(placements, design) if placements else "")
