"""The structure pass: specifications as engineers write them (tables, numbered headings, stories, labels)."""
from __future__ import annotations

import glob
import random
from pathlib import Path

import pytest

from sekkei import model as M
from sekkei.engine import design
from sekkei.engine import structure as S

REAL = Path(__file__).parent.parent / "examples" / "real"


def test_numbered_headings_and_requirement_table_japanese():
    c = S.canonicalise((REAL / "rfp_ja.md").read_text(encoding="utf-8"))
    assert "## Functional" in c.text and "## Non-functional" in c.text and "## Constraints" in c.text and "## Out of scope" in c.text
    assert "## Background" in c.text
    assert "- F-1 従業員は経費(日付、金額、費目、領収書画像)を申請できること。 (must)" in c.text
    assert "(could)" in c.text and "(should)" in c.text
    assert c.deadline and "2027" in c.deadline
    assert any(n.startswith("front matter skipped") for n in c.notes)
    assert "給与計算" in c.text.split("## Out of scope")[1]


def test_user_stories_and_acceptance_criteria():
    c = S.canonicalise((REAL / "jira_export.md").read_text(encoding="utf-8"))
    assert c.text.startswith("# Customer self-service returns portal")
    assert "- Customers can request a return for an order item." in c.text
    assert "when the customer selects an item" in c.text and "double-clicks" in c.text
    assert c.rationales["Customers can request a return for an order item."] == "they get a refund"
    assert "Story points" not in c.text


def test_meeting_notes_labels_todo_out_of_scope_decided():
    c = S.canonicalise((REAL / "slack_notes.md").read_text(encoding="utf-8"))
    assert c.todos == ["Ana: ask data-eng about a read-only role"]
    assert "## Out of scope\n- Writing back to Snowflake.\n- Any BI-tool replacement." in c.text
    assert "## Constraints\n- Python, we already have the FastAPI template." in c.text
    assert "Team of 2 (Bo, Chen)." in c.text
    assert c.deadline == "MVP in 6 weeks"
    assert any(t.startswith("maybe alerts?") for t in c.tentative)
    assert "Ana:" not in c.text


def test_rfc_sections_and_alternatives():
    c = S.canonicalise((REAL / "rfc_en.md").read_text(encoding="utf-8"))
    assert "## Background" in c.text and "## Requirements" in c.text and "## Out of scope" in c.text
    assert c.alternatives and c.alternatives[0].startswith("Envoy with ext_authz")
    assert "Envoy" not in c.text.split("## Constraints")[1]
    r = design((REAL / "rfc_en.md").read_text(encoding="utf-8"))
    assert r.ok
    kinds = {q.id: q.kind for q in r.design.requirements}
    nf = [q for q in r.design.requirements if q.kind == "nonfunctional" and not q.rationale.startswith("assumed")]
    assert len(nf) >= 3, kinds        # the generic "Requirements" heading does not force everything functional
    assert any(d.status == "rejected" and "Envoy" in d.title for d in r.design.decisions)
    assert r.analysis.languages == ["go"]


def test_checkboxes_and_nested_bullets():
    c = S.canonicalise((REAL / "mixed.md").read_text(encoding="utf-8"))
    assert "[ ]" not in c.text and "[x]" not in c.text
    assert "  - 予約確定時に SMS と email で通知" in c.text
    assert sum(1 for n in c.notes if n.startswith("nested bullet")) == 3


def test_one_liner_is_designed():
    r = design((REAL / "tiny.md").read_text(encoding="utf-8"))
    assert r.ok and any(not q.rationale.startswith("assumed") for q in r.design.requirements)
    assert r.design.name == "a-slack-bot"
    assert "Chat provider" in {c.name for c in r.design.components}


@pytest.mark.parametrize("name", sorted(p.stem for p in REAL.glob("*.md")))
def test_real_specs_design_lint_clean_and_deterministic(name):
    text = (REAL / f"{name}.md").read_text(encoding="utf-8")
    r = design(text)
    assert r.ok, [str(d) for d in r.diagnostics if d.severity == "error"]
    assert M.dumps(r.design) == M.dumps(design(text).design)
    assert r.notes.to_markdown()


