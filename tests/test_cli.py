"""End-to-end loop through the command line: init, lint, render, plan, brief, accept, next."""
from __future__ import annotations

import json
import os

import pytest

from sekkei.cli import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--name", "demo"]) == 0
    return tmp_path


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_full_loop(project, capsys):
    code, out, _ = run(capsys, "lint")
    assert code == 0 and "OK" in out

    code, out, _ = run(capsys, "render", "-o", "DESIGN.md")
    assert code == 0 and (project / "DESIGN.md").read_text().startswith("# demo — design")

    code, out, _ = run(capsys, "plan", "--json")
    plan = json.loads(out)
    assert plan["waves"] == [["WP-1"], ["WP-2"]] and plan["ready"] == ["WP-1"]
    assert plan["packages"]["WP-2"]["status"] == "todo"

    code, out, _ = run(capsys, "brief", "WP-1", "-o", "brief.md")
    assert code == 0 and "# Work package WP-1" in (project / "brief.md").read_text()

    code, out, _ = run(capsys, "next")
    assert out.split() == ["WP-1"]

    report = {"work_package": "WP-1", "files_touched": ["app/store.py"],
              "checks": [{"id": "A-1", "passed": True, "output": ""}, {"id": "A-2", "passed": True, "output": ""}],
              "deviations": [], "proposed_decisions": [], "notes": ""}
    (project / "report.json").write_text(json.dumps(report))
    code, out, _ = run(capsys, "accept", "report.json")
    assert code == 0 and "accepted WP-1; now ready: WP-2" in out

    code, out, _ = run(capsys, "status")
    assert "| WP-1 | done |" in out and "| WP-2 | ready |" in out
    code, out, _ = run(capsys, "start", "WP-2")
    assert code == 0 and "in_progress" in out
    code, out, _ = run(capsys, "brief", "WP-2")
    assert "WP-1=done" in out

    report["checks"][0]["passed"] = False
    (project / "report.json").write_text(json.dumps(report))
    code, out, _ = run(capsys, "accept", "report.json")
    assert code == 1 and "rejected" in out and "A-1 did not pass" in out


def test_design_change_after_brief_is_caught(project, capsys):
    (project / "old.json").write_text((project / "design.json").read_text())
    assert run(capsys, "brief", "WP-1")[0] == 0  # records the fingerprint
    code, out, _ = run(capsys, "diff", "old.json")
    assert code == 0 and out == "no changes\n"
    d = json.loads((project / "design.json").read_text())
    d["interfaces"][0]["operations"][0]["output"] = "Todo"
    (project / "design.json").write_text(json.dumps(d))
    code, out, _ = run(capsys, "diff", "old.json")
    assert code == 1 and "changed  interfaces/I-1 (output)" not in out  # fields are nested: operations
    assert "changed  interfaces/I-1 (operations)" in out and "WP-1:" in out and "WP-2:" in out
    code, out, _ = run(capsys, "status")
    assert "| WP-1 | ready (stale brief) |" in out and "| WP-2 | todo |" in out
    report = {"work_package": "WP-1", "files_touched": [], "deviations": [], "proposed_decisions": [], "notes": "",
              "checks": [{"id": "A-1", "passed": True}, {"id": "A-2", "passed": True}]}
    (project / "report.json").write_text(json.dumps(report))
    code, out, _ = run(capsys, "accept", "report.json")
    assert code == 1 and "stale" in out
    assert run(capsys, "brief", "WP-1")[0] == 0  # re-issue the brief against the new design
    code, out, _ = run(capsys, "accept", "report.json")
    assert code == 0
    code, out, _ = run(capsys, "diff", "old.json", "--json")
    assert json.loads(out)["affected"]["WP-2"]


def test_scope_check_and_drift(project, capsys):
    code, out, _ = run(capsys, "scope", "WP-1", "app/store.py", "app/api.py")
    assert code == 1 and "app/api.py" in out
    code, out, _ = run(capsys, "scope", "WP-1", "app/store.py")
    assert code == 0
    code, out, _ = run(capsys, "check")  # nothing implemented yet
    assert code == 1 and "missing_path" in out
    os.makedirs("app")
    (project / "app" / "store.py").write_text("class Store:\n    def add(self, title): ...\n    def list_all(self): ...\n")
    (project / "app" / "api.py").write_text("from .store import Store\n")
    code, out, _ = run(capsys, "check", "--json")
    assert code == 0 and all(f["severity"] != "error" for f in json.loads(out))


def test_lint_flags_and_gate(project, capsys):
    d = json.loads((project / "design.json").read_text())
    d["risks"][0]["mitigation"] = ""  # a warning
    (project / "design.json").write_text(json.dumps(d))
    assert run(capsys, "lint")[0] == 0
    assert run(capsys, "lint", "--strict")[0] == 1
    assert run(capsys, "lint", "--disable", "V007")[0] == 0
    code, out, _ = run(capsys, "lint", "--json")
    assert json.loads(out)[0]["rule"] == "V007"
    d["work_packages"][0]["files"] = []  # an error
    (project / "design.json").write_text(json.dumps(d))
    assert run(capsys, "lint")[0] == 1
    with pytest.raises(SystemExit):
        main(["brief", "WP-1"])  # gated
    assert main(["brief", "WP-1", "--force"]) == 0
    with pytest.raises(SystemExit):
        main(["plan"])


def test_misc_commands(project, capsys):
    code, out, _ = run(capsys, "schema")
    assert json.loads(out)["title"] == "sekkei design file"
    code, out, _ = run(capsys, "rules")
    assert "| S001 |" in out
    code, out, _ = run(capsys, "prompt", "--no-schema")
    assert "solution architect" in out
    code, out, _ = run(capsys, "graph", "--dot", "--packages")
    assert "digraph" in out
    code, out, _ = run(capsys, "matrix", "--json")
    assert "R-1" in json.loads(out)
    with pytest.raises(SystemExit):
        main(["init"])  # refuses to overwrite
    assert main(["init", "--force"]) == 0
    with pytest.raises(SystemExit):
        main(["lint", "-d", "missing.json"])
    (project / "bad.json").write_text("{")
    with pytest.raises(SystemExit):
        main(["lint", "-d", "bad.json"])


def test_python_dsl_file_is_accepted(project, capsys):
    (project / "design.py").write_text("from sekkei.examples import starter_design\ndesign = starter_design('py')\n")
    code, out, _ = run(capsys, "lint", "-d", "design.py")
    assert code == 0
