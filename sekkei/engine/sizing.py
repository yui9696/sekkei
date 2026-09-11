"""Capacity and effort estimates from the numbers in the text, with every assumption stated.

Formulas are the ones an architect writes on a whiteboard: Little's law for concurrency,
rate × size × time for storage, rate × outage for backlog, package sizes × team for the
calendar. Nothing here is precise; everything here is reproducible and labelled.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import graph as G
from ..model import Design
from .analysis import Analysis
from .text import interval_seconds
from .text import per_second as _per_second


def implied_rate(an: Analysis) -> tuple[float, str] | None:
    """'2,000 online drivers ... every 5 seconds' -> 400/s with its derivation; None when not derivable."""
    interval = None
    src = ""
    for u in an.requirements:
        secs = interval_seconds(u.sentence.text)
        if secs:
            interval, src = secs, u.id
            break
    if not interval:
        return None
    pops = [(q, u) for u in an.requirements for q in u.sentence.quantities if q.kind == "count" and (q.value >= 100 or q.noun in POPULATION_NOUNS or q.noun in ("drivers", "trucks", "devices", "sensors", "vehicles"))]
    if not pops:
        return None
    q, u = max(pops, key=lambda t: t[0].value)
    return q.value / interval, f"{q.raw} {q.noun} ({u.id}) ÷ every {interval:g} s ({src})"

DEFAULT_PAYLOAD_BYTES = 2048
DEFAULT_SERVICE_MS = 200          # mean time of one outbound/handler call
DEFAULT_OUTAGE_HOURS = 1.0
SIZE_DAYS = {"S": 2, "M": 5, "L": 10}   # person-days per package size (assumption)
#: count nouns that denote a population worth dividing a rate by (not "5 attempts")
POPULATION_NOUNS = {"endpoints", "users", "tenants", "customers", "items", "records", "devices", "sensors", "clients",
                    "subscribers", "orders", "products", "accounts", "files", "warehouses", "stores", "sites", "nodes",
                    "services", "queues", "topics", "channels", "rows", "documents", "events", "messages", "jobs"}


@dataclass
class Estimate:
    name: str
    value: str
    formula: str
    inputs: str


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
        cap.estimates.append(Estimate("implied update rate", _fmt(rate_val) + "/s", "count ÷ interval", derivation))
        cap.estimates.append(Estimate("implied updates per day", _fmt(rate_val * 86400), "implied rate × 86,400 s", derivation))
        cap.estimates.append(Estimate("storage growth per day (updates)", _fmt(rate_val * 86400 * payload) + "B", "implied rate × 86,400 × record size", derivation + f"; {payload_src}"))
    if not rates and not implied:
        cap.missing.append("no rate stated (events/s, requests/s); throughput, storage growth and backlog cannot be estimated")
    for u, q, r in rates[:2]:
        what = q.noun or "requests"
        cap.estimates.append(Estimate(f"{what} per day", _fmt(r * 86400), "rate × 86,400 s", f"{q.raw} ({u.id})"))
        cap.estimates.append(Estimate(f"storage growth per day ({what})", _fmt(r * 86400 * payload) + "B",
                                      "rate × 86,400 × record size", f"{q.raw} ({u.id}); {payload_src}"))
        cap.estimates.append(Estimate(f"storage after 30 days ({what})", _fmt(r * 86400 * 30 * payload) + "B",
                                      "daily growth × 30", "same inputs; no retention stated" if not durations else "same inputs"))
        cap.estimates.append(Estimate(f"backlog after a {DEFAULT_OUTAGE_HOURS:g} h downstream outage", _fmt(r * 3600 * DEFAULT_OUTAGE_HOURS) + f" {what}",
                                      "rate × outage seconds", f"{q.raw} ({u.id}); outage length assumed"))
        conc = r * DEFAULT_SERVICE_MS / 1000
        cap.estimates.append(Estimate(f"concurrent handlers to sustain the rate ({what})", _fmt(conc),
                                      "Little's law: rate × mean service time", f"{q.raw} ({u.id}); mean service time assumed {DEFAULT_SERVICE_MS} ms"))
        if "async_delivery" in an.patterns:
            for k in (1, 10):
                cap.estimates.append(Estimate(f"outbound deliveries per second if each event matches {k} target(s)", _fmt(r * k),
                                              "event rate × fan-out", f"{q.raw} ({u.id}); fan-out {k} assumed"))
        for lu, lq in latencies[:1]:
            secs = lq.value / (1000 if lq.unit.lower().startswith("ms") else 1)
            cap.estimates.append(Estimate("in-flight items at the latency target", _fmt(r * secs),
                                          "rate × latency target (Little's law upper bound)", f"{q.raw} ({u.id}) × {lq.raw} ({lu.id})"))
    populations = [(u, q) for u, q in counts if q.value >= 100 or q.noun in POPULATION_NOUNS]
    for u, q in populations[:3]:
        cap.estimates.append(Estimate(f"number of {q.noun}", _fmt(q.value), "stated", f"{q.raw} {q.noun} ({u.id})"))
        if rates:
            r = rates[0][2]
            cap.estimates.append(Estimate(f"average rate per {q.noun[:-1] if q.noun.endswith('s') else q.noun} (if evenly spread)",
                                          _fmt(r / q.value) + "/s", "rate ÷ count", f"{rates[0][1].raw} ÷ {q.raw}"))
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


def effort(design: Design, an: Analysis) -> Effort:
    days = {w.id: SIZE_DAYS.get(w.size, 5) for w in design.work_packages}
    total = sum(days.values())
    g = G.package_graph(design)
    try:
        waves = G.waves(g)
    except ValueError:
        waves = [[w.id for w in design.work_packages]]
    # critical path in days
    best: dict[str, int] = {}
    for wave in waves:
        for w in wave:
            best[w] = days[w] + max((best[d] for d in g[w]), default=0)
    critical = max(best.values(), default=0)
    team = an.team_size or 2
    calendar = max(critical, -(-total // team))
    return Effort(total, critical, calendar, team, waves,
                  [f"Package sizes S/M/L = {SIZE_DAYS['S']}/{SIZE_DAYS['M']}/{SIZE_DAYS['L']} person-days (assumption).",
                   f"Team of {team}" + ("" if an.team_size else " (assumed; no team size stated)") + "; packages in one wave run in parallel up to the team size."])


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
