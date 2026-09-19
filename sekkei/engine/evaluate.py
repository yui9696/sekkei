"""Decision scoring (ATAM-style utility) and the architecture review the engine writes about itself."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Design
from . import catalog as K
from .analysis import Analysis


@dataclass
class Scored:
    option: K.Option
    score: float
    available: bool
    reason: str


def score_option(opt: K.Option, qualities: dict[str, float], constraints: set[str], rate: float = 0.0,
                 stated: set[str] | None = None) -> Scored:
    """utility = Σ_q w_q · fit_o(q); unavailable if a needed constraint token is absent or an excluded one present;
    an option with a rate ceiling below the stated rate is unavailable. The "stated in the constraints" bonus counts
    only tokens the author wrote (``stated``), never ones the engine's own assumed answers introduced."""
    if opt.max_rate and rate > opt.max_rate:
        return Scored(opt, -1.0, False, f"stated rate {rate:,.0f}/s exceeds this option's ceiling of {opt.max_rate:,.0f}/s")
    if opt.needs and not any(n in constraints for n in opt.needs):
        return Scored(opt, -1.0, False, f"needs {' or '.join(opt.needs)}, not in the constraints")
    hit = [x for x in opt.excludes if x in (stated if stated is not None else constraints)]
    if hit:
        return Scored(opt, -1.0, False, f"ruled out by {', '.join(hit)}")
    weights = qualities or {"simplicity": 0.5}
    score = sum(w * opt.fit.get(q, 1) for q, w in weights.items())
    total = sum(weights.values()) or 1.0
    bonus_pool = stated if stated is not None else constraints
    bonus = 1.0 if any(b in bonus_pool for b in opt.bonus_when) else 0.0
    return Scored(opt, round(score / total + bonus, 3), True, "stated in the constraints" if bonus else "")


def decide(dp: K.DecisionPoint, qualities: dict[str, float], constraints: set[str],
           forced: str | None = None, rate: float = 0.0, stated: set[str] | None = None) -> tuple[Scored, list[Scored], str, str]:
    """Score the options; ``forced`` (an option name or a unique prefix/substring) overrides the winner;
    ``rate`` is the stated peak rate per second (0 when unknown)."""
    ranked = sorted((score_option(o, qualities, constraints, rate, stated) for o in dp.options),
                    key=lambda s: (-s.available, -s.score, dp.options.index(s.option)))
    best = ranked[0]
    if not best.available:  # every option unavailable: fall back to catalogue order but say so
        best = Scored(dp.options[0], 0.0, True, "no option satisfied the constraints; catalogue default taken")
    if forced:
        hit = next((s for s in ranked if s.option.name.lower().startswith(forced.lower()) or forced.lower() in s.option.name.lower()), None)
        if hit is not None:
            best = Scored(hit.option, hit.score, True, "chosen in the interview")
    drivers = sorted(qualities.items(), key=lambda kv: -kv[1])[:2]
    driver_txt = ", ".join(f"{q} (weight {w})" for q, w in drivers) or "simplicity (no qualities stated)"
    rationale = (f"Scored against the active qualities; decided by {driver_txt}. "
                 + "; ".join(f"{s.option.name.split(' (')[0].split(';')[0][:48]}: "
                             + (f"{s.score:.2f}" if s.available else f"unavailable ({s.reason})") for s in ranked))
    losers = [s for s in ranked if s.option is not best.option and s.available]
    consequences = " ".join(f"Not choosing '{s.option.name.split(' (')[0][:48]}' gives up: {', '.join(s.option.pros[:2])}." for s in losers[:2])
    if best.reason:
        rationale += ". " + best.reason
    return best, ranked, rationale, consequences


@dataclass
class Review:
    unrecognised: list[tuple[str, str]] = field(default_factory=list)      # (req id, text)
    unaddressed: list[tuple[str, str]] = field(default_factory=list)       # (quality, why)
    assumptions: list[str] = field(default_factory=list)
    generic: list[str] = field(default_factory=list)                       # component ids from the fallback
    decisions: list[tuple[str, str, str]] = field(default_factory=list)    # (id, title, choice)
    notes: list[str] = field(default_factory=list)

    @property
    def needs_human(self) -> bool:
        return bool(self.unrecognised or self.unaddressed or self.generic)

    def to_markdown(self) -> str:
        s = ["# Architecture review (engine)\n"]
        s.append("What the engine could not do on its own, in order of importance.\n")
        if self.unrecognised:
            s.append("## Requirements the catalogue did not recognise\n")
            s.append("These are kept as requirements and assigned to the generic core/surface; refine their components and interfaces.\n")
            s.extend(f"- **{rid}**: {txt}" for rid, txt in self.unrecognised)
            s.append("")
        if self.unaddressed:
            s.append("## Quality attributes without a specific tactic\n")
            s.extend(f"- **{q}**: {why}" for q, why in self.unaddressed)
            s.append("")
        if self.generic:
            s.append("## Generic components\n")
            s.append("Produced by the layered fallback, not by a recognised pattern: " + ", ".join(self.generic) + "\n")
        if self.assumptions:
            s.append("## Assumptions made\n")
            s.extend(f"- {a}" for a in self.assumptions)
            s.append("")
        if self.decisions:
            s.append("## Decisions taken (scored trade-offs)\n")
            s.extend(f"- {did} {title}: **{choice}**" for did, title, choice in self.decisions)
            s.append("")
        if self.notes:
            s.append("## Notes\n")
            s.extend(f"- {n}" for n in self.notes)
            s.append("")
        if not self.needs_human:
            s.append("Every requirement was recognised and every active quality has a tactic. Review the decisions above; they are the judgement calls.\n")
        return "\n".join(s).rstrip() + "\n"


_TACTIC_KEYS = {t.quality: t for t in K.TACTICS}


def review(design: Design, an: Analysis, generic_components: list[str]) -> Review:
    rv = Review()
    rv.unrecognised = [(u.id, u.sentence.text) for u in an.unrecognised]
    rv.assumptions = list(an.assumptions)
    rv.generic = list(generic_components)
    rv.decisions = [(d.id, d.title, d.choice) for d in design.decisions]
    active_decisions = {d.title for d in design.decisions}
    comp_names = {c.name for c in design.components}
    for q, w in sorted(an.qualities.items(), key=lambda kv: -kv[1]):
        t = _TACTIC_KEYS[q]
        has_arch = any(K.ARCHETYPES[a].name in comp_names for a in t.archetypes)
        has_dec = any(K.DECISIONS[d].title in active_decisions for d in t.decisions)
        has_acc = any(a.kind == "metric" and (design.requirement(a.metric) is not None)
                      for wp in design.work_packages for a in wp.acceptance) if t.acceptance else False
        if not (has_arch or has_dec or has_acc or t.convention):
            rv.unaddressed.append((q, f"signals present (weight {w}) but the catalogue has no component, decision or check for it"))
        elif q == "availability" and not has_dec:
            rv.unaddressed.append((q, "no redundancy decision applies (no service component); decide instance count and health-based restart explicitly"))
    if an.team_size and len([c for c in design.components if c.kind != "external"]) > 4 * an.team_size:
        rv.notes.append(f"{len(design.components)} components for a team of {an.team_size}; consider merging adjacent layers.")
    nf = [u for u in an.requirements if u.kind == "nonfunctional" and u.metric and u.metric[1] == "review"]
    for u in nf:
        rv.notes.append(f"{u.id} is a quality statement without a number; agree a target before accepting the metric check.")
    return rv
