"""The rest of what a solution architect hands over: ADRs, C4 diagrams, risk register, FMEA,
roadmap, RACI, SLOs, a cost model and runbooks — all derived from the design graph and the
architect's notes, all deterministic, none of it invented.

Two rules keep this honest:

* every number is either in the requirements, computed by a formula shown next to it, or
  marked as an assumption in the same table (never a plausible-looking default that hides);
* prices are never guessed. The cost model lists quantities and formulas; unit prices come
  from a prices file the reader supplies, or the price column stays "?" and the total is a
  formula.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import graph as G
from . import model as M
from . import render as RD
from .model import Design, Requirement, WorkPackage

LEVEL = {"low": 1, "medium": 2, "high": 3}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "x"


def _table(header: list[str], rows: list[list[str]]) -> str:
    esc = lambda x: str(x).replace("|", "¦").replace("\n", " ")
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def _decision(design: Design, word: str):
    """The decision about *word* — a catalogue decision by title, else the engine's assumed answer (title 'Assumed answer: … (Q-word)')."""
    for d in design.decisions:
        if d.status == "accepted" and word in d.title.lower():
            return d
    for d in design.decisions:
        if word in d.title.lower():
            return d
    return None


def _wp_of(design: Design) -> dict[str, WorkPackage]:
    return {c: w for w in design.work_packages for c in w.components}


def _dependents(design: Design) -> dict[str, set[str]]:
    """component id -> components that (transitively) require one of its interfaces."""
    owner = {i.id: i.owner for i in design.interfaces}
    direct: dict[str, set[str]] = {c.id: set() for c in design.components}
    for c in design.components:
        for i in c.requires:
            b = owner.get(i)
            if b and b != c.id:
                direct.setdefault(b, set()).add(c.id)
    out: dict[str, set[str]] = {}
    for cid in direct:
        seen: set[str] = set()
        stack = [cid]
        while stack:
            x = stack.pop()
            for y in direct.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        out[cid] = seen
    return out


# ---------------------------------------------------------------------------
# 1. Executive summary
# ---------------------------------------------------------------------------


def executive_summary(design: Design, notes) -> str:
    musts = [r for r in design.requirements if r.priority == "must" and r.kind == "functional"]
    nfr = [r for r in design.requirements if r.kind == "nonfunctional" and r.metric]
    risks = sorted(design.risks, key=lambda k: -(LEVEL.get(k.likelihood, 2) * LEVEL.get(k.impact, 2)))[:5]
    open_qs = [q for q in notes.questions if q.id not in {a.question_id for a in notes.answers}]
    text_qs = list(getattr(notes, "text_questions", []) or [])
    s = [f"# {design.name} — executive summary\n", design.summary or "", "",
         "## What is being built\n"]
    s += [f"- {g}" for g in design.goals[:8]] or ["- (no goals derived; see the requirements)"]
    if design.non_goals:
        s.append("\nOut of scope: " + "; ".join(design.non_goals[:5]))
    s += ["", "## Shape of the solution\n",
          f"- {len(design.components)} components ({sum(1 for c in design.components if c.kind == 'external')} external), "
          f"{len(design.interfaces)} interfaces, {len(design.entities)} entities, {len(design.flows)} flows.",
          f"- {len([d for d in design.decisions if d.status == 'accepted'])} architecture decisions taken; "
          f"{len([d for d in design.decisions if d.status == 'proposed'])} proposed from assumptions (confirm before build).",
          f"- {len(musts)} must-have functional requirements; {len(nfr)} measurable quality targets.",
          "", "## Effort and calendar (assumptions stated in the notes)\n",
          f"- {notes.effort.person_days} person-days across {len(design.work_packages)} work packages in {len(notes.effort.waves)} waves; "
          f"critical path {notes.effort.critical_path_days} days; about **{notes.effort.calendar_days} working days** with a team of {notes.effort.team}.",
          "", "## Top risks\n"]
    s += [f"- **{k.id}** ({k.likelihood}/{k.impact}): {k.description} — *{k.mitigation}*" for k in risks]
    s += ["", "## Decisions that need a human\n"]
    s += [f"- {d.id} {d.title}: proposed **{d.choice}**" for d in design.decisions if d.status == "proposed"][:10] or ["- none; every decision is backed by the text"]
    s += ["", f"## Open questions: {len(open_qs) + len(text_qs)}\n"]
    s += [f"- (from the text) {q}" for q in text_qs[:10]]
    s += [f"- {q.question}" for q in open_qs[:10]]
    return "\n".join(s).rstrip() + "\n"


