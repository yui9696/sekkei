"""The engine's self-audit finds what the linter cannot: ignored sentences, lost numbers, contradictions."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sekkei import redteam as RT

FIX = Path(__file__).parent / "fixtures"
EVAL = Path(__file__).parent.parent / "examples" / "eval"


def _rules(rt: RT.RedTeam, rule: str, severity: str | None = None) -> list[RT.Finding]:
    return [f for f in rt.findings if f.rule == rule and (severity is None or f.severity == severity)]


def test_inert_requirement_is_found_where_the_evaluation_said_the_design_is_silent():
    rt = RT.run((EVAL / "docsearch.md").read_text(encoding="utf-8"))
    hits = _rules(rt, "RT01", "high")
    assert hits and "visible only to members of the tagged team" in hits[0].evidence


def test_constraints_that_match_the_default_are_info_not_findings():
    rt = RT.run((FIX / "webhooks.md").read_text(encoding="utf-8"))
    assert not rt.high
    assert all(f.severity == "info" for f in _rules(rt, "RT01"))


def test_contradiction_between_can_and_must_not():
    text = "# T\n## Functional\n- Staff can delete orders through the API.\n- Staff must not delete orders after shipment.\n- Customers can delete their account.\n"
    rt = RT.run(text)
    hits = _rules(rt, "RT05", "high")
    assert len(hits) == 1 and "'delete orders'" in hits[0].message


def test_no_false_contradiction_from_quality_sentences():
    rt = RT.run((FIX / "inventory.md").read_text(encoding="utf-8"))
    assert not _rules(rt, "RT05")


def test_number_carried_only_as_a_note_is_reported():
    text = "# T\n## Functional\n- Staff can add items through a REST API.\n- The offer window is 15 seconds and a batch holds 7 drivers.\n## Constraints\n- Python. Team of 2.\n"
    rt = RT.run(text)
    hits = _rules(rt, "RT08")
    assert hits and hits[0].severity == "info" and "15 seconds" in hits[0].message


def test_determinism_and_deliverable_drift_are_clean_on_fixtures():
    for name in ("saas", "cli_tool", "novel"):
        rt = RT.run((FIX / f"{name}.md").read_text(encoding="utf-8"))
        assert not _rules(rt, "RT04") and not _rules(rt, "RT09"), name


def test_fragile_decisions_are_reported_as_info():
    rt = RT.run((FIX / "novel.md").read_text(encoding="utf-8"))
    hits = _rules(rt, "RT02")
    assert hits and all(f.severity == "info" for f in hits)
    assert any("Primary store" in f.message for f in hits)


def test_japanese_input_can_be_red_teamed():
    rt = RT.run((Path(__file__).parent.parent / "examples" / "ja" / "zaiko.md").read_text(encoding="utf-8"))
    assert rt.runs >= 10 and not _rules(rt, "RT04")


def test_cli_exit_code_follows_high_findings(tmp_path):
    p = tmp_path / "c.md"
    p.write_text("# T\n## Functional\n- Staff can delete orders through the API.\n- Staff must not delete orders after shipment.\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "sekkei.cli", "redteam", str(p), "-o", str(tmp_path / "r.md"), "--json"], capture_output=True, text=True)
    assert r.returncode == 1 and '"rule": "RT05"' in r.stdout and (tmp_path / "r.md").exists()
    r = subprocess.run([sys.executable, "-m", "sekkei.cli", "redteam", str(FIX / "webhooks.md")], capture_output=True, text=True)
    assert r.returncode == 0 and "Red-team report" in r.stdout
