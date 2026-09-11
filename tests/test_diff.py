from __future__ import annotations

from sekkei import brief as B
from sekkei import diff as DF
from sekkei import state as S
from sekkei.examples import starter_design


def test_diff_lists_added_removed_changed():
    old, new = starter_design(), starter_design()
    new.interfaces[0].operations[0].output = "Todo"          # I-1 changed
    new.requirements.pop(0)                                 # R-1 removed
    new.risks.append(type(new.risks[0])("K-2", "x"))        # K-2 added
    new.conventions.rules.append("Use black.")
    changes = DF.diff(old, new)
    assert [(c.collection, c.id, c.kind) for c in changes] == [
        ("requirements", "R-1", "removed"),
        ("interfaces", "I-1", "changed"),
        ("risks", "K-2", "added"),
        ("$", "conventions", "changed"),
    ]
    assert changes[1].fields == ["operations"]
    assert DF.diff(old, starter_design()) == []


def test_affected_packages_follow_the_graph():
    old, new = starter_design(), starter_design()
    new.interfaces[0].operations[0].output = "Todo"  # I-1: implemented by WP-1, consumed by WP-2's C-2
    aff = DF.affected_packages(new, DF.diff(old, new))
    assert set(aff) == {"WP-1", "WP-2"}
    assert "implemented interface I-1 changed" in aff["WP-1"]
    assert "consumed interface I-1 changed" in aff["WP-2"]

    old, new = starter_design(), starter_design()
    new.requirements[0].statement += " Titles are trimmed."  # R-1: WP-2 only
    assert list(DF.affected_packages(new, DF.diff(old, new))) == ["WP-2"]

    old, new = starter_design(), starter_design()
    new.decisions[0].choice = "sqlite"  # affects C-1 -> WP-1
    assert list(DF.affected_packages(new, DF.diff(old, new))) == ["WP-1"]

    old, new = starter_design(), starter_design()
    new.conventions.test_command = "pytest"
    assert set(DF.affected_packages(new, DF.diff(old, new))) == {"WP-1", "WP-2"}

    text = DF.format_diff(DF.diff(old, new), DF.affected_packages(new, DF.diff(old, new)))
    assert "changed  $/conventions" in text and "WP-1: conventions changed" in text
    assert DF.format_diff([], {}) == "no changes\n"


def test_stale_brief_blocks_acceptance(tmp_path):
    d = starter_design()
    st = S.State.load(tmp_path)
    fp = B.brief_fingerprint(d, "WP-1")
    st.record_brief("WP-1", fp)
    assert not st.is_stale("WP-1", fp) and not st.is_stale("WP-2", "anything")
    report = {"work_package": "WP-1", "files_touched": [], "deviations": [], "proposed_decisions": [], "notes": "",
              "checks": [{"id": "A-1", "passed": True}, {"id": "A-2", "passed": True}]}
    # design changes after the brief was issued
    d.interfaces[0].operations[0].inputs[0].type = "str, non-empty"
    fp2 = B.brief_fingerprint(d, "WP-1")
    assert fp2 != fp and st.is_stale("WP-1", fp2)
    problems = S.accept(d, st, report, fingerprint=fp2)
    assert problems and "stale" in problems[0]
    assert st.status("WP-1") == "todo"
    assert S.accept(d, st, report, fingerprint=fp2, force=True) == []
    assert "(stale brief)" in S.status_table(d, st, {"WP-1": fp2})
    # fingerprint ignores statuses
    st.set_status("WP-2", "in_progress")
    assert B.brief_fingerprint(d, "WP-1") == fp2