# ---------------------------------------------------------------------------
# 2. ADRs (MADR shape)
# ---------------------------------------------------------------------------


def adrs(design: Design) -> dict[str, str]:
    out: dict[str, str] = {}
    names = {c.id: c.name for c in design.components}
    for n, d in enumerate(design.decisions, 1):
        s = [f"# ADR-{n:04d}: {d.title}\n",
             f"- Status: {d.status}", f"- Design id: {d.id}",
             f"- Affects: {', '.join(names.get(a, a) for a in d.affects) or '—'}", "",
             "## Context\n", d.context or "(no context recorded)", "", "## Options considered\n"]
        for o in d.options:
            s.append(f"### {o.name}" + (" ← chosen" if o.name == d.choice and d.status != "rejected" else " ← rejected" if d.status == "rejected" else ""))
            s += [f"- (+) {p}" for p in o.pros] + [f"- (−) {c}" for c in o.cons]
            s.append("")
        decided = f"**{d.choice}**" if d.status != "rejected" else "**Rejected** — not part of the design (recorded so the reasoning survives)."
        s += ["## Decision\n", decided, "", d.rationale or "", "", "## Consequences\n", d.consequences or "(none recorded)", ""]
        if d.status == "proposed":
            s.append("> Proposed from an assumption the engine made; confirm or override by stating the answer in the requirements.\n")
        out[f"ADR-{n:04d}-{_slug(d.title)}.md"] = "\n".join(s).rstrip() + "\n"
    return out


# ---------------------------------------------------------------------------
# 3. C4 (context + container) in Mermaid
# ---------------------------------------------------------------------------


def _people(actors: list[str]) -> list[str]:
    from .engine import text as T
    out: list[str] = []
    for a in actors:
        if a not in T.HUMAN_ACTORS:
            continue
        base = a[:-1] if a.endswith("s") and a[:-1] in actors else a
        if base not in out:
            out.append(base)
    return out


def c4_context(design: Design, actors: list[str]) -> str:
    out = ["graph TB", f'  SYS["{design.name}"]']
    for a in _people(actors):
        out.append(f'  A_{_slug(a).replace("-", "_")}(["{a}"])')
        out.append(f'  A_{_slug(a).replace("-", "_")} --> SYS')
    for c in design.components:
        if c.kind == "external":
            out.append(f'  {RD._mid(c.id)}[["{c.name}"]]')
            out.append(f"  SYS --> {RD._mid(c.id)}")
    return "\n".join(out) + "\n"


def c4_container(design: Design) -> str:
    out = ["graph LR"]
    groups: dict[str, list] = {}
    for c in design.components:
        groups.setdefault(c.kind, []).append(c)
    for kind, cs in groups.items():
        out.append(f"  subgraph {kind}")
        for c in cs:
            shape = ("[(", ")]") if c.kind == "datastore" else ("[[", "]]") if c.kind == "external" else ("[", "]")
            out.append(f'    {RD._mid(c.id)}{shape[0]}"{c.name}"{shape[1]}')
        out.append("  end")
    owner = {i.id: i.owner for i in design.interfaces}
    for c in design.components:
        for i in c.requires:
            b = owner.get(i)
            if b and b != c.id:
                out.append(f"  {RD._mid(c.id)} --> {RD._mid(b)}")
    return "\n".join(out) + "\n"


def c4_markdown(design: Design, actors: list[str]) -> str:
    return (f"# C4 — {design.name}\n\n## Level 1: system context\n\n```mermaid\n{c4_context(design, actors)}```\n\n"
            f"## Level 2: containers\n\n```mermaid\n{c4_container(design)}```\n\n"
            "## Level 3: components by responsibility\n\n" +
            _table(["component", "kind", "responsibility", "provides", "requires"],
                   [[c.id + " " + c.name, c.kind, c.responsibility, ", ".join(i.id for i in design.interfaces if i.owner == c.id), ", ".join(c.requires)]
                    for c in design.components]))


