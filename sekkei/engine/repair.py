"""Lint the synthesised design and apply the few repairs synthesis may legitimately make."""
from __future__ import annotations

from .. import rules as R
from ..model import Design


def _surface(design: Design):
    for kind in ("service", "cli", "module"):
        for c in design.components:
            if c.kind == kind:
                return c
    return design.components[0] if design.components else None


def repair(design: Design, max_passes: int = 4) -> tuple[Design, list[R.Diagnostic], list[str]]:
    """Return (design, remaining diagnostics, log of repairs applied)."""
    log: list[str] = []
    for _ in range(max_passes):
        diags = R.lint(design)
        changed = False
        for d in diags:
            if d.rule == "V001" and design.requirement(d.where) is not None:
                s = _surface(design)
                if s is not None and d.where not in s.satisfies:
                    s.satisfies.append(d.where)
                    log.append(f"V001: attached {d.where} to {s.id} (no pattern claimed it)")
                    changed = True
            elif d.rule == "V002" and design.requirement(d.where) is not None:
                r = design.requirement(d.where)
                comps = [c.id for c in design.components if d.where in c.satisfies]
                for wp in design.work_packages:
                    if set(wp.components) & set(comps) and d.where not in wp.satisfies:
                        wp.satisfies.append(d.where)
                        log.append(f"V002: {wp.id} now delivers {d.where}")
                        changed = True
                        break
                else:
                    if design.work_packages and r is not None:
                        design.work_packages[-1].satisfies.append(d.where)
                        log.append(f"V002: {design.work_packages[-1].id} delivers {d.where} (last package)")
                        changed = True
            elif d.rule == "C007":
                wp = design.work_package(d.where)
                target = d.message.split("implemented by ")[1].split(",")[0] if "implemented by " in d.message else ""
                if wp is not None and target and target not in wp.depends_on:
                    wp.depends_on.append(target)
                    log.append(f"C007: {wp.id} now depends on {target}")
                    changed = True
            elif d.rule == "V009":
                c = design.component(d.where)
                if c is not None and design.requirements:
                    # a component no requirement names: attach the constraint/quality requirement closest to its layer
                    fallback = next((r.id for r in design.requirements if r.kind == "constraint"), design.requirements[0].id)
                    c.satisfies.append(fallback)
                    log.append(f"V009: {c.id} attached to {fallback} (infrastructure component)")
                    changed = True
        if not changed:
            break
    return design, R.lint(design), log
