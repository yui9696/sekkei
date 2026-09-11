"""Regressions from the debugging pass of 2026-09-11 (edge cases and quality fixes)."""
from __future__ import annotations

from pathlib import Path

import pytest

from sekkei import rules as R
from sekkei.engine import design

EVAL = Path(__file__).parent.parent / "examples" / "eval"
FIX = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("text", ["", "   \n\n", "# Only a title\n", "## Functional\n\n## Constraints\n"])
def test_empty_input_is_refused_not_designed_from_assumptions(text):
    r = design(text)
    assert not r.ok
    assert any(d.rule == "S008" for d in r.diagnostics)
    assert r.answers == [] and r.design.requirements == []


def test_cli_reports_missing_and_unreadable_files_without_tracebacks(tmp_path, monkeypatch, capsys):
    from sekkei.cli import main

    monkeypatch.chdir(tmp_path)
    for argv in (["design", "nope.md"], ["ask", "nope.md"], ["interview", "--script", "nope.txt"], ["draft", "nope.md"]):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert "not found" in str(exc.value)
    (tmp_path / "bin.md").write_bytes(b"\xff\xfe- Users can create items.\n")
    with pytest.raises(SystemExit) as exc:
        main(["design", "bin.md"])
    assert "UTF-8" in str(exc.value)
    (tmp_path / "e.md").write_text("# nothing\n")
    assert main(["design", "e.md", "-o", "e.json"]) == 1
    assert "S008" in capsys.readouterr().out
    (tmp_path / "r.md").write_text("- Users can create items through a REST API.\n")
    assert main(["design", "r.md", "-o", "deep/dir/x.json", "--render", "deep/dir/D.md"]) == 0  # parents created
    assert (tmp_path / "deep" / "dir" / "x.json").exists()


def test_packages_do_not_mix_domain_components_with_unrelated_ones():
    r = design((EVAL / "telemetry.md").read_text(encoding="utf-8"))
    d = r.design
    for w in d.work_packages:
        names = [d.component(c).name for c in w.components]
        if "Readings processor" in names:
            assert names == ["Readings processor"]
    # infrastructure may still be batched
    assert any(len(w.components) > 1 for w in d.work_packages)


def test_entry_point_interfaces_are_not_orphans():
    for f in ("telemetry", ):
        r = design((EVAL / f"{f}.md").read_text(encoding="utf-8"))
        assert not any(x.rule == "V008" for x in R.lint(r.design)), [str(x) for x in R.lint(r.design)]
    r = design((FIX / "novel.md").read_text(encoding="utf-8"))
    assert not any(x.rule == "V008" for x in R.lint(r.design))


def test_synthesised_contracts_use_the_entity_types_when_known():
    r = design((EVAL / "telemetry.md").read_text(encoding="utf-8"))
    proc = next(i for i in r.design.interfaces if i.name.startswith("Readings processor"))
    types = {p.type for o in proc.operations for p in o.inputs}
    assert "Reading" in types or "list[Reading]" in types


def test_timing_rules_of_a_use_case_reach_its_operation():
    r = design((EVAL / "ride.md").read_text(encoding="utf-8"))
    api = next(i for i in r.design.interfaces if i.name.startswith("Public HTTP API"))
    accept = next(o for o in api.operations if o.name == "POST /drivers/{id}/accept")
    assert "15 seconds" in accept.pre and "R-2" in accept.pre


def test_time_series_and_vector_store_decisions():
    r = design((EVAL / "telemetry.md").read_text(encoding="utf-8"))
    titles = {x.title: x.choice for x in r.design.decisions}
    assert titles.get("Time-series storage", "").startswith("TimescaleDB")
    r = design((EVAL / "docsearch.md").read_text(encoding="utf-8"))
    titles = {x.title: x.choice for x in r.design.decisions}
    assert titles.get("Vector index for semantic search", "").startswith("pgvector")


def test_interview_memoises_the_engine_run():
    from sekkei.engine.interview import Interview

    iv = Interview("- Users can create items through a REST API.\n")
    a = iv.result()
    b = iv.result()
    assert a is b
    iv.add("Users can delete items.")
    assert iv.result() is not a
