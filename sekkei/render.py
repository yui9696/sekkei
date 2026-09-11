"""Render a design as a Markdown document, plus Mermaid/DOT graphs and the traceability matrix."""
from __future__ import annotations

from . import graph as G
from .model import Design, Interface


def _esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def _list(items: list[str], empty: str = "—") -> str:
    return ", ".join(items) if items else empty


def interface_table(iface: Interface) -> str:
    if not iface.operations:
        return "_(no operations declared)_\n"
    lines = ["| operation | inputs | output | errors | pre / post |", "|---|---|---|---|---|"]
    for o in iface.operations:
        ins = ", ".join(f"`{p.name}`" + (f": {p.type}" if p.type else "") for p in o.inputs) or "—"
        prepost = " / ".join(x for x in (o.pre, o.post) if x) or "—"
        lines.append(
            f"| `{_esc(o.name)}` | {_esc(ins)} | {_esc(o.output) or '—'} | {_esc(_list(o.errors))} | {_esc(prepost)} |"
        )
        if o.description:
            lines.append(f"| | {_esc(o.description)} | | | |")
    return "\n".join(lines) + "\n"


def mermaid(design: Design, which: str = "components") -> str:
    out = ["graph LR"]
    if which == "components":
        for c in design.components:
            label = c.name.replace('"', "'")
            shape = ("[(", ")]") if c.kind == "datastore" else ("[[", "]]") if c.kind == "external" else ("[", "]")
            out.append(f'  {_mid(c.id)}{shape[0]}"{c.id} {label}"{shape[1]}')
        owner = {i.id: i.owner for i in design.interfaces}
        for c in design.components:
            for i in c.requires:
                b = owner.get(i)
                if b and b != c.id:
                    out.append(f"  {_mid(c.id)} -->|{i}| {_mid(b)}")
    else:
        for w in design.work_packages:
            label = w.title.replace('"', "'")
            out.append(f'  {_mid(w.id)}["{w.id} {label} ({w.size})"]')
        for w in design.work_packages:
            for d in w.depends_on:
                out.append(f"  {_mid(d)} --> {_mid(w.id)}")
    return "\n".join(out) + "\n"


def sequence(design: Design, flow_id: str) -> str:
    """A flow as a Mermaid sequence diagram (participants are the components it touches)."""
    f = next((x for x in design.flows if x.id == flow_id), None)
    if f is None:
        raise KeyError(flow_id)
    out = ["sequenceDiagram"]
    seen: list[str] = []
    for st in f.steps:
        for c in (st.from_, st.to):
            if c not in seen:
                seen.append(c)
    for c in seen:
        comp = design.component(c)
        label = (comp.name if comp else c).replace('"', "'")
        out.append(f"  participant {_mid(c)} as {c} {label}")
    if f.trigger:
        out.append(f"  Note over {_mid(seen[0])}: {f.trigger.replace(':', ' -')}")
    for st in f.steps:
        desc = (st.description or st.via).replace(":", " -")
        out.append(f"  {_mid(st.from_)}->>{_mid(st.to)}: {st.via} {desc}")
    return "\n".join(out) + "\n"


def dot(design: Design, which: str = "components") -> str:
    out = ["digraph G {", "  rankdir=LR;", "  node [shape=box];"]
    if which == "components":
        for c in design.components:
            out.append(f'  "{c.id}" [label="{c.id}\\n{c.name}"];')
        owner = {i.id: i.owner for i in design.interfaces}
        for c in design.components:
            for i in c.requires:
                b = owner.get(i)
                if b and b != c.id:
                    out.append(f'  "{c.id}" -> "{b}" [label="{i}"];')
    else:
        for w in design.work_packages:
            out.append(f'  "{w.id}" [label="{w.id}\\n{w.title}"];')
        for w in design.work_packages:
            for d in w.depends_on:
                out.append(f'  "{d}" -> "{w.id}";')
    out.append("}")
    return "\n".join(out) + "\n"


def _mid(id_: str) -> str:
    return id_.replace("-", "_").replace(".", "_")


def traceability_markdown(design: Design) -> str:
    tr = G.traceability(design)
    lines = ["| requirement | priority | components | work packages | acceptance |", "|---|---|---|---|---|"]
    for r in design.requirements:
        t = tr[r.id]
        lines.append(
            f"| {r.id} | {r.priority} | {_list(t['components'])} | {_list(t['packages'])} | {_list(t['acceptance'])} |"
        )
    return "\n".join(lines) + "\n"