def test_go_is_a_language_only_as_a_tech_token():
    r = design("# x\n## Functional\n- Users go to the page and submit a form.\n## Constraints\n- Python. Team of 2.\n")
    assert r.analysis.languages == ["python"]
    r = design((REAL / "todo_engineer.md").read_text(encoding="utf-8"))
    assert r.analysis.languages == ["go"]
    assert r.design.conventions.language == "go"


def test_store_decision_uses_the_stated_database():
    r = design((REAL / "migration.md").read_text(encoding="utf-8"))
    store = {x.title: x.choice for x in r.design.decisions}["Primary store"]
    assert store.startswith("MySQL")
    r2 = design("# x\n## Functional\n- Users can create orders.\n## Constraints\n- Containers behind an ingress. Team of 2.\n")
    assert {x.title: x.choice for x in r2.design.decisions}["Primary store"] == "PostgreSQL"


def test_fuzz_mutations_never_crash(tmp_path):
    srcs = [p.read_text(encoding="utf-8") for p in REAL.glob("*.md")]
    rnd = random.Random(7)
    junk = ["", "|", "```", "~~~", "# ", "- ", "1.", "TODO:", "（）", "﻿", "8:00", "1e30", "Team of 0.", "| No | 内容 |", "|---|---|"]
    for k in range(25):
        lines = rnd.choice(srcs).split("\n")
        for _ in range(rnd.randint(1, 6)):
            i = rnd.randrange(len(lines)) if lines else 0
            op = rnd.choice(["del", "dup", "junk", "trunc", "nest", "cut"])
            if op == "del" and lines:
                del lines[i]
            elif op == "dup" and lines:
                lines.insert(i, lines[i])
            elif op == "junk":
                lines.insert(i, rnd.choice(junk))
            elif op == "trunc" and lines:
                lines[i] = lines[i][: rnd.randint(0, len(lines[i]))]
            elif op == "nest" and lines:
                lines[i] = "    " + lines[i]
            elif op == "cut":
                lines = lines[:i]
        text = "\n".join(lines)
        r = design(text)
        assert M.dumps(r.design) == M.dumps(design(text).design)
        if r.design.requirements:
            assert not [d for d in r.diagnostics if d.severity == "error"], text[:200]


# --- a list introduced by a bare "…:" line, and what a reference section swallows -------------

_ACTION_LIST = """Notes from the depot sync

Present: two supervisors, one developer

Agreed actions:

- Drivers can record a failed delivery with a reason code.
- Supervisors can reassign a stop before the van leaves.
- The system keeps each delivery photo for 90 days.

DECIDED: we stay on the existing PostgreSQL instance; no new database.
Not included this time: the customer-facing tracking page.
"""


def test_a_list_introduced_by_a_bare_colon_line_is_read_not_swallowed():
    r = design(_ACTION_LIST)
    stated = [x.statement for x in r.design.requirements if "assumed by the engine" not in x.statement]
    assert any("record a failed delivery" in s for s in stated)
    assert any("reassign a stop" in s for s in stated)
    assert any("90 days" in s for s in stated)


def test_a_decision_or_an_exclusion_inside_an_action_list_keeps_its_kind():
    r = design(_ACTION_LIST)
    decided = next(x for x in r.design.requirements if "no new database" in x.statement)
    assert decided.kind == "constraint"
    assert any("tracking page" in g for g in r.design.non_goals), r.design.non_goals


def test_what_a_reference_section_swallows_is_listed_not_dropped_in_silence():
    text = ("# Depot tool\n\n## Functional\n- Drivers can record a failed delivery with a reason code.\n\n"
            "## Appendix\n\nThe depot ran on paper forms until last year.\nThe forms are archived in the back office.\n\n"
            "## Constraints\n- Python. Team of 2.\n")
    r = design(text)
    dropped = " ".join(t for t, _ in r.analysis.dropped)
    assert "paper forms" in dropped and "back office" in dropped, r.analysis.dropped
