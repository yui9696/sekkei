from __future__ import annotations

from sekkei import render as RD
from sekkei.examples import starter_design


def test_render_markdown_has_every_section_and_graphs():
    d = starter_design()
    md = RD.render_markdown(d)
    for h in ("## Requirements", "## Components", "## Interfaces", "## Entities", "## Flows",
              "## Decisions", "## Risks", "## Work packages", "## Traceability", "## Conventions"):
        assert h in md
    assert md.count("```mermaid") == 2 + len(d.flows)  # component graph, package graph, one sequence diagram per flow
    assert "C_2 -->|I-1| C_1" in md and "WP_1 --> WP_2" in md
    assert "**Layers**" in md and "**Waves**" in md and "Critical path (weight 3)" in md
    assert "✔ **in-memory list**" in md and "✘ **sqlite**" in md


def test_render_escapes_pipes_in_tables():
    d = starter_design()
    d.requirements[0].statement = "a | b"
    assert "a \\| b" in RD.render_markdown(d)


def test_render_survives_cycles():
    d = starter_design()
    d.components[0].requires.append("I-2")
    md = RD.render_markdown(d)
    assert "Layers not computable" in md


def test_dot_and_mermaid_outputs():
    d = starter_design()
    dot = RD.dot(d, "components")
    assert '"C-2" -> "C-1" [label="I-1"];' in dot
    assert '"WP-1" -> "WP-2";' in RD.dot(d, "packages")
    assert 'WP_2["WP-2 HTTP API (M)"]' in RD.mermaid(d, "packages")


def test_traceability_markdown():
    t = RD.traceability_markdown(starter_design())
    assert "| R-3 | must | C-1 | WP-1 | A-1, A-2 |" in t
