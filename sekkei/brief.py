"""Self-contained work-package briefs for implementing agents.

A brief contains exactly what one agent needs for one package — contracts to implement,
contracts to consume, write scope, conventions, acceptance checks, and the report it must
return — and nothing else. It is generated from the design, never edited by hand.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from . import model as M
from .model import Design, Interface
from .render import interface_table
from .state import State, report_template


def _bullets(items: list[str]) -> list[str]:
    return [f"- {x}" for x in items] if items else ["- (none)"]


def brief_fingerprint(design: Design, wp_id: str) -> str:
    """Hash of everything in a package's brief that comes from the design (statuses excluded).

    Recorded in the state when a brief is issued; if it differs later, the brief is stale
    and ``sekkei accept`` refuses the completion report unless forced.
    """
    return hashlib.sha256(render_brief(design, wp_id, None).encode("utf-8")).hexdigest()[:16]


def render_brief(design: Design, wp_id: str, state: Optional[State] = None) -> str:
    d = design
    wp = d.work_package(wp_id)
    if wp is None:
        raise KeyError(f"unknown work package {wp_id!r}")
    s: list[str] = []
    s.append(f"# Work package {wp.id} — {wp.title}\n")
    s.append(f"Project: **{d.name}** (design v{d.version}). Size: {wp.size}.\n")

    # 1. goal + requirements verbatim
    s.append("## 1. Goal\n")
    s.append((wp.goal or wp.title) + "\n")
    reqs = [r for r in d.requirements if r.id in wp.satisfies]
    if reqs:
        s.append("This package must satisfy the following requirements, quoted verbatim:\n")
        for r in reqs:
            m = f" _(metric: {M.metric_text(r.metric)})_" if r.metric else ""
            s.append(f"- **{r.id}** ({r.kind}, {r.priority}): {r.statement}{m}")
        s.append("")

    # 2. build
    s.append("## 2. Build\n")
    comps = [c for c in d.components if c.id in wp.components]
    for c in comps:
        path = f" at `{c.path}`" if c.path else ""
        s.append(f"- **{c.id} {c.name}** ({c.kind}){path}: {c.responsibility}")
    if not comps:
        s.append("- (no components listed)")
    s.append("")

    # 3. implement
    s.append("## 3. Implement these interfaces\n")
    impl = [i for i in d.interfaces if i.id in wp.implements]
    if impl:
        for i in impl:
            s.append(f"### {i.id} — {i.name} ({i.kind}, owner {i.owner})\n")
            if i.description:
                s.append(i.description + "\n")
            s.append(interface_table(i))
    else:
        s.append("(none)\n")

    # 4. use, do not modify
    s.append("## 4. Use, do not modify\n")
    consumed: dict[str, Interface] = {}
    for c in comps:
        for iid in c.requires:
            iface = d.interface(iid)
            if iface is not None and iface.id not in wp.implements:
                consumed[iface.id] = iface
    if consumed:
        s.append("Your components call these interfaces. Code against the contract below; do not change them.\n")
        for i in consumed.values():
            builders = [w.id for w in d.packages_implementing(i.id)]
            status = ""
            if state is not None and builders:
                status = " · status: " + ", ".join(f"{b}={state.status(b)}" for b in builders)
            s.append(f"### {i.id} — {i.name} ({i.kind}, owner {i.owner}, built by {', '.join(builders) or '?'}{status})\n")
            s.append(interface_table(i))
    else:
        s.append("(this package consumes no other interface)\n")

    # entities owned by these components
    ents = [e for e in d.entities if e.owner in wp.components]
    if ents:
        s.append("## 4b. Entities you own\n")
        for e in ents:
            s.append(f"### {e.id} — {e.name}\n")
            s.append("| field | type | constraints |\n|---|---|---|")
            s.extend(f"| `{f.name}` | {f.type} | {f.constraints} |" for f in e.fields)
            s.append("")

    # 5. scope
    s.append("## 5. Write scope\n")
    s.append("You may create or modify only these paths. Anything else is out of bounds; if you need to touch\n"
             "another file, stop and report it as a deviation.\n")
    s.extend(f"- `{f}`" for f in wp.files)
    s.append("")

    # 6. conventions
    cv = d.conventions
    s.append("## 6. Conventions\n")
    conv: list[str] = []
    if cv.language:
        conv.append(f"Language: {cv.language}")
    if cv.test_command:
        conv.append(f"Run tests with: `{cv.test_command}`")
    if cv.lint_command:
        conv.append(f"Run lint with: `{cv.lint_command}`")
    conv.extend(cv.rules)
    s.extend(_bullets(conv))
    if cv.definition_of_done:
        s.append("\nDefinition of done:\n")
        s.extend(f"- {x}" for x in cv.definition_of_done)
    s.append("")

    # decisions affecting these components
    decs = [x for x in d.decisions if set(x.affects) & (set(wp.components) | set(wp.implements))]
    if decs:
        s.append("## 6b. Decisions that bind you\n")
        for x in decs:
            s.append(f"- **{x.id} {x.title}**: {x.choice or '(no choice recorded)'}" + (f" — {x.rationale}" if x.rationale else ""))
        s.append("")

    # 7. acceptance
    s.append("## 7. Acceptance\n")
    s.append("The package is done only when every check below passes.\n")
    for a in wp.acceptance:
        extra = f" — run `{a.command}`" if a.command else (f" — report the measured value against {a.metric}" if a.metric else "")
        s.append(f"- **{a.id}** ({a.kind}): {a.description}{extra}")
    s.append("")

    # 8. dependencies
    s.append("## 8. Dependencies\n")
    if wp.depends_on:
        for dep in wp.depends_on:
            st = f" — {state.status(dep)}" if state is not None else ""
            other = d.work_package(dep)
            s.append(f"- {dep}{f' {other.title}' if other else ''}{st}")
    else:
        s.append("- (none; this package can start now)")
    s.append("")
    if wp.notes:
        s.append("## Notes\n")
        s.append(wp.notes + "\n")

    # 9. report
    s.append("## 9. Report back\n")
    s.append("When finished, return this JSON (fill every field; `output` is the tail of the check's output).\n"
             "It is validated by `sekkei accept`; a package is not done until the report is accepted.\n")
    s.append("```json\n" + json.dumps(report_template(d, wp.id), indent=2) + "\n```\n")
    s.append("Rules of engagement: implement exactly the contracts above; do not widen the scope; if the design is\n"
             "wrong, say so in `deviations` rather than silently working around it.")
    return "\n".join(s).rstrip() + "\n"
