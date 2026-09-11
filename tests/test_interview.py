"""Designing in dialogue: prompts in architect order, answers become canonical requirements, overrides stick."""
from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from sekkei.engine import Overrides, design
from sekkei.engine.interview import Interview, canonical_bullet, classify_free_text, run_cli

FIX = Path(__file__).parent / "fixtures"
NOVEL = (FIX / "novel.md").read_text(encoding="utf-8")


def test_free_text_becomes_classified_bullets():
    items = classify_free_text("Staff can add stock items through a REST API. Search returns within 300 ms p95. TypeScript on Node 20, PostgreSQL available")
    assert items == [("functional", "Staff can add stock items through a REST API."),
                     ("nonfunctional", "Search returns within 300 ms p95."),
                     ("constraint", "TypeScript on Node 20, PostgreSQL available.")]


def test_canonical_bullets_are_recognisable_by_the_analyser():
    assert canonical_bullet("Q-team", "we are 3") == ("constraint", "Team of 3.")
    assert canonical_bullet("Q-store", "PostgreSQL 15 and Redis") == ("constraint", "PostgreSQL 15 and Redis available.")
    assert canonical_bullet("Q-latency", "200 ms") == ("nonfunctional", "Operations complete within 200 ms p95.")
    assert canonical_bullet("Q-auth", "OIDC with Okta") == ("constraint", "Authentication via OIDC with Okta.")
    iv = Interview()
    iv.add("Staff can add stock items through a REST API.")
    for qid, raw in (("Q-team", "3"), ("Q-store", "PostgreSQL"), ("Q-lang", "TypeScript on Node 20")):
        p = next(p for p in iv.pending() if p.key == qid)
        iv.reply(p, raw)
    an = iv.result().analysis
    assert an.team_size == 3 and "postgres" in an.constraints and an.languages == ["typescript"]
    assert not any(p.key in ("Q-team", "Q-store", "Q-lang") for p in iv.pending())


def test_prompts_come_in_architect_order_and_enter_accepts_the_proposal():
    iv = Interview(NOVEL)
    pend = iv.pending()
    assert pend[0].kind == "placement" and "Temperature reader" in pend[0].proposal
    assert [p.kind for p in pend].index("question") > 0
    topics = [p.key for p in pend if p.kind == "question"]
    assert topics.index("Q-deploy") < topics.index("Q-rate")
    ack = iv.reply(pend[0], "")
    assert ack == "owner confirmed"
    q = next(p for p in iv.pending() if p.kind == "question")
    ack = iv.reply(q, "")
    assert ack.startswith("accepted:")
    assert "(confirmed in the interview)" in iv.text()
    assert q.key in iv.answers and q.key not in {p.key for p in iv.pending()}


def test_a_named_owner_overrides_the_synthesised_component():
    iv = Interview(NOVEL)
    p = next(p for p in iv.pending() if p.kind == "placement" and "Vents" in p.proposal)
    iv.reply(p, "Domain core")
    r = iv.result()
    placed = next(x for x in r.placements if r.design.requirement(x.requirement).statement == p.key)
    assert placed.how == "chosen in the interview" and r.design.component(placed.owners[0]).name == "Domain core"
    assert not any(c.name == "Vents controller" for c in r.design.components)
    assert r.ok


def test_close_decisions_can_be_forced():
    # force a decision through the override path and check the rationale
    r = design("# Shop\n\n## Functional\n- Customers can create and list orders through a REST API.\n\n## Constraints\n- Python 3.12, PostgreSQL available. Team of 2.\n",
               overrides=Overrides(decisions={"api_style": "gRPC"}))
    d = next(x for x in r.design.decisions if x.title == "API style")
    assert d.choice == "gRPC" and "chosen in the interview" in d.rationale
    iv = Interview()
    iv.add("Customers can create and list orders through a REST API.")
    from sekkei.engine.interview import Prompt
    ack = iv.reply(Prompt("decision", "api_style", "x", "1", options=["REST/JSON over HTTP (1.4)", "gRPC (1.3)"]), "2")
    assert ack.endswith("gRPC") and iv.decisions == {"api_style": "gRPC"}


def test_skip_undo_and_state_round_trip():
    iv = Interview()
    iv.add("Visitors can subscribe with an email address.")
    q = next(p for p in iv.pending() if p.kind == "question")
    iv.reply(q, "skip")
    assert q.key in iv.skipped and q.key not in {p.key for p in iv.pending()}
    assert iv.undo() and q.key not in iv.skipped
    iv.reply(q, "PostgreSQL" if q.key == "Q-store" else "x")
    again = Interview.from_state(json.loads(json.dumps(iv.to_state())))
    assert again.text() == iv.text() and again.answers == iv.answers


def test_run_cli_scripted_session(tmp_path):
    script = StringIO(
        "The controller reads temperature from four sensors every ten seconds.\n"  # requirement (describe phase)
        "It opens or closes the roof vents according to the setpoints.\n"          # another one
        "\n"            # empty line: start the questions
        "\n"            # accept the first placement proposal
        "\n"            # accept the second
        "Rust\n"        # Q-lang
        "The grower adjusts setpoints on a touch panel.\n"  # a stray requirement typed at a question: added, question re-asked
        "skip\n"        # that question left open
        "/status\n"
        "/design\n"
        "/done\n"
    )
    out = StringIO()
    assert run_cli(script, out, tmp_path) == 0
    text = out.getvalue()
    assert "[placement]" in text and "owner confirmed" in text and "Rust." in (tmp_path / "requirements.md").read_text()
    assert "reads as a requirement" in text and "touch panel" in (tmp_path / "requirements.md").read_text()
    assert "- skip." not in (tmp_path / "requirements.md").read_text()
    assert (tmp_path / "design.json").exists() and (tmp_path / "NOTES.md").exists()
    st = json.loads((tmp_path / ".sekkei" / "interview.json").read_text())
    assert st["answers"].get("Q-lang") == "Rust." and st["skipped"]
    # resuming picks the state up
    out2 = StringIO()
    run_cli(StringIO("/done\n"), out2, tmp_path)
    assert "resumed" in out2.getvalue()


def test_requirement_vs_answer_heuristic():
    from sekkei.engine.interview import Prompt, looks_like_requirement

    q = Prompt("question", "Q-team", "How many people?", "2")
    assert looks_like_requirement("Customers can see delivery attempts per event and manually redeliver.", q)
    assert not looks_like_requirement("3", q) and not looks_like_requirement("PostgreSQL and Redis", q)
    assert not looks_like_requirement("Customers can see delivery attempts per event.", Prompt("decision", "k", "x", "1"))
    assert canonical_bullet("Q-team", "Python 3.12 team of 3") == ("constraint", "Team of 3.")


def test_cli_command(tmp_path, monkeypatch, capsys):
    from sekkei.cli import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / "replies.txt").write_text("Users can upload photos and share them with friends.\n\n\n\n/done\n")
    assert main(["interview", "--script", "replies.txt", "--out-dir", "out"]) == 0
    assert (tmp_path / "out" / "design.json").exists()
    assert "status:" in capsys.readouterr().out