# ---------------------------------------------------------------------------
# 4. Risk register
# ---------------------------------------------------------------------------


def risk_register(design: Design) -> str:
    wp = _wp_of(design)
    rows = []
    for k in sorted(design.risks, key=lambda k: (-(LEVEL.get(k.likelihood, 2) * LEVEL.get(k.impact, 2)), k.id)):
        score = LEVEL.get(k.likelihood, 2) * LEVEL.get(k.impact, 2)
        owners = sorted({wp[a].id for a in k.affects if a in wp})
        rows.append([k.id, k.description, k.likelihood, k.impact, str(score), k.mitigation, ", ".join(owners) or "—", ", ".join(k.affects)])
    return ("# Risk register\n\nScore = likelihood × impact on a 1–3 scale (9 = act now). Owner = the work package that builds the affected component; "
            "the mitigation is already in that package's brief.\n\n"
            + _table(["id", "risk", "likelihood", "impact", "score", "mitigation", "owner WP", "affects"], rows))


# ---------------------------------------------------------------------------
# 5. FMEA
# ---------------------------------------------------------------------------

_MODES = (("unavailable", "calls fail or time out"), ("slow", "latency above target; queues grow"), ("corrupt", "wrong or lost data"))
#: archetypes whose failure degrades a side effect (notifications, telemetry, exports) but does not stop the request path
_ASYNC = {"notifier", "email", "sms", "observability", "audit", "bus", "cdn", "backup", "reporting", "batch", "scheduler", "exporter", "sftp_target", "legacy_adapter", "legacy_system"}


def fmea(design: Design) -> str:
    deps = _dependents(design)
    names = {c.id: c.name for c in design.components}
    req = {r.id: r for r in design.requirements}
    has_obs = any("observability" in " ".join(c.tags) for c in design.components)
    redundancy = _decision(design, "redundancy")
    backup = _decision(design, "backup")
    rows = []
    arch = {c.id: {t.split(":", 1)[1] for t in c.tags if t.startswith("archetype:")} for c in design.components}
    for c in design.components:
        is_async = bool(arch[c.id] & _ASYNC)
        affected = {c.id} if is_async else {c.id} | deps.get(c.id, set())
        sat = sorted({r for x in design.components if x.id in affected for r in x.satisfies if r in req and req[r].kind != "constraint"})
        musts = [r for r in sat if r in req and req[r].priority == "must"]
        sev = ("medium" if musts else "low") if is_async else ("high" if musts else "medium" if sat else "low")
        for mode, effect in _MODES:
            if mode == "corrupt" and c.kind not in ("datastore", "job", "module"):
                continue
            if c.kind == "external":
                mitig = "timeouts and retries with backoff on our side; queue the work; circuit-break after repeated failures"
            elif mode == "unavailable" and c.kind in ("service", "job") and redundancy:
                mitig = redundancy.choice
            elif mode == "corrupt" and c.kind == "datastore" and backup:
                mitig = backup.choice
            elif mode == "corrupt":
                mitig = "validate at the boundary; idempotent writes; audit history to reconstruct"
            else:
                mitig = "health check + restart; dependents degrade (read-only / queue) rather than fail"
            detect = "metrics + alert (observability component present)" if has_obs else "**none** — no observability component in the design"
            rows.append([c.id + " " + names[c.id], mode, effect + (" (side effect only: notifications/telemetry/exports degrade, the request path continues)" if is_async and mode != "corrupt" else ""),
                         ", ".join(sorted(names[x] for x in affected - {c.id})) or "—",
                         ", ".join(sat) or "—", sev, detect, mitig])
    return ("# FMEA — failure modes and effects\n\nEffects are computed from the dependency graph (who requires this component's interfaces, transitively) "
            "and from `satisfies` (which requirements stop being met). Components whose work is a side effect (notifier, email/SMS provider, observability, audit, exports, batch, CDN, "
            "legacy exchange) do not propagate: their failure degrades that side effect, not the request path. Severity: high when a must-have requirement on the request path is affected.\n\n"
            + _table(["component", "failure mode", "local effect", "dependents affected", "requirements at risk", "severity", "detection", "mitigation"], rows))


