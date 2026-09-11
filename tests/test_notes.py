"""The architect's notes: questions, capacity, effort, threats, template, sequence diagrams."""
from __future__ import annotations

import json
from pathlib import Path

from sekkei import render as RD
from sekkei.engine import REQUIREMENTS_TEMPLATE, ask, design
from sekkei.engine import gaps, sizing, threats

FIX = Path(__file__).parent / "fixtures"
MINIMAL = "# Newsletter signup\n\n- Visitors can subscribe with an email address and confirm through a link sent by email.\n- Admins can export the subscriber list as CSV.\n"


def load(name: str) -> str:
    return (FIX / f"{name}.md").read_text(encoding="utf-8")


def test_minimal_input_yields_a_design_and_the_questions_an_architect_would_ask():
    r = design(MINIMAL)
    assert r.ok and r.design.components and r.design.work_packages
    ids = {q.id for q in r.notes.questions}
    assert {"Q-lang", "Q-store", "Q-deploy", "Q-team", "Q-rate", "Q-latency", "Q-availability", "Q-auth"} <= ids
    assert "Q-compliance" in ids  # email = personal data, no regime stated
    assert all(q.assumption for q in r.notes.questions)
    md = r.notes.to_markdown()
    assert "## 1. Questions" in md and "## 2. Capacity" in md and "## 4. Threat model" in md and "no rate stated" in md


def test_a_complete_spec_leaves_few_questions():
    qs = {q.id for q in ask(load("webhooks"))}
    for answered in ("Q-lang", "Q-store", "Q-deploy", "Q-team", "Q-rate", "Q-volume", "Q-latency"):
        assert answered not in qs, answered
    # genuinely unanswered by the text: how customers authenticate to the admin API, retention, backups
    assert {"Q-auth", "Q-retention", "Q-backup"} <= qs


def test_answering_a_question_changes_only_its_target():
    before = design(MINIMAL)
    after = design(MINIMAL + "\n## Constraints\n- TypeScript on Node 20, PostgreSQL available.\n")
    qb = {q.id for q in before.notes.questions}
    qa = {q.id for q in after.notes.questions}
    assert {"Q-lang", "Q-store"} <= qb and not {"Q-lang", "Q-store"} & qa
    assert after.design.conventions.language == "typescript"
    assert {x.title: x.choice for x in after.design.decisions}["Primary store"] == "PostgreSQL"
    # unrelated parts unchanged
    assert [c.name for c in before.design.components] == [c.name for c in after.design.components]


def test_capacity_estimates_show_formula_and_inputs():
    r = design(load("webhooks"))
    cap = r.notes.capacity
    names = {e.name: e for e in cap.estimates}
    assert "events per day" in names and names["events per day"].value == "86.4 M"
    assert names["backlog after a 1 h downstream outage"].value.startswith("3.6 M")
    assert any("Little" in e.formula for e in cap.estimates)
    assert any("fan-out" in e.formula for e in cap.estimates)  # async delivery pattern
    assert all(e.inputs and e.formula for e in cap.estimates)
    assert cap.missing == []
    assert sizing.capacity(design(MINIMAL).analysis).missing


def test_effort_and_schedule():
    r = design(load("webhooks"))
    e = r.notes.effort
    assert e.team == 3 and e.person_days > 0 and e.critical_path_days <= e.calendar_days
    assert e.waves == [w for w in e.waves if w]
    md = sizing.effort_markdown(e)
    assert "person-days" in md and "critical path" in md


def test_threats_become_risks_with_mitigations_and_reach_the_briefs():
    r = design(load("webhooks"))
    d = r.design
    ssrf = [k for k in d.risks if k.description.startswith("[ssrf]")]
    assert ssrf and "private" in ssrf[0].mitigation and ssrf[0].affects
    assert all(k.mitigation for k in d.risks)
    rows = threats.threat_table(d)
    assert {cat for _, _, th in rows for cat in [th.category]} >= {"spoofing", "tampering", "ssrf", "denial_of_service"}
    assert threats.inject_risks(d) == 0  # idempotent
    md = threats.threats_markdown(d)
    assert "| C-" in md and "proof" in md


def test_template_and_sequence_diagrams():
    assert "## Functional" in REQUIREMENTS_TEMPLATE and "## Out of scope" in REQUIREMENTS_TEMPLATE
    r = design(REQUIREMENTS_TEMPLATE.replace("<", "").replace(">", ""))
    assert r.ok  # the template itself is designable
    d = design(load("webhooks")).design
    seq = RD.sequence(d, d.flows[0].id)
    assert seq.startswith("sequenceDiagram") and "->>" in seq
    assert RD.render_markdown(d).count("sequenceDiagram") == len(d.flows)


def test_cli_ask_and_template(tmp_path, monkeypatch, capsys):
    from sekkei.cli import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / "r.md").write_text(MINIMAL)
    assert main(["ask", "r.md"]) == 0
    assert "| 1 |" in capsys.readouterr().out
    assert main(["ask", "r.md", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"].startswith("Q-")
    assert main(["template", "-o", "requirements.md"]) == 0
    assert (tmp_path / "requirements.md").read_text().startswith("# <System name>")
    assert main(["design", "r.md", "-o", "d.json", "--review", "n.md"]) == 0
    assert "open questions" in capsys.readouterr().out and "Threat model" in (tmp_path / "n.md").read_text()
