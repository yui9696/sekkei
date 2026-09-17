"""Adversarial self-audit of a design: does the engine honour every sentence, and how much is guessed?

The engine can be wrong in ways its linter cannot see: a lint-clean design may ignore a
requirement entirely (nothing in the design changes when the sentence is deleted), lose a
number the text stated, contradict itself, or rest mostly on assumptions. This module
attacks the design with the requirements text as the oracle:

  RT01 inert requirement     delete the sentence -> the design (minus its own id) is unchanged
  RT02 fragile decision      double every rate / halve every latency / drop a constraint -> which choices flip
  RT03 uncovered requirement no component satisfies it (the linter tolerates this for constraints)
  RT04 non-determinism       two runs differ byte for byte
  RT05 contradiction         must and must not on the same verb and object; the same metric with two targets
  RT06 assumption load       more decisions proposed from assumptions than taken from the text
  RT07 unrecognised          sentences no pattern understood (restated here so they are not forgotten)
  RT08 lost number           a number in a requirement that appears nowhere else in the design
  RT09 deliverable drift     the roadmap total and the notes disagree (the two documents share one formula; this is the check)

Findings carry a severity: high when a must-have is affected or the engine misbehaves, else
info. The exit code of `sekkei redteam` is 1 when a high finding exists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import model as M
from .engine import EngineResult, design


@dataclass
class Finding:
    rule: str
    severity: str        # high | medium | info
    subject: str         # requirement id, decision id, ...
    message: str
    evidence: str = ""


@dataclass
class RedTeam:
    findings: list[Finding] = field(default_factory=list)
    runs: int = 0

    @property
    def high(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "high"]

    def to_markdown(self) -> str:
        s = ["# Red-team report (engine self-audit)\n",
             f"{len(self.findings)} finding(s) from {self.runs} engine runs: "
             f"{len(self.high)} high, {sum(1 for f in self.findings if f.severity == 'medium')} medium, "
             f"{sum(1 for f in self.findings if f.severity == 'info')} info.\n"]
        for sev in ("high", "medium", "info"):
            fs = [f for f in self.findings if f.severity == sev]
            if not fs:
                continue
            s.append(f"## {sev}\n")
            for f in fs:
                s.append(f"- **{f.rule}** [{f.subject}] {f.message}" + (f"\n  - evidence: {f.evidence}" if f.evidence else ""))
            s.append("")
        if not self.findings:
            s.append("No findings: every requirement moves the design, no number was lost, and the design is deterministic.\n")
        return "\n".join(s).rstrip() + "\n"

    def to_json(self) -> dict:
        return {"runs": self.runs, "findings": [f.__dict__ for f in self.findings]}


# ---------------------------------------------------------------------------
# Shape: the design minus requirement ids, so that renumbering after a deletion is invisible
# ---------------------------------------------------------------------------


def shape(d: M.Design) -> dict:
    return {
        "components": sorted((c.name, c.kind, tuple(sorted(c.requires))) for c in d.components),
        "interfaces": sorted((i.owner, i.name, tuple(sorted(o.name for o in i.operations))) for i in d.interfaces),
        "entities": sorted((e.name, tuple(f.name for f in e.fields)) for e in d.entities),
        "flows": sorted((f.name, len(f.steps)) for f in d.flows),
        "decisions": sorted((x.title, x.choice) for x in d.decisions if x.status == "accepted"),
        "packages": sorted((w.title, w.size) for w in d.work_packages),
        "acceptance": sorted(re.sub(r"\bR-\d+\b", "R-?", f"{a.kind}:{a.description}:{a.command}") for w in d.work_packages for a in w.acceptance),
        "metrics": sorted(f"{r.metric.name}:{r.metric.target}" for r in d.requirements if r.metric and not r.rationale.startswith("assumed")),
        "conventions": sorted(d.conventions.rules),
        "risks": sorted(k.description for k in d.risks),
    }


def _remove_sentence(text: str, sentence: str, source: str | None) -> str | None:
    """Delete one requirement from the text: the whole bullet line when the sentence is the line, else the substring."""
    needle = source or sentence
    lines = text.splitlines()
    for n, line in enumerate(lines):
        body = re.sub(r"^\s*(?:[-*•・●]|\d+[.)])\s*", "", line).strip()
        if body == needle.strip() or body.rstrip("。.") == needle.strip().rstrip("。."):
            return "\n".join(lines[:n] + lines[n + 1:])
        if needle.strip() in line:
            return "\n".join(lines[:n] + [line.replace(needle.strip(), "", 1)] + lines[n + 1:])
    return None


_NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w.])")


# ---------------------------------------------------------------------------
# Attacks
# ---------------------------------------------------------------------------


def _inert(text: str, base: EngineResult, rt: RedTeam) -> None:
    ref = shape(base.design)
    sources = base.analysis.normalisation.sources if base.analysis.normalisation else {}
    for u in base.analysis.requirements:
        if u.sentence.assumed:
            continue
        src = sources.get(u.sentence.text)
        cut = _remove_sentence(text, u.sentence.text, src)
        if cut is None:
            continue
        r2 = design(cut)
        rt.runs += 1
        if r2.design.requirements and shape(r2.design) == ref:
            if u.kind == "constraint":
                rt.findings.append(Finding("RT01", "info", u.id, "deleting this constraint changes nothing: it coincides with what the engine assumes by default (still worth stating)",
                                           u.sentence.text[:160]))
                continue
            sev = "high" if u.kind == "functional" and u.priority == "must" else "medium"
            rt.findings.append(Finding("RT01", sev, u.id, "deleting this sentence changes nothing in the design: it is recorded as a requirement but not honoured",
                                       u.sentence.text[:160]))


def _fragile(text: str, base: EngineResult, rt: RedTeam) -> None:
    accepted = {x.title: x.choice for x in base.design.decisions if x.status == "accepted"}
    variants = []
    rate_text = re.sub(r"(\d[\d,]*)(\s*)(/s\b|/sec\b|per second|requests/s|rps)", lambda m: f"{int(m.group(1).replace(',', '')) * 2}{m.group(2)}{m.group(3)}", text)
    if rate_text != text:
        variants.append(("every rate doubled", rate_text))
    lat_text = re.sub(r"(\d+)(\s*ms\b)", lambda m: f"{max(1, int(m.group(1)) // 2)}{m.group(2)}", text)
    if lat_text != text:
        variants.append(("every latency target halved", lat_text))
    for u in base.analysis.requirements:
        if u.kind == "constraint" and not u.sentence.assumed:
            cut = _remove_sentence(text, u.sentence.text, base.analysis.normalisation.sources.get(u.sentence.text) if base.analysis.normalisation else None)
            if cut:
                variants.append((f"constraint {u.id} removed ({u.sentence.text[:60]})", cut))
    for label, variant in variants:
        r2 = design(variant)
        rt.runs += 1
        after = {x.title: x.choice for x in r2.design.decisions if x.status == "accepted"}
        flips = [(t, accepted[t], after[t]) for t in accepted if t in after and after[t] != accepted[t]]
        gone = [t for t in accepted if t not in after]
        if flips:
            rt.findings.append(Finding("RT02", "info", label, f"{len(flips)} decision(s) change: " + "; ".join(f"{t}: {a} → {b}" for t, a, b in flips)))
        if gone and label.startswith("constraint"):
            rt.findings.append(Finding("RT02", "info", label, "decision(s) disappear: " + ", ".join(gone)))


def _uncovered(base: EngineResult, rt: RedTeam) -> None:
    covered = {r for c in base.design.components for r in c.satisfies}
    for r in base.design.requirements:
        if r.id not in covered and r.kind == "functional":
            rt.findings.append(Finding("RT03", "high" if r.priority == "must" else "medium", r.id, "no component satisfies this requirement", r.statement[:160]))


def _determinism(text: str, base: EngineResult, rt: RedTeam) -> None:
    r2 = design(text)
    rt.runs += 1
    if M.dumps(r2.design) != M.dumps(base.design) or r2.notes.to_markdown() != base.notes.to_markdown():
        rt.findings.append(Finding("RT04", "high", "engine", "two runs on the same text differ"))


_NEG_VERB = re.compile(r"\b(?:must not|never|cannot|may not|shall not|must never)\s+(?:be\s+)?([a-z]+)\b")
_POS_VERB = re.compile(r"\b(?:can|must|should|shall|will|may)\s+(?:be\s+)?([a-z]+)\b")


def _verb_obj(m: re.Match, low: str) -> tuple[str, str] | None:
    from .engine import text as T
    v = T.verb_of(m.group(1))
    if not v:
        return None
    after = [w for w in T.tokens(low[m.end():m.end() + 60]) if w not in T.STOPWORDS and w not in T.NON_OBJECTS]
    return (v, after[0]) if after else None


def _contradictions(base: EngineResult, rt: RedTeam) -> None:
    pos: dict[tuple[str, str], str] = {}
    neg: dict[tuple[str, str], str] = {}
    for u in base.analysis.requirements:
        low = u.sentence.lower
        for m in _NEG_VERB.finditer(low):
            k = _verb_obj(m, low)
            if k:
                neg[k] = u.id
        for m in _POS_VERB.finditer(low):
            if re.search(r"\b(?:not|never)\s+$", low[:m.start() + 1]) or low[max(0, m.start() - 6):m.start()].strip().endswith("not"):
                continue
            k = _verb_obj(m, low)
            if k:
                pos[k] = u.id
    for key in set(pos) & set(neg):
        if pos[key] != neg[key]:
            rt.findings.append(Finding("RT05", "high", f"{pos[key]}/{neg[key]}", f"'{key[0]} {key[1]}' is required by one sentence and forbidden by another"))
    seen: dict[str, tuple[str, str]] = {}
    for r in base.design.requirements:
        if r.metric and r.kind == "nonfunctional":
            k = r.metric.name
            if k in seen and seen[k][1] != r.metric.target and "target to be agreed" not in k:
                rt.findings.append(Finding("RT05", "medium", f"{seen[k][0]}/{r.id}", f"metric '{k}' has two targets: {seen[k][1]} and {r.metric.target}"))
            seen.setdefault(k, (r.id, r.metric.target))


def _assumption_load(base: EngineResult, rt: RedTeam) -> None:
    proposed = [x for x in base.design.decisions if x.status == "proposed"]
    accepted = [x for x in base.design.decisions if x.status == "accepted"]
    assumed = [u for u in base.analysis.requirements if u.sentence.assumed]
    stated = [u for u in base.analysis.requirements if not u.sentence.assumed]
    if proposed and len(proposed) > len(accepted):
        rt.findings.append(Finding("RT06", "medium", "decisions", f"{len(proposed)} decisions are proposed from assumptions against {len(accepted)} taken from the text; answer the questions in NOTES.md §1 before building"))
    if assumed and len(assumed) >= len(stated):
        rt.findings.append(Finding("RT06", "medium", "requirements", f"{len(assumed)} requirements were assumed by the engine against {len(stated)} stated"))


def _unrecognised(base: EngineResult, rt: RedTeam) -> None:
    for rid, txt in base.review.unrecognised:
        rt.findings.append(Finding("RT07", "medium", rid, "no catalogue pattern recognised this sentence; it was placed by the engine's fallback", txt[:160]))


def _lost_numbers(base: EngineResult, rt: RedTeam) -> None:
    d = base.design
    hay = M.dumps(M.Design(name=d.name, components=d.components, interfaces=d.interfaces, entities=d.entities, flows=d.flows,
                           decisions=d.decisions, risks=d.risks, work_packages=d.work_packages,
                           requirements=[M.Requirement(r.id, "", r.kind, r.priority, r.metric) for r in d.requirements]))
    hay = re.sub(r'"description": "from R-\d+: [^"]*"', '""', hay)   # verbatim quotes of the sentence are traceability, not honouring
    hay += base.notes.to_markdown().split("## 6.")[0]   # notes sections before the sentence table
    strong = re.sub(r"stated values: [^\"\n]*", "", hay)      # the engine's catch-all note on operations does not count as a contract
    for u in base.analysis.requirements:
        if u.sentence.assumed or u.kind == "constraint":
            continue
        for q in u.sentence.quantities:
            if q.kind == "code":
                continue
            raw = q.raw.split()[0]
            forms = {raw, raw.replace(",", ""), f"{q.value:g}", f"{q.value:,.0f}"}
            found = lambda h: any(re.search(r"(?<![\w.,-])" + re.escape(f) + r"(?![\w.,]\w)", h) for f in forms)
            if not found(hay):
                rt.findings.append(Finding("RT08", "high" if u.priority == "must" else "medium", u.id,
                                           f"the number {q.raw} appears in the requirement but nowhere in the design (no metric, precondition, decision or estimate carries it)",
                                           u.sentence.text[:160]))
            elif not found(strong):
                rt.findings.append(Finding("RT08", "info", u.id,
                                           f"the number {q.raw} reaches the design only as a 'stated values' note on operations; no metric, specific precondition or decision uses it",
                                           u.sentence.text[:160]))


def _deliverable_drift(base: EngineResult, rt: RedTeam) -> None:
    e = base.notes.effort
    if sum(e.phase_days) != e.calendar_days or e.critical_path_days > e.calendar_days:
        rt.findings.append(Finding("RT09", "high", "effort", f"calendar {e.calendar_days} ≠ sum of phases {sum(e.phase_days)} or below the critical path {e.critical_path_days}"))


def run(text: str, base: EngineResult | None = None) -> RedTeam:
    rt = RedTeam()
    base = base or design(text)
    rt.runs += 1
    if not base.design.requirements:
        rt.findings.append(Finding("RT07", "high", "input", "no requirements found; nothing to audit"))
        return rt
    _determinism(text, base, rt)
    _uncovered(base, rt)
    _contradictions(base, rt)
    _assumption_load(base, rt)
    _unrecognised(base, rt)
    _lost_numbers(base, rt)
    _deliverable_drift(base, rt)
    _inert(text, base, rt)
    _fragile(text, base, rt)
    return rt