# ---------------------------------------------------------------------------
# 6. Roadmap and RACI
# ---------------------------------------------------------------------------

SIZE_DAYS = G.SIZE_WEIGHT


def roadmap(design: Design, effort) -> str:
    wps = {w.id: w for w in design.work_packages}
    s = ["# Roadmap\n", f"Team of {effort.team}; package sizes S/M/L = 2/5/10 person-days (assumption). Days are working days; "
         "a phase's calendar length is its person-days divided by the team, or its longest package, whichever is larger.\n"]
    day = 0
    rows = []
    for n, (wave, length) in enumerate(zip(effort.waves, effort.phase_days), 1):
        pd = sum(SIZE_DAYS.get(wps[w].size, 5) for w in wave)
        rows.append([f"Phase {n}", f"day {day + 1}–{day + length}", str(pd), ", ".join(f"{w} {wps[w].title} ({wps[w].size})" for w in wave),
                     "; ".join(sorted({a.description for w in wave for a in wps[w].acceptance if a.kind == "metric" and re.search(r"latency|availab|lost|duplicate|unauthenticated|retention|occurrences|metrics exposed", a.description)}))[:200] or "all acceptance checks green"])
        day += length
    s.append(_table(["phase", "calendar", "person-days", "packages (parallel within the phase)", "exit criterion"], rows))
    s.append(f"\nTotal: {effort.person_days} person-days, {day} working days end to end (critical path {effort.critical_path_days} days).\n")
    s.append("\n## Milestones\n")
    s += [f"- End of phase {n}: {', '.join(wps[w].title for w in wave)} done and accepted." for n, wave in enumerate(effort.waves, 1)]
    return "\n".join(s) + "\n"


_SECURITY_ARCH = {"auth", "secrets", "signer", "dispatcher", "tenancy", "data_protection", "admin_api", "surface_api", "ingest_api", "sync", "files", "payments"}
_OPS_KINDS = {"datastore", "job", "service"}


def raci(design: Design, effort) -> str:
    team = max(effort.team, 1)
    engineers = [f"Engineer {i + 1}" for i in range(team)]
    rows = []
    k = 0
    comps = {c.id: c for c in design.components}
    for wave in effort.waves:
        for w in wave:
            wp = next(x for x in design.work_packages if x.id == w)
            arch = {t.split(":", 1)[1] for c in wp.components for t in comps[c].tags if t.startswith("archetype:")}
            kinds = {comps[c].kind for c in wp.components}
            r = engineers[k % team]
            k += 1
            c = []
            if arch & _SECURITY_ARCH:
                c.append("Security reviewer")
            if kinds & _OPS_KINDS:
                c.append("Ops/SRE")
            rows.append([wp.id + " " + wp.title, r, "Tech lead", ", ".join(c) or "—", "Product owner"])
    return ("# RACI\n\nResponsible = the engineer who builds it (round-robin over the team in wave order; reassign freely), "
            "Accountable = tech lead, Consulted = security reviewer for packages with a security-relevant component and Ops/SRE for anything that runs "
            "or stores, Informed = product owner.\n\n" + _table(["work package", "R", "A", "C", "I"], rows))


# ---------------------------------------------------------------------------
# 7. SLOs
# ---------------------------------------------------------------------------


def _num(target: str) -> tuple[str, float | None]:
    m = re.search(r"(<=|>=|<|>|=)?\s*([\d.]+)", target)
    if not m:
        return "", None
    try:
        return (m.group(1) or ""), float(m.group(2))
    except ValueError:
        return (m.group(1) or ""), None


def _slo_target(m) -> str:
    unit = m.unit.strip()
    return m.target if not unit or unit in m.target else f"{m.target} {unit}"


