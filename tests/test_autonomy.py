"""Autonomy: the engine answers its own questions and owns every requirement."""
from __future__ import annotations

from pathlib import Path

from sekkei import rules as R
from sekkei.engine import answers as A
from sekkei.engine import design, analyse
from sekkei.engine.gaps import questions

FIX = Path(__file__).parent / "fixtures"
MINIMAL = "# Newsletter signup\n\n- Visitors can subscribe with an email address and confirm through a link sent by email.\n- Admins can export the subscriber list as CSV.\n"


def load(name: str) -> str:
    return (FIX / f"{name}.md").read_text(encoding="utf-8")


def test_every_question_has_an_answer_rule():
    an = analyse(MINIMAL)
    qs = questions(an)
    unanswered = [q.id for q in qs if A.answer(q, an) is None]
    assert unanswered == []


def test_minimal_input_leaves_no_open_question_and_the_answers_shape_the_design():
    r = design(MINIMAL)
    assert r.ok
    answered = {a.question_id for a in r.answers}
    assert {q.id for q in r.notes.questions} <= answered
    # answers flowed through the normal analysis
    assert r.design.conventions.language == "python"
    assert r.analysis.team_size == 2 and "postgres" in r.analysis.constraints
    assert {x.title: x.choice for x in r.design.decisions}["Primary store"] == "PostgreSQL"
    assert any(u.kind == "nonfunctional" and u.metric and "300 ms" in u.metric[1] for u in r.analysis.requirements)
    # and are recorded as proposed decisions and as flagged requirements
    proposed = [x for x in r.design.decisions if x.status == "proposed"]
    assert len(proposed) == len(r.answers) and all(x.title.startswith("Assumed answer") and len(x.options) >= 2 for x in proposed)
    assumed_reqs = [q for q in r.design.requirements if q.rationale.startswith("assumed by the engine")]
    assert assumed_reqs and all(q.statement.endswith("(assumed by the engine).") or "assumed by the engine" in q.statement for q in assumed_reqs)
    md = r.notes.to_markdown()
    assert "Questions the engine answered" in md and "Still open" not in md
    assert [d for d in R.lint(r.design, strict=True, disable=["Q"]) if d.severity != "info"] == []


def test_no_assume_keeps_the_questions_open():
    r = design(MINIMAL, assume=False)
    assert r.answers == [] and len(r.notes.questions) >= 10
    assert not any(x.status == "proposed" for x in r.design.decisions)
    assert "Questions to answer before committing" in r.notes.to_markdown()


def test_evidence_beats_defaults():
    r = design(load("cli_tool"))
    by_q = {a.question_id: a for a in r.answers}
    assert by_q["Q-store"].answer.startswith("SQLite") and by_q["Q-store"].evidence
    assert by_q["Q-auth"].answer.startswith("No authentication")
    r = design(load("inventory"))  # staff + OIDC provider already stated -> no auth question at all
    assert "Q-auth" not in {a.question_id for a in r.answers}
    r = design(load("webhooks"))
    assert {a.question_id for a in r.answers} >= {"Q-auth", "Q-retention", "Q-backup"}
    assert {a.question_id for a in r.answers}.isdisjoint({"Q-lang", "Q-store", "Q-rate", "Q-team"})


def test_unrecognised_requirements_get_owners_or_new_components():
    r = design(load("novel"))
    assert r.ok
    placed = {p.requirement: p for p in r.placements}
    assert set(placed) == {u.id for u in r.analysis.unrecognised} and placed
    hows = {p.how.split(" ")[0] for p in placed.values()}
    assert "synthesised" in hows
    names = {c.name for c in r.design.components}
    assert any(n.endswith(" reader") for n in names) and any(n.endswith(" controller") for n in names)
    assert "Local user interface" in names  # no network + panel -> ui, not an HTTP API
    # every requirement is owned, every synthesised component is packaged and wired to the core
    for q in r.design.requirements:
        assert any(q.id in c.satisfies for c in r.design.components), q.id
    core = next(c for c in r.design.components if c.name == "Domain core")
    for c in r.design.components:
        if "synthesised" in c.tags:
            assert r.design.packages_building(c.id)
            iface = r.design.provided_by(c.id)[0]
            assert iface.id in core.requires and iface.operations
            assert c.id in r.trace and r.trace[c.id]["rules"] == ["owner:synthesised"]
    md = r.notes.to_markdown()
    assert "placed without a catalogue pattern" in md and "synthesised" in md


def test_a_sentence_no_pattern_knows_is_still_placed():
    text = load("webhooks") + "\n## Functional\n- The system computes a health score for each endpoint from its last 100 attempts.\n"
    r = design(text)
    p = next((p for p in r.placements if "health score" in next(q.statement for q in r.design.requirements if q.id == p.requirement)), None)
    assert p is not None and p.owners and all(r.design.component(o) is not None for o in p.owners)
    assert p.how.startswith(("matched", "synthesised", "core rule"))


def test_autonomous_design_is_still_deterministic_and_lint_clean():
    import sekkei
    for name in ("novel", "cli_tool", "inventory", "webhooks"):
        a, b = design(load(name)), design(load(name))
        assert sekkei.dumps(a.design) == sekkei.dumps(b.design)
        assert a.ok and [d for d in R.lint(a.design, strict=True, disable=["Q"]) if d.severity != "info"] == []


def test_cli_flags(tmp_path, monkeypatch, capsys):
    from sekkei.cli import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / "r.md").write_text(MINIMAL)
    assert main(["design", "r.md", "-o", "d.json", "--review", "n.md", "--augmented", "a.md"]) == 0
    out = capsys.readouterr().out
    assert "questions answered by the engine" in out and (tmp_path / "a.md").read_text().count("Assumed by the engine") >= 1
    assert main(["design", "r.md", "-o", "d2.json", "--review", "n2.md", "--no-assume"]) == 0
    assert "open questions" in capsys.readouterr().out


def test_a_stated_platform_is_not_overwritten_by_the_engines_default():
    """The deployment, auth and migration questions are answered by the vocabulary of the *answers*:
    a text that says "private VMs, no public cloud" has answered the deployment question even though
    it never says "deploy", and the engine must not append a contradicting assumption."""
    text = ("# Crew swap\n\n## Functional\n- Planners can request a crew swap between two rostered flights.\n\n"
            "## Constraints\n- Private VMs only, no public cloud, no managed services.\n"
            "- Sign-in is through the corporate Okta tenant.\n"
            "- The existing roster system stays; integrate through its REST API.\n- Team of 4.\n")
    r = design(text)
    assumed = [x.statement for x in r.design.requirements if "assumed by the engine" in x.statement]
    assert not any("containers" in s or "ingress" in s for s in assumed), assumed
    assert not any("API keys" in s for s in assumed), assumed
    assert not any("no existing data" in s.lower() for s in assumed), assumed
