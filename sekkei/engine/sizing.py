"""Capacity and effort estimates from the numbers in the text, with every assumption stated.

Formulas are the ones an architect writes on a whiteboard: Little's law for concurrency,
rate × size × time for storage, rate × outage for backlog, package sizes × team for the
calendar. Nothing here is precise; everything here is reproducible and labelled.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import graph as G
from ..model import Design
from .analysis import Analysis
from .text import interval_seconds
from .text import per_second as _per_second


_PER_REPORT_NOUNS = {"points", "values", "readings", "measurements", "samples", "metrics", "signals", "channels", "fields"}
_STANDARD_RE = re.compile(r"\b(?:iec|iso|rfc|ieee|din|en|ansi|itu|nist|fips|pci|ietf|jis|bs)[- ]?$", re.I)


def _is_population(q, an: Analysis) -> bool:
    """A count that can be divided by an interval: a population noun (users, devices, rtus, sites …), never a standard's
    number ('IEC 60870 specialist') and never a noun that appears once with a number that reads as an identifier."""
    if not q.noun:
        return False
    text = " ".join(u.sentence.text for u in an.requirements)
    i = text.find(q.raw)
    before = text[max(0, i - 8): i].strip() if i >= 0 else ""
    if _STANDARD_RE.search(before) or re.search(r"\b(?:version|v|no\.?|number|#)\s*$", before, re.I):
        return False
    if q.noun in POPULATION_NOUNS or q.noun.rstrip("s") in POPULATION_NOUNS:
        return True
    return q.value >= 100 and text.lower().count(q.noun.lower()) >= 2 and q.noun.endswith("s")


_GENERIC_NOUNS = {"system", "platform", "service", "data", "users", "time", "day", "days", "second", "seconds", "minute", "minutes", "hour", "hours"}


def _related(u, src_unit, q) -> bool:
    """The population sentence is the interval sentence, or the two share a specific noun (RTUs … 4,200 substations /
    Each RTU reports … every 4 seconds): a count from an unrelated sentence must not be divided by this interval."""
    if u.id == src_unit.id:
        return True
    a = {w.rstrip("s") for w in u.sentence.nouns} - _GENERIC_NOUNS
    b = {w.rstrip("s") for w in src_unit.sentence.nouns} - _GENERIC_NOUNS
    return q.noun.rstrip("s") in b or bool(a & b)


def implied_rate(an: Analysis) -> tuple[float, str] | None:
    """'2,000 online drivers ... every 5 seconds' -> 400/s with its derivation; None when not derivable."""
    interval = None
    src = ""
    per_report = 1.0
    per_txt = ""
    for u in an.requirements:
        secs = interval_seconds(u.sentence.text)
        if secs:
            interval, src = secs, u.id
            # "reports 40 analogue points and 24 digital points every 4 seconds": items per report multiply the rate
            per = [q for q in u.sentence.quantities if q.kind == "count" and q.noun in _PER_REPORT_NOUNS]
            if per:
                per_report = sum(q.value for q in per)
                per_txt = f" × {' + '.join(q.raw for q in per)} {per[0].noun} per report"
            break
    if not interval:
        return None
    src_unit = next(u for u in an.requirements if u.id == src)
    pops = [(q, u) for u in an.requirements for q in u.sentence.quantities if q.kind == "count" and _is_population(q, an)
            and _related(u, src_unit, q)]
    if not pops:
        return None
    q, u = max(pops, key=lambda t: t[0].value)
    return q.value * per_report / interval, f"{q.raw} {q.noun} ({u.id}){per_txt} ÷ every {interval:g} s ({src})"

def implied_inputs(an: Analysis) -> tuple[float, float, float]:
    """The (count, per-report items, interval seconds) behind ``implied_rate``; zeros when not derivable."""
    interval, per = None, 1.0
    for u in an.requirements:
        secs = interval_seconds(u.sentence.text)
        if secs:
            interval = secs
            per_q = [q for q in u.sentence.quantities if q.kind == "count" and q.noun in _PER_REPORT_NOUNS]
            per = sum(q.value for q in per_q) if per_q else 1.0
            break
    if not interval:
        return 0.0, 1.0, 0.0
    src_unit = next((u for u in an.requirements if interval_seconds(u.sentence.text)), None)
    pops = [q for u in an.requirements for q in u.sentence.quantities if q.kind == "count" and _is_population(q, an)
            and src_unit is not None and _related(u, src_unit, q)]
    return (max(q.value for q in pops) if pops else 0.0), per, interval


DEFAULT_PAYLOAD_BYTES = 2048
DEFAULT_SERVICE_MS = 200          # mean time of one outbound/handler call
DEFAULT_OUTAGE_HOURS = 1.0
SIZE_DAYS = G.SIZE_WEIGHT   # person-days per package size (assumption); one table with graph.critical_path
#: count nouns that denote a population worth dividing a rate by (not "5 attempts")
POPULATION_NOUNS = {"endpoints", "users", "tenants", "customers", "items", "records", "devices", "sensors", "clients",
                    "subscribers", "orders", "products", "accounts", "files", "warehouses", "stores", "sites", "nodes",
                    "services", "queues", "topics", "channels", "rows", "documents", "events", "messages", "jobs",
                    "rtus", "substations", "gateways", "loggers", "meters", "vehicles", "trucks", "drivers", "participants",
                    "patients", "players", "matches", "tickets", "claims", "policies", "greenhouses", "farms", "fields", "stations",
                    "terminals", "kiosks", "machines", "cameras", "turbines", "assets", "shipments", "parcels", "repos", "tests"}


@dataclass
class Estimate:
    name: str
    value: str
    formula: str
    inputs: str
    #: machine-readable form of the same estimate: an expression over named numeric inputs and the value it gives
    expr: str = ""
    terms: dict = field(default_factory=dict)
    number: float | None = None

    def machine(self) -> dict:
        return {"name": self.name, "value": self.number, "expr": self.expr, "inputs": self.terms, "shown": self.value, "formula": self.formula, "inputs_text": self.inputs}


@dataclass
class Capacity:
    estimates: list[Estimate] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def _fmt(n: float) -> str:
    def trim(x: str) -> str:
        return x.rstrip("0").rstrip(".") if "." in x else x

    if n >= 1e12:
        return trim(f"{n / 1e12:.2f}") + " T"
    if n >= 1e9:
        return trim(f"{n / 1e9:.2f}") + " G"
    if n >= 1e6:
        return trim(f"{n / 1e6:.2f}") + " M"
    if n >= 1e3:
        return trim(f"{n / 1e3:.1f}") + " k"
    return f"{n:.0f}" if n == int(n) else trim(f"{n:.2f}")


def capacity(an: Analysis) -> Capacity:
    cap = Capacity()
    qs = [(u, q) for u in an.requirements for q in u.sentence.quantities]
    rates = [(u, q, _per_second(q)) for u, q in qs if q.kind == "rate"]
    rates = [(u, q, r) for u, q, r in rates if r]
    # a peak/burst figure sizes concurrency, never storage or daily volume
    def is_peak(u, q):
        i = u.sentence.text.find(q.raw)
        before = u.sentence.text[max(0, i - 40):i].lower()
        after = u.sentence.text[i + len(q.raw):i + len(q.raw) + 60].lower()
        return bool(re.search(r"\bpeaks?\b|\bburst|\bspike|\bsurge|\bup to\b.{0,12}$", before)) or \
            bool(re.search(r"\bpeak|\bburst|\bspike|\bsurge|\bfor (?:a |the )?(?:few )?(?:\d+ )?(?:minutes?|seconds?|hours?)\b|\bin the (?:minute|hour|seconds?) after\b|\bat (?:the )?(?:london |market )?open\b|\bduring (?:a |the )?(?:goal|launch|event|sale)", after))
    # "20 operations per day per lock" × 40,000 locks: a per-unit rate is multiplied by the fleet when the fleet is stated
    def fleet_factor(u, q):
        i = u.sentence.text.find(q.raw)
        after = u.sentence.text[i + len(q.raw):i + len(q.raw) + 40].lower()
        m = re.search(r"\bper (?:\w+ )?([a-z]+)\b", after)
        if not m:
            return 1.0, ""
        noun = m.group(1)
        for u2 in an.requirements:
            for q2 in u2.sentence.quantities:
                if q2.kind == "count" and q2.noun and (q2.noun == noun or q2.noun.rstrip("s") == noun.rstrip("s")):
                    return q2.value, f" × {q2.raw} {q2.noun} ({u2.id})"
        return 1.0, ""
    peaks = [(u, q, r) for u, q, r in rates if is_peak(u, q)]
    rates = [(u, q, r) for u, q, r in rates if not is_peak(u, q)]
    scaled = []
    for u, q, r in rates:
        f, ftxt = fleet_factor(u, q)
        if f > 1:
            q.raw = q.raw + ftxt if ftxt not in q.raw else q.raw
        scaled.append((u, q, r * f))
    rates = scaled
    counts = [(u, q) for u, q in qs if q.kind == "count"]
    sizes = [(u, q) for u, q in qs if q.kind == "size"]
    latencies = [(u, q) for u, q in qs if q.kind == "latency"]
    durations = [(u, q) for u, q in qs if q.kind == "duration"]

    payload = DEFAULT_PAYLOAD_BYTES
    payload_src = f"assumed {DEFAULT_PAYLOAD_BYTES} bytes per record"
    for u, q in sizes:
        if any(w in u.sentence.lower for w in ("payload", "body", "record", "message", "event", "document")):
            mult = {"kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3, "tb": 1024 ** 4, "bytes": 1, "byte": 1}.get(q.unit.lower(), 1)
            payload, payload_src = q.value * mult, f"{q.raw} stated in {u.id}"
            break
    cap.assumptions.append(f"Record size: {payload_src}.")

    implied = implied_rate(an)
    if implied and not [r for r in rates if not r[0].sentence.assumed]:
        rate_val, derivation = implied
        n_pop, per, interval = implied_inputs(an)
        cap.estimates.append(Estimate("implied update rate", _fmt(rate_val) + "/s", "count × items per report ÷ interval", derivation,
                                      "count * per / interval", {"count": n_pop, "per": per, "interval": interval}, rate_val))
        cap.estimates.append(Estimate("implied updates per day", _fmt(rate_val * 86400), "implied rate × 86,400 s", derivation,
                                      "count * per / interval * 86400", {"count": n_pop, "per": per, "interval": interval}, rate_val * 86400))
        cap.estimates.append(Estimate("storage growth per day (updates)", _fmt(rate_val * 86400 * payload) + "B", "implied rate × 86,400 × record size", derivation + f"; {payload_src}",
                                      "count * per / interval * 86400 * payload", {"count": n_pop, "per": per, "interval": interval, "payload": payload}, rate_val * 86400 * payload))
    if not rates and not implied:
        cap.missing.append("no rate stated (events/s, requests/s); throughput, storage growth and backlog cannot be estimated")
    for u, q, r in rates[:2]:
        what = q.noun or "requests"
        base = {"rate": r}
        cap.estimates.append(Estimate(f"{what} per day", _fmt(r * 86400), "rate × 86,400 s", f"{q.raw} ({u.id})",
                                      "rate * 86400", base, r * 86400))
        cap.estimates.append(Estimate(f"storage growth per day ({what})", _fmt(r * 86400 * payload) + "B",
                                      "rate × 86,400 × record size", f"{q.raw} ({u.id}); {payload_src}",
                                      "rate * 86400 * payload", {**base, "payload": payload}, r * 86400 * payload))
        cap.estimates.append(Estimate(f"storage after 30 days ({what})", _fmt(r * 86400 * 30 * payload) + "B",
                                      "daily growth × 30", "same inputs; no retention stated" if not durations else "same inputs",
                                      "rate * 86400 * payload * 30", {**base, "payload": payload}, r * 86400 * 30 * payload))
        cap.estimates.append(Estimate(f"backlog after a {DEFAULT_OUTAGE_HOURS:g} h downstream outage", _fmt(r * 3600 * DEFAULT_OUTAGE_HOURS) + f" {what}",
                                      "rate × outage seconds", f"{q.raw} ({u.id}); outage length assumed",
                                      "rate * 3600 * outage_hours", {**base, "outage_hours": DEFAULT_OUTAGE_HOURS}, r * 3600 * DEFAULT_OUTAGE_HOURS))
        conc = r * DEFAULT_SERVICE_MS / 1000
        cap.estimates.append(Estimate(f"concurrent handlers to sustain the rate ({what})", _fmt(conc),
                                      "Little's law: rate × mean service time", f"{q.raw} ({u.id}); mean service time assumed {DEFAULT_SERVICE_MS} ms",
                                      "rate * service_ms / 1000", {**base, "service_ms": DEFAULT_SERVICE_MS}, conc))
        if "async_delivery" in an.patterns:
            for k in (1, 10):
                cap.estimates.append(Estimate(f"outbound deliveries per second if each event matches {k} target(s)", _fmt(r * k),
                                              "event rate × fan-out", f"{q.raw} ({u.id}); fan-out {k} assumed",
                                              "rate * fanout", {**base, "fanout": k}, r * k))
        for lu, lq in [x for x in latencies if x[1].value / (1000 if x[1].unit.lower().startswith("ms") else 1) <= 60][:1]:
            secs = lq.value / (1000 if lq.unit.lower().startswith("ms") else 1)
            cap.estimates.append(Estimate("in-flight items at the latency target", _fmt(r * secs),
                                          "rate × latency target (Little's law upper bound)", f"{q.raw} ({u.id}) × {lq.raw} ({lu.id})",
                                          "rate * latency_s", {**base, "latency_s": secs}, r * secs))
    for u, q, r in peaks[:1]:
        conc = r * DEFAULT_SERVICE_MS / 1000
        cap.estimates.append(Estimate(f"concurrent handlers at the stated peak ({q.noun or 'requests'})", _fmt(conc),
                                      "Little's law: peak rate × mean service time", f"{q.raw} ({u.id}); mean service time assumed {DEFAULT_SERVICE_MS} ms",
                                      "rate * service_ms / 1000", {"rate": r, "service_ms": DEFAULT_SERVICE_MS}, conc))
    populations = [(u, q) for u, q in counts if _is_population(q, an) and q.value > 0]
    for u, q in populations[:3]:
        cap.estimates.append(Estimate(f"number of {q.noun}", _fmt(q.value), "stated", f"{q.raw} {q.noun} ({u.id})", "count", {"count": q.value}, q.value))
        if rates:
            r = rates[0][2]
            cap.estimates.append(Estimate(f"average rate per {q.noun[:-1] if q.noun.endswith('s') else q.noun} (if evenly spread)",
                                          _fmt(r / q.value) + "/s", "rate ÷ count", f"{rates[0][1].raw} ÷ {q.raw}",
                                          "rate / count", {"rate": r, "count": q.value}, r / q.value))
    cap.assumptions.append(f"Mean service time {DEFAULT_SERVICE_MS} ms and a {DEFAULT_OUTAGE_HOURS:g} h outage are engine assumptions; replace with measurements.")
    return cap


@dataclass
class Effort:
    person_days: int
    critical_path_days: int
    calendar_days: int
    team: int
    waves: list[list[str]]
    assumptions: list[str]
    #: calendar length of each wave: max(longest package, ceil(person-days / team)); their sum is calendar_days
    phase_days: list[int] = field(default_factory=list)
    #: person-days of each package in each wave, in wave order (the inputs of phase_days)
    wave_days: list[list[int]] = field(default_factory=list)
    #: package -> (days, packages it depends on): the DAG behind critical_path_days
    tasks: dict = field(default_factory=dict)

    def machine(self) -> dict:
        return {"person_days": self.person_days, "critical_path_days": self.critical_path_days, "calendar_days": self.calendar_days,
                "team": self.team, "waves": self.waves, "phase_days": self.phase_days, "wave_days": self.wave_days, "tasks": self.tasks}


def effort(design: Design, an: Analysis) -> Effort:
    days = {w.id: SIZE_DAYS.get(w.size, 5) for w in design.work_packages}
    total = sum(days.values())
    g = G.package_graph(design)
    try:
        waves = G.waves(g)
    except ValueError:
        waves = [[w.id for w in design.work_packages]]   # a dependency cycle (lint C-rules report it); no critical path
    # critical path in days
    best: dict[str, int] = {}
    for wave in waves:
        for w in wave:
            best[w] = days[w] + max((best.get(d, 0) for d in g[w]), default=0)
    critical = max(best.values(), default=0)
    team = an.team_size if an.team_size and an.team_size > 0 else 2
    phase = [max(max((days[w] for w in wave), default=0), -(-sum(days[w] for w in wave) // team)) for wave in waves]
    calendar = sum(phase)
    return Effort(total, critical, calendar, team, waves,
                  [f"Package sizes S/M/L = {SIZE_DAYS['S']}/{SIZE_DAYS['M']}/{SIZE_DAYS['L']} person-days (assumption).",
                   f"Team of {team}" + ("" if an.team_size else " (assumed; no team size stated)") + "; packages in one wave run in parallel up to the team size; "
                   "a wave lasts max(longest package, person-days ÷ team) and waves run one after another."], phase,
                  [[days[w] for w in wave] for wave in waves],
                  {w.id: {"duration": days[w.id], "after": list(w.depends_on)} for w in design.work_packages})


def capacity_markdown(cap: Capacity) -> str:
    s = []
    if cap.estimates:
        s += ["| estimate | value | formula | inputs |", "|---|---|---|---|"]
        s += [f"| {e.name} | {e.value} | {e.formula} | {e.inputs} |" for e in cap.estimates]
        s.append("")
    for m in cap.missing:
        s.append(f"- Missing: {m}.")
    for a in cap.assumptions:
        s.append(f"- Assumption: {a}")
    return "\n".join(s) + "\n"


def effort_markdown(e: Effort) -> str:
    s = [f"- Total effort: **{e.person_days} person-days**; critical path **{e.critical_path_days} days**; "
         f"with a team of {e.team}: **about {e.calendar_days} working days** ({-(-e.calendar_days // 5)} weeks)."]
    s += [f"- Wave {n}: {', '.join(w)}" for n, w in enumerate(e.waves, 1)]
    s += [f"- Assumption: {a}" for a in e.assumptions]
    return "\n".join(s) + "\n"