def slos(design: Design) -> str:
    rows = []
    for r in design.requirements:
        if r.kind != "nonfunctional" or not r.metric or r.rationale.startswith("assumed"):
            continue
        m = r.metric
        low = r.statement.lower()
        is_avail = ("%" in m.target or m.unit.strip().startswith("%")) and re.search(r"availab|uptime|during|monthly|of the time|trading hours|business hours|稼働", low) is not None
        is_latency = "latency" in m.name
        is_loss = "lost" in m.name or "duplicate" in m.name
        if not (is_avail or is_latency or is_loss) or m.target == "review":
            continue          # rates, sizes, retention periods and "99.9 % of payments within 24 h" are not SLOs to page on
        cmp, val = _num(m.target)
        budget = ""
        pct = re.search(r"\bp(50|90|95|99|999)\b", m.name)
        p = "p" + pct.group(1) if pct else "p95"
        if is_avail and val is not None and 90 <= val < 100:
            window_min = 30 * 24 * 60
            note = ""
            hm = re.search(r"(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})", r.statement)
            if hm:
                hours = (int(hm.group(3)) * 60 + int(hm.group(4)) - int(hm.group(1)) * 60 - int(hm.group(2))) / 60
                if 0 < hours < 24:
                    days = 22 if re.search(r"trading|business|weekday|営業", low) else 30
                    window_min = int(hours * 60 * days)
                    note = f" (stated window {hm.group(0)}: {hours:g} h × {days} days)"
            minutes = (100 - val) / 100 * window_min
            budget = f"error budget {minutes:.2f} min / 30 days = (100 − {val:g}) % × {window_min:,} min{note}"
            alert = "page at 14.4× burn over 1 h and 6× over 6 h (multi-window burn rate)"
        elif is_latency and val is not None:
            unit = m.unit.strip() if m.unit.strip() not in m.target else ""
            shown = f"{val:g} {unit}".strip() if unit else m.target.lstrip("<=> ")
            share = {"p50": "50 %", "p90": "10 %", "p95": "5 %", "p99": "1 %", "p999": "0.1 %"}[p]
            budget = f"{share} of requests may exceed {shown} ({p})" if pct else f"target {M.metric_text(m)}"
            alert = f"alert when the 5-minute {p} exceeds {shown} for 10 minutes"
        elif is_loss and val is not None:
            budget = "zero tolerance: every occurrence is an incident"
            alert = "alert on the first occurrence"
        elif val is None:
            budget = "**target to agree** (quality statement without a number)"
            alert = "—"
        else:
            continue
        rows.append([r.id, m.name, _slo_target(m), budget, alert, r.statement[:120]])
    return ("# SLOs\n\nOne row per availability, latency or loss target stated in the text; rates, sizes and retention periods are capacity/compliance facts, not SLOs, and engine assumptions are never SLOs. "
            "Error budgets use a 30-day window (or the stated service window × 22 trading days). Burn-rate thresholds are the usual SRE defaults; tune after a month of data.\n\n"
            + (_table(["req", "SLI", "SLO", "budget", "alerting", "source"], rows) if rows else "No measurable quality requirement stated; agree SLOs before go-live.\n"))


# ---------------------------------------------------------------------------
# 8. Cost model (quantities and formulas; prices only from the reader)
# ---------------------------------------------------------------------------


@dataclass
class CostLine:
    item: str
    qty: float
    unit: str
    formula: str
    price_key: str
    price: float | None = None

    @property
    def monthly(self) -> float | None:
        return None if self.price is None else self.qty * self.price


def cost_lines(design: Design, notes, prices: dict[str, float] | None = None) -> list[CostLine]:
    prices = prices or {}
    lines: list[CostLine] = []
    services = [c for c in design.components if c.kind == "service"]
    jobs = [c for c in design.components if c.kind == "job"]
    redundancy = _decision(design, "redundancy")
    per_role = 2 if redundancy and redundancy.choice.startswith("Two or more") else 1
    if services:
        lines.append(CostLine("application instances (services)", per_role * len(services), "instance-month",
                              f"{per_role} per role (redundancy decision) × {len(services)} service components", "instance_month"))
    if jobs:
        lines.append(CostLine("worker/job instances", max(1, per_role - 1) * len(jobs), "instance-month",
                              f"{max(1, per_role - 1)} × {len(jobs)} job components", "instance_month"))
    stores = [c for c in design.components if c.kind == "datastore"]
    if stores:
        replicas = 1 + (1 if redundancy and per_role == 2 else 0)
        lines.append(CostLine("database instances", replicas, "db-month", f"1 primary + {replicas - 1} replica (redundancy decision)", "db_month"))
    growth = next((e for e in notes.capacity.estimates if e.name.startswith("storage growth per day")), None)
    if growth:
        m = re.match(r"([\d.]+)\s*([kMGT]?)B", growth.value)
        if m:
            mult = {"": 1, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}[m.group(2)]
            gb = float(m.group(1)) * mult * 30 / 1e9
            lines.append(CostLine("storage growth (30 days)", round(gb, 2), "GB-month", f"{growth.value}/day × 30 ({growth.formula})", "storage_gb_month"))
    if any(c.kind == "external" for c in design.components):
        for c in design.components:
            if c.kind == "external":
                lines.append(CostLine(f"external: {c.name}", 1, "contract", "usage-based; quote from the provider", "external_" + _slug(c.name).replace("-", "_")))
    for ln in lines:
        ln.price = prices.get(ln.price_key)
    return lines


