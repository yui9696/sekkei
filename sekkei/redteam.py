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
  RT10 assumed over stated   the engine answered a question the author had already answered in the text

Findings carry a severity: high when a must-have is affected or the engine misbehaves, else
info. The exit code of `sekkei redteam` is 1 when a high finding exists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import model as M
from .engine import EngineResult, design
from .engine import gaps


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


#: an acceptance check that quotes its requirement ("R-3 (must): <the sentence> — exercised through …")
#: is traceability, not design: the attacks below must not count it as the requirement being honoured
QUOTED_ACCEPTANCE = re.compile(r"^R-\d+ \((?:must|should|could)\): ")


def shape(d: M.Design) -> dict:
    return {
        "components": sorted((c.name, c.kind, tuple(sorted(c.requires))) for c in d.components),
        "interfaces": sorted((i.owner, i.name, tuple(sorted(o.name for o in i.operations))) for i in d.interfaces),
        # contract preconditions carry the stated numbers (retry schedules, windows): losing one is a change
        "contracts": sorted(re.sub(r"\bR-\d+\b", "R-?", f"{i.name}:{o.name}:{o.pre}:{o.post}") for i in d.interfaces for o in i.operations if o.pre or o.post),
        "entities": sorted((e.name, tuple(f.name for f in e.fields)) for e in d.entities),
        "flows": sorted((f.name, len(f.steps)) for f in d.flows),
        "decisions": sorted((x.title, x.choice) for x in d.decisions if x.status == "accepted"),
        "packages": sorted(w.title for w in d.work_packages),
        "acceptance": sorted(re.sub(r"\bR-\d+\b", "R-?", f"{a.kind}:{a.description}:{a.command}")
                             for w in d.work_packages for a in w.acceptance if not QUOTED_ACCEPTANCE.match(a.description)),
        "metrics": sorted(f"{r.metric.name}:{r.metric.target}" for r in d.requirements if r.metric and not r.rationale.startswith("assumed")),
        "conventions": sorted(d.conventions.rules),
        "risks": sorted(k.description for k in d.risks),
    }


def _remove_sentence(text: str, sentence: str, source: str | None) -> str | None:
    """Delete one requirement from the text: the whole bullet (including its wrapped continuation lines) when the
    sentence is the bullet, a table row when it came from a table, else the substring. Row ids ("2-1", "R-01",
    "#101"), a prepended "(must)" and a "Label: " from a titled table cell are ignored when matching."""
    needle = (source or sentence).strip()
    if "\n" in needle:                       # a Given/When/Then block: remove its lines
        lines_ = text.splitlines()
        drop = {l.strip() for l in needle.splitlines()}
        kept = [l for l in lines_ if l.strip() not in drop]
        return "\n".join(kept) if len(kept) < len(lines_) else None
    core = re.sub(r"^\s*(?:[A-Za-z]{1,4}-?\d{1,6}|\d+-\d+|N-\d+)\s+", "", needle)
    core = re.sub(r"\s*\((?:must|should|could)\)\s*$", "", core).strip().rstrip("。.")
    cands = [needle.rstrip("。."), core, re.sub(r"^[^:：]{1,24}[:：]\s*", "", core)]
    if "; " in core and ":" in core:                       # every-cell table row: match on its longest cell
        cells = [re.sub(r"^[^:：]{1,24}[:：]\s*", "", c).strip() for c in core.split("; ")]
        cands.append(max(cells, key=len))
    cands = [c for c in dict.fromkeys(cands) if len(c) >= 12]
    norm = lambda t: " ".join(t.split())
    lines = text.splitlines()
    # group bullets with their wrapped continuation lines
    units: list[tuple[int, int]] = []
    n = 0
    while n < len(lines):
        if re.match(r"^\s*(?:[-*+•・●]|\d+[.)])\s+", lines[n]):
            m = n + 1
            while m < len(lines) and lines[m].strip() and not re.match(r"^\s*(?:[-*+•・●]|\d+[.)])\s+|^\s*#|^\s*\|", lines[m]) and (lines[m].startswith((" ", "\t")) or not lines[m - 1].rstrip().endswith((".", "。", ":"))):
                m += 1
            units.append((n, m))
            n = m
        elif lines[n].strip() and not re.match(r"^\s*#|^\s*\|", lines[n]):
            m = n + 1          # a prose paragraph: consecutive non-empty, non-bullet, non-heading lines
            while m < len(lines) and lines[m].strip() and not re.match(r"^\s*(?:[-*+•・●]|\d+[.)])\s+|^\s*#|^\s*\|", lines[m]):
                m += 1
            units.append((n, m))
            n = m
        else:
            units.append((n, n + 1))
            n += 1
    for a, b in units:
        block = " ".join(lines[a:b])
        body = norm(re.sub(r"^\s*(?:[-*+•・●]|\d+[.)]|[A-Z]?\d+(?:\.\d+)+|第\s*\d+\s*[条項])\s*", "", block)).rstrip("。.")
        for cand in cands:
            nc = norm(cand)
            if body == nc or body == norm(needle).rstrip("。."):
                return "\n".join(lines[:a] + lines[b:])
            if nc in norm(block):
                if block.strip().startswith("|"):
                    return "\n".join(lines[:a] + lines[b:])       # a table row is one requirement: drop the row
                nb = norm(block).replace(nc, "", 1)
                return "\n".join(lines[:a] + [nb] + lines[b:])
    return None


_NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w.])")


# ---------------------------------------------------------------------------
# Attacks
# ---------------------------------------------------------------------------


RT01_CAP = 80   # engine runs for the deletion attack; beyond this the attack samples (reported in the findings)


def _inert(text: str, base: EngineResult, rt: RedTeam) -> None:
    ref = shape(base.design)
    sources = dict(base.analysis.normalisation.sources) if base.analysis.normalisation else {}
    if base.analysis.structure:
        for folded, src in base.analysis.structure.sources.items():
            sources.setdefault(folded, src)
    # a requirement's statement may carry the row id the structure pass kept; its source line carries it too
    for u in base.analysis.requirements:
        if u.sentence.row_id and u.sentence.text not in sources:
            sources[u.sentence.text] = u.sentence.row_id + " " + u.sentence.text
    units = [u for u in base.analysis.requirements if not u.sentence.assumed]
    if len(units) > RT01_CAP:
        rt.findings.append(Finding("RT01", "info", "sampling", f"{len(units)} stated requirements; the deletion attack ran on the first {RT01_CAP} only (one engine run each)"))
        units = units[:RT01_CAP]
    skipped: list[str] = []
    for u in units:
        src = sources.get(u.sentence.text)
        cut = _remove_sentence(text, u.sentence.text, src)
        if cut is None:
            skipped.append(u.id)
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
    if skipped:
        sev = "high" if len(skipped) > len(units) // 2 else "medium"
        rt.findings.append(Finding("RT01", sev, "coverage", f"{len(skipped)} of {len(units)} stated requirements could not be located in the source text and were NOT tested by the deletion attack "
                                   f"({', '.join(skipped[:8])}{'…' if len(skipped) > 8 else ''}); a green result covers only the rest"))


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


_CONTRADICTION_PAIRS = [
    ("retention vs deletion", r"\b(?:retained|kept|stored) (?:indefinitely|forever|permanently)\b|\bnever (?:be )?deleted\b|\bmust not be deleted\b|永年|削除しない",
     r"\bdelet(?:e|ed|es|ion) (?:after|within|on request|when)\b|\bpurged? after\b|\bexpire(?:s|d)? after\b|\b削除\b"),
    ("residency vs hosting", r"\b(?:stay|stays|remain|remains|kept|processed|hosted) (?:in|within) (?:the )?(?:uk|eu|europe|japan|germany|sweden|finland|nordic|canada|australia)\b|\bmust not leave\b|国内",
     r"\b(?:hosted|hosting|run|runs|processed|stored) (?:in|on) (?:the )?(?:us|usa|united states|us-east|us-west|virginia|singapore|india)\b|\bus[- ]hosted\b|\bamerican\b"),
    ("anonymity vs identifiers", r"\bno identifiable\b|\banonymi[sz]ed\b|\bde-?identified\b|\bpseudonymi[sz]ed\b|匿名",
     r"\bemail address(?:es)?\b|\bfull names?\b|\bdate of birth\b|\bnational (?:id|insurance)\b|\bphone numbers?\b"),
    ("forbidden practice vs current practice", r"\b(?:forbidden|prohibited|not allowed|must not) .{0,40}\b(?:download|extract|export|copy)|\bmust not (?:download|extract|export|copy)\b",
     r"\b(?:download|extract|export|copy)(?:s|ed)? .{0,40}\b(?:laptops?|usb|local (?:disk|machine)|desktop)\b|\bhappens today\b"),
    ("single region vs several", r"\bsingle region\b|\bone region\b", r"\btwo regions\b|\bmulti-?region\b|\bboth regions\b|\bper region\b|\beach region\b"),
    ("one store vs another", r"\bpostgres(?:ql)?\b.{0,30}\b(?:primary|main|the) (?:store|database)\b|\bstore(?:d)? in postgres", r"\bparquet\b|\bduckdb\b|\bstored as files\b|\bflat files\b"),
]


