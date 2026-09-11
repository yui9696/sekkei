from __future__ import annotations

import json

import pytest

from sekkei import state as S
from sekkei.examples import starter_design


def good_report():
    return {
        "work_package": "WP-1", "files_touched": ["app/store.py", "tests/test_store.py"],
        "checks": [{"id": "A-1", "passed": True, "output": "ok"}, {"id": "A-2", "passed": True, "output": "3 ms"}],
        "deviations": [], "proposed_decisions": [], "notes": "",
    }


def test_report_template_lists_every_acceptance_check():
    t = S.report_template(starter_design(), "WP-1")
    assert [c["id"] for c in t["checks"]] == ["A-1", "A-2"]
    assert set(t) == set(S.REPORT_KEYS)
    with pytest.raises(KeyError):
        S.report_template(starter_design(), "WP-9")


@pytest.mark.parametrize("mutate,needle", [
    (lambda r: r.update(work_package="WP-9"), "not in the design"),
    (lambda r: r.pop("notes"), "missing key 'notes'"),
    (lambda r: r["checks"].pop(), "A-2 is not reported"),
    (lambda r: r["checks"][0].update(passed=False), "A-1 did not pass"),
    (lambda r: r["checks"].append({"id": "A-3", "passed": True}), "not an acceptance check"),
    (lambda r: r["files_touched"].append("app/api.py"), "outside the package's write scope"),
    (lambda r: r.update(checks="none"), "checks must be a list"),
])
def test_validate_report_rejects(mutate, needle):
    r = good_report()
    mutate(r)
    problems = S.validate_report(starter_design(), r)
    assert any(needle in p for p in problems), problems


def test_validate_report_accepts_a_good_report():
    assert S.validate_report(starter_design(), good_report()) == []
    assert S.validate_report(starter_design(), "no") == ["report must be a JSON object"]


def test_accept_marks_done_persists_and_unlocks(tmp_path):
    d = starter_design()
    st = S.State.load(tmp_path)
    assert st.status("WP-1") == "todo" and S.next_packages(d, st) == ["WP-1"]
    assert S.accept(d, st, good_report()) == []
    assert st.status("WP-1") == "done" and S.next_packages(d, st) == ["WP-2"]
    reloaded = S.State.load(tmp_path)
    assert reloaded.done() == {"WP-1"}
    assert reloaded.entry("WP-1")["report"]["checks"][0]["id"] == "A-1"
    assert json.loads((tmp_path / ".sekkei" / "state.json").read_text())["packages"]["WP-1"]["status"] == "done"
    bad = good_report()
    bad["checks"][0]["passed"] = False
    assert S.accept(d, st, bad)  # rejected, state untouched
    assert st.status("WP-1") == "done"


def test_status_table_and_set_status(tmp_path):
    d = starter_design()
    st = S.State.load(tmp_path)
    table = S.status_table(d, st)
    assert "| WP-1 | ready |" in table and "| WP-2 | todo |" in table
    st.set_status("WP-2", "blocked")
    assert "| WP-2 | blocked |" in S.status_table(d, st)
    with pytest.raises(ValueError):
        st.set_status("WP-2", "finished")