def unknown_price_keys(lines: list[CostLine], prices: dict[str, float] | None) -> list[str]:
    return sorted(set(prices or {}) - {ln.price_key for ln in lines})


def cost_model(design: Design, notes, prices: dict[str, float] | None = None) -> str:
    lines = cost_lines(design, notes, prices)
    rows = [[ln.item, f"{ln.qty:g}", ln.unit, ln.formula, ln.price_key, "?" if ln.price is None else f"{ln.price:g}",
             "?" if ln.monthly is None else f"{ln.monthly:,.2f}"] for ln in lines]
    known = [ln.monthly for ln in lines if ln.monthly is not None]
    by_key: dict[str, float] = {}
    for ln in lines:
        if ln.price is None:
            by_key[ln.price_key] = by_key.get(ln.price_key, 0) + ln.qty
    unknown = list(by_key)
    total = " + ".join(([f"{sum(known):,.2f}"] if known else []) + [f"{q:g} × {k}" for k, q in by_key.items()]) or "0"
    s = ["# Cost model (monthly)\n",
         "Quantities come from the design (instances per role from the redundancy decision, one database per store, storage from the capacity estimate). "
         "Unit prices are **not** guessed: supply them with `--prices prices.json` (keys in the *price key* column), otherwise the column reads `?` and the total is a formula.\n",
         _table(["item", "qty", "unit", "how the quantity was derived", "price key", "unit price", "monthly"], rows),
         f"\n**Total per month: {total}**\n"]
    extra = unknown_price_keys(lines, prices)
    if extra:
        s.append(f"\n**Warning**: price keys not used by any line: {', '.join(extra)} (check the spelling against the *price key* column).\n")
    if unknown:
        s.append("\nExample prices file:\n\n```json\n" + json.dumps({k: 0 for k in sorted(set(unknown))}, indent=2) + "\n```\n")
    s.append("\nNot in this model: people (see the roadmap for person-days), egress, licences, and one-off migration work.\n")
    return "\n".join(s)


# ---------------------------------------------------------------------------
# 9. Runbooks
# ---------------------------------------------------------------------------


def runbooks(design: Design) -> str:
    s = ["# Runbooks\n", "One section per component that runs or stores. Steps are the standard ones for the component's kind; fill the command column when the code exists.\n"]
    alerting = next((r for r in design.requirements if "alert" in r.statement.lower()), None)
    backup = _decision(design, "backup")
    for c in design.components:
        if c.kind not in ("service", "job", "datastore"):
            continue
        s.append(f"## {c.id} {c.name} ({c.kind})\n")
        s.append(f"Responsibility: {c.responsibility}\n")
        rows = []
        if c.kind == "service":
            rows += [["health", "GET the readiness endpoint; expect 200 within 1 s", "readiness"],
                     ["restart", "rolling restart one instance at a time; watch error rate", "deploy tool"],
                     ["scale", "add an instance when p95 latency or CPU exceeds the SLO for 10 min", "autoscaler / manual"]]
        if c.kind == "job":
            rows += [["stuck", "check the last run time and queue depth; if late by > 2 intervals, run once by hand", "run_once"],
                     ["backlog", "raise worker count temporarily; confirm the depth falls", "scale"],
                     ["poison item", "inspect the dead-letter; fix or discard with a note", "dead-letter tool"]]
        if c.kind == "datastore":
            rows += [["disk", "alert at 80 % usage; extend or archive", "monitoring"],
                     ["slow queries", "list queries > 1 s; add the index the plan asks for", "slow query log"],
                     ["restore", backup.choice if backup else "**no backup decision in the design** — decide before go-live", "backup tool"]]
        rows.append(["alerts", alerting.statement if alerting else "no alerting requirement stated; decide thresholds", "alert rules"])
        s.append(_table(["situation", "what to do", "where"], rows))
    return "\n".join(s) + "\n"


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------