def _contradictions(base: EngineResult, rt: RedTeam) -> None:
    pos: dict[tuple[str, str], str] = {}
    neg: dict[tuple[str, str], str] = {}
    for u in base.analysis.requirements:
        low = u.sentence.lower
        for m in _NEG_VERB.finditer(low):
            if re.search(r"\b(?:that|which|whose|if|unless|while)\b", low[m.end(): m.end() + 60]):
                continue                 # "cannot place an order for a product that is not in stock": a condition, not a contradiction
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
            if k in seen and seen[k][1] != r.metric.target and "target to be agreed" not in k and k not in ("time", "value", "size"):
                rt.findings.append(Finding("RT05", "medium", f"{seen[k][0]}/{r.id}", f"metric '{k}' has two targets: {seen[k][1]} and {r.metric.target}"))
            seen.setdefault(k, (r.id, r.metric.target))
    # sentence pairs that usually cannot both hold: reported as candidates, the reader decides
    stated = [(r.id, r.statement) for r in base.design.requirements if not r.rationale.startswith("assumed")] + [("non-goal", g) for g in base.design.non_goals]
    for label, rx_a, rx_b in _CONTRADICTION_PAIRS:
        a = [(i, s) for i, s in stated if re.search(rx_a, s, re.I)]
        b = [(i, s) for i, s in stated if re.search(rx_b, s, re.I)]
        for ia, sa in a[:2]:
            for ib, sb in b[:2]:
                if ia != ib:
                    rt.findings.append(Finding("RT05", "medium", f"{ia}/{ib}", f"possible contradiction ({label})", f"{sa[:110]} ⟷ {sb[:110]}"))


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
    hay = re.sub(r'"description": "R-\d+ \((?:must|should|could)\): [^"]*"', '""', hay)   # …and so is an acceptance check that quotes it
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


#: words too common in an assumed answer to prove that the author's sentence means the same thing
_ECHO_STOP = {"the", "and", "with", "per", "for", "from", "into", "behind", "several", "instances", "instance", "stated",
              "engine", "default", "assumed", "system", "systems", "service", "services", "data", "record", "records",
              "operations", "first", "release", "team", "people", "single", "small", "existing", "available", "each"}


def _assumed_over_stated(base: EngineResult, rt: RedTeam) -> None:
    """An engine assumption on a topic the author wrote about.

    The engine answers its own questions so that a thin text still yields a design. When the
    author *did* write about the topic, the answer must repeat what they wrote — otherwise the
    design carries the engine's preference where the customer stated theirs, and downstream
    (ADRs, briefs, the requirement table) the two are indistinguishable.
    """
    for x in base.design.decisions:
        if x.status != "proposed":
            continue
        m = re.search(r"\((Q-[a-z]+)\)", x.title)
        if not m:
            continue
        said = gaps.answered_in_text(m.group(1), base.analysis)
        if not said:
            continue
        keys = [w for w in re.findall(r"[A-Za-z][\w.+#/-]{2,}", x.choice) if w.lower() not in _ECHO_STOP]
        if any(any(re.search(r"\b" + re.escape(k) + r"\b", t, re.I) for k in keys) for t in said):
            continue          # the assumed answer repeats what the text says: no conflict
        topic = x.title.split(":", 1)[1].split("(")[0].strip()
        strong = [t for t in said if re.search(r"\bno\b|\bnot\b|\bnever\b|\bonly\b|\bmust\b|\bshall\b|\b既存\b|禁止", t, re.I)]
        rt.findings.append(Finding("RT10", "high" if strong else "medium", x.id,
                                   f"the engine assumed “{x.choice}” for {topic}, but the text speaks to it; the assumption is appended to the requirements and is not marked as disputed",
                                   (strong or said)[0][:160]))


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
    _assumed_over_stated(base, rt)
    _deliverable_drift(base, rt)
    _inert(text, base, rt)
    _fragile(text, base, rt)
    return rt