def render_markdown(design: Design) -> str:
    d = design
    s: list[str] = []
    s.append(f"# {d.name} — design\n")
    if d.summary:
        s.append(d.summary + "\n")
    s.append(f"_version {d.version} · schema sekkei/{d.schema_version}_\n")

    if d.goals or d.non_goals:
        s.append("## Goals\n")
        s.extend(f"- {g}" for g in d.goals)
        if d.non_goals:
            s.append("\n**Non-goals**\n")
            s.extend(f"- {g}" for g in d.non_goals)
        s.append("")

    s.append("## Requirements\n")
    s.append("| id | kind | priority | statement | metric |")
    s.append("|---|---|---|---|---|")
    for r in d.requirements:
        m = f"{r.metric.name} {r.metric.target} {r.metric.unit}".strip() if r.metric else "—"
        s.append(f"| {r.id} | {r.kind} | {r.priority} | {_esc(r.statement)} | {_esc(m)} |")
    s.append("")

    s.append("## Components\n")
    s.append("```mermaid\n" + mermaid(d, "components") + "```\n")
    for c in d.components:
        s.append(f"### {c.id} — {c.name}\n")
        s.append(f"- **kind**: {c.kind}" + (f" · **path**: `{c.path}`" if c.path else ""))
        s.append(f"- **responsibility**: {c.responsibility}")
        s.append(f"- **provides**: {_list([i.id for i in d.provided_by(c.id)])}")
        s.append(f"- **requires**: {_list(c.requires)}")
        s.append(f"- **satisfies**: {_list(c.satisfies)}")
        s.append("")
    try:
        ls = G.layers(d)
        s.append("**Layers** (each layer depends only on earlier ones):\n")
        s.extend(f"{n}. {', '.join(layer)}" for n, layer in enumerate(ls))
        s.append("")
    except ValueError as exc:
        s.append(f"_Layers not computable: {exc}_\n")

    if d.interfaces:
        s.append("## Interfaces\n")
        for i in d.interfaces:
            s.append(f"### {i.id} — {i.name}\n")
            s.append(f"- **kind**: {i.kind} · **owner**: {i.owner} · **stability**: {i.stability}")
            if i.description:
                s.append(f"- {i.description}")
            s.append("")
            s.append(interface_table(i))

    if d.entities:
        s.append("## Entities\n")
        for e in d.entities:
            s.append(f"### {e.id} — {e.name} (owner {e.owner})\n")
            if e.description:
                s.append(e.description + "\n")
            s.append("| field | type | constraints |")
            s.append("|---|---|---|")
            for f in e.fields:
                s.append(f"| `{f.name}` | {_esc(f.type)} | {_esc(f.constraints)} |")
            s.append("")

    if d.flows:
        s.append("## Flows\n")
        for f in d.flows:
            s.append(f"### {f.id} — {f.name}\n")
            if f.trigger:
                s.append(f"_Trigger:_ {f.trigger}\n")
            for n, st in enumerate(f.steps, 1):
                s.append(f"{n}. {st.from_} → {st.to} via {st.via}" + (f": {st.description}" if st.description else ""))
            s.append("")
            s.append("```mermaid\n" + sequence(d, f.id) + "```\n")

    if d.decisions:
        s.append("## Decisions\n")
        for dec in d.decisions:
            s.append(f"### {dec.id} — {dec.title} ({dec.status})\n")
            if dec.context:
                s.append(f"**Context.** {dec.context}\n")
            for o in dec.options:
                mark = "✔" if o.name == dec.choice else "✘"
                s.append(f"- {mark} **{o.name}**")
                s.extend(f"  - + {p}" for p in o.pros)
                s.extend(f"  - − {c}" for c in o.cons)
            if dec.rationale:
                s.append(f"\n**Rationale.** {dec.rationale}")
            if dec.consequences:
                s.append(f"\n**Consequences.** {dec.consequences}")
            if dec.affects:
                s.append(f"\n_Affects:_ {_list(dec.affects)}")
            s.append("")

    if d.risks:
        s.append("## Risks\n")
        s.append("| id | risk | likelihood | impact | mitigation |")
        s.append("|---|---|---|---|---|")
        for k in d.risks:
            s.append(f"| {k.id} | {_esc(k.description)} | {k.likelihood} | {k.impact} | {_esc(k.mitigation)} |")
        s.append("")

    s.append("## Work packages\n")
    s.append("```mermaid\n" + mermaid(d, "packages") + "```\n")
    try:
        ws = G.waves(G.package_graph(d))
        s.append("**Waves** (packages in one wave may run in parallel):\n")
        s.extend(f"{n + 1}. {', '.join(w)}" for n, w in enumerate(ws))
        weight, path = G.critical_path(d)
        s.append(f"\n_Critical path (weight {weight}):_ {' → '.join(path)}\n")
    except ValueError as exc:
        s.append(f"_Plan not computable: {exc}_\n")
    for w in d.work_packages:
        s.append(f"### {w.id} — {w.title} ({w.size})\n")
        if w.goal:
            s.append(w.goal + "\n")
        s.append(f"- **components**: {_list(w.components)} · **implements**: {_list(w.implements)}")
        s.append(f"- **depends on**: {_list(w.depends_on)} · **satisfies**: {_list(w.satisfies)}")
        s.append(f"- **write scope**: {_list([f'`{f}`' for f in w.files])}")
        s.append("- **acceptance**:")
        for a in w.acceptance:
            cmd = f" — `{a.command}`" if a.command else (f" — metric {a.metric}" if a.metric else "")
            s.append(f"  - {a.id} ({a.kind}) {a.description}{cmd}")
        if w.notes:
            s.append(f"- **notes**: {w.notes}")
        s.append("")

    s.append("## Traceability\n")
    s.append(traceability_markdown(d))

    if d.conventions.language or d.conventions.test_command or d.conventions.rules:
        s.append("## Conventions\n")
        cv = d.conventions
        if cv.language:
            s.append(f"- **language**: {cv.language}")
        if cv.test_command:
            s.append(f"- **test**: `{cv.test_command}`")
        if cv.lint_command:
            s.append(f"- **lint**: `{cv.lint_command}`")
        s.extend(f"- {r}" for r in cv.rules)
        if cv.definition_of_done:
            s.append("\n**Definition of done**\n")
            s.extend(f"- {x}" for x in cv.definition_of_done)
        s.append("")
    return "\n".join(s).rstrip() + "\n"