MANIFEST = ".sekkei-deliverables.json"


@dataclass
class Package:
    files: dict[str, str] = field(default_factory=dict)

    def write(self, out: Path) -> list[Path]:
        """Writes the package. Files written by an earlier `deliver` into the same directory (listed in its manifest)
        and not produced this time are removed, so a stale ADR never survives a re-run; files sekkei never wrote are left alone."""
        stale: list[str] = []
        manifest = out / MANIFEST
        if manifest.exists():
            try:
                old = json.loads(manifest.read_text(encoding="utf-8")).get("files", [])
            except (ValueError, OSError):
                old = []
            for name in old:
                if name not in self.files and (out / name).is_file():
                    (out / name).unlink()
                    stale.append(name)
        written = []
        for name, body in self.files.items():
            p = out / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
            written.append(p)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"files": sorted(self.files), "removed_stale": stale}, indent=1) + "\n", encoding="utf-8")
        self.removed_stale = stale
        return written


def package(result, prices: dict[str, float] | None = None) -> Package:
    """Everything, from an ``EngineResult``: the design and notes plus the consultant's documents."""
    from . import model as M
    d = result.design
    notes = result.notes
    pk = Package()
    pk.files["design.json"] = M.dumps(d)
    pk.files["DESIGN.md"] = RD.render_markdown(d)
    pk.files["NOTES.md"] = notes.to_markdown()
    pk.files["notes.json"] = json.dumps(notes.machine(), indent=2, ensure_ascii=False) + "\n"
    pk.files["00_EXECUTIVE_SUMMARY.md"] = executive_summary(d, notes)
    for name, body in adrs(d).items():
        pk.files["adr/" + name] = body
    pk.files["C4.md"] = c4_markdown(d, result.analysis.actors)
    pk.files["RISK_REGISTER.md"] = risk_register(d)
    pk.files["FMEA.md"] = fmea(d)
    pk.files["ROADMAP.md"] = roadmap(d, notes.effort)
    pk.files["RACI.md"] = raci(d, notes.effort)
    pk.files["SLO.md"] = slos(d)
    pk.files["COST_MODEL.md"] = cost_model(d, notes, prices)
    pk.files["RUNBOOKS.md"] = runbooks(d)
    pk.files["INDEX.md"] = index_markdown(pk, d)
    return pk


def index_markdown(pk: Package, design: Design) -> str:
    s = [f"# Deliverables — {design.name}\n", "Generated by `sekkei deliver`; every file is derived from `design.json` and the requirements, deterministically.\n",
         "| file | what it is |", "|---|---|"]
    what = {"00_EXECUTIVE_SUMMARY.md": "one page for the sponsor", "DESIGN.md": "the architecture (components, contracts, entities, flows, decisions, risks, work packages)",
            "NOTES.md": "architect's notes: open questions, assumptions, capacity, effort, threats", "C4.md": "context and container diagrams (Mermaid)",
            "RISK_REGISTER.md": "risks scored and owned", "FMEA.md": "failure modes and their effects from the dependency graph",
            "ROADMAP.md": "phases, calendar, milestones", "RACI.md": "who builds, approves, is consulted, is informed",
            "SLO.md": "service-level objectives and error budgets", "COST_MODEL.md": "monthly quantities and formulas (prices from you)",
            "RUNBOOKS.md": "operational procedures per running component", "design.json": "the machine-readable design (input to lint/plan/brief/check)",
            "notes.json": "the notes in machine-readable form: every estimate as expression + inputs + value, the effort DAG and waves"}
    for name in pk.files:
        if name.startswith("adr/"):
            continue
        s.append(f"| {name} | {what.get(name, '')} |")
    s.append(f"| adr/ | {sum(1 for n in pk.files if n.startswith('adr/'))} architecture decision records (MADR) |")
    return "\n".join(s) + "\n"
