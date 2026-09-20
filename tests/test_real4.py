"""The fourth red team: over-corrections of earlier fixes, and what it found on its own six specs."""
from __future__ import annotations

from pathlib import Path

import pytest

from sekkei import deliverables as DV
from sekkei import diff as DF
from sekkei import model as M
from sekkei import redteam as RT
from sekkei.engine import design, structure as S, text as T

REAL4 = Path(__file__).parent.parent / "examples" / "real4"


def _design(name: str):
    return design((REAL4 / f"{name}.md").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(p.stem for p in REAL4.glob("*.md")))
def test_specs_design_lint_clean_and_deterministic(name):
    text = (REAL4 / f"{name}.md").read_text(encoding="utf-8")
    r = design(text)
    assert r.ok, [str(d) for d in r.diagnostics if d.severity == "error"]
    assert M.dumps(r.design) == M.dumps(design(text).design)


def test_hash_prefixed_bullets_and_hash_column_survive():              # B1
    r = _design("rb_hash_bullets")
    stmts = [q.statement for q in r.design.requirements]
    assert any("create a widget" in s for s in stmts) and any("delete their own widget" in s for s in stmts)
    r2 = _design("rb_hash_table")
    assert len([q for q in r2.design.requirements if not q.rationale.startswith("assumed")]) >= 3
    r3 = _design("01_secq_hrsaas")
    stmts3 = " ".join(q.statement for q in r3.design.requirements)
    assert "SCIM 2.0" in stmts3 and "TLS 1.3" in stmts3 and "Sweden or Finland" in stmts3
    assert "AES-256" not in stmts3                                   # a CURRENT row is not work
    assert any("status 'CURRENT'" in n for n in r3.analysis.structure.notes)


def test_excluded_from_inside_a_requirement_is_a_condition():          # B2
    r = _design("exclusions")
    stmts = [q.statement for q in r.design.requirements if not q.rationale.startswith("assumed")]
    assert len(stmts) >= 5 and any("separate" in s for s in stmts) and any("download link" in s for s in stmts)
    assert r.design.non_goals == ["Phone system integration."]
    r2 = _design("excl_prose")
    assert any("excluded" in q.statement for q in r2.design.requirements)


def test_redteam_reports_untested_requirements():                      # B3
    rt = RT.run((REAL4.parent / "real3" / "03_rfp_nougyou.md").read_text(encoding="utf-8"))
    cov = [f for f in rt.findings if f.subject == "coverage"]
    assert not cov or int(cov[0].message.split(" of ")[0]) <= 2
    assert rt.runs > 10
    rt2 = RT.run((REAL4.parent.parent / "tests" / "fixtures" / "webhooks.md").read_text(encoding="utf-8"))
    assert not [f for f in rt2.findings if f.subject == "coverage"]      # wrapped bullets and paragraphs are located


def test_numbered_not_in_scope_heading():                              # B4
    r = _design("rb_numbered_nis")
    assert set(r.design.non_goals) == {"Payments to users.", "Changes to Northgate."}
    assert not any("Northgate" in q.statement for q in r.design.requirements)


def test_team_counts_sum_every_role():                                  # M1
    c = S.Canonical("")
    assert S._team_line("Team: 3 firmware, 2 bridge, 5 cloud, 3 mobile, 1 QA, 1 security.", c).startswith("Team of 15.")
    assert S._team_line("Team: Tokyo 4 server engineers, Berlin 2 tools engineers + 1 data engineer, 1 SRE shared.", c).startswith("Team of 8.")
    assert S._team_line("Team: 2 developers, 1 designer, 1 content designer (Welsh), 1 user researcher, 1 delivery manager; an accessibility specialist is available 2 days a week.", c).startswith("Team of 6.")
    assert _design("03_hw_fw_cloud_lock").analysis.team_size == 15


def test_capacity_is_not_extrapolated_from_bursts_or_unrelated_numbers():   # M2
    r = _design("01_secq_hrsaas")
    for e in r.notes.capacity.estimates:
        assert "637" not in e.value and "TB" not in e.value or "peak" in e.name.lower(), (e.name, e.value)
    r2 = design((REAL4.parent / "real2" / "01_confluence_trading.md").read_text(encoding="utf-8"))
    names = {e.name: e for e in r2.notes.capacity.estimates}
    assert not any("34.56 M" in e.value for e in names.values())        # the 400/s London-open burst is a peak, not a day
    r3 = design((REAL4.parent / "real3" / "01_tender_grid.md").read_text(encoding="utf-8"))
    assert not any("peaks of" in q.statement for q in r3.design.requirements if q.rationale.startswith("assumed"))   # no invented 10× peak


def test_slo_window_is_not_the_maintenance_window():                    # M3
    r = _design("01_secq_hrsaas")
    slo = DV.slos(r.design)
    assert "02:00" not in slo and "4 h ×" not in slo


def test_stray_words_do_not_rearchitect_round4():                       # M4
    r = _design("06_research_platform_diagrams")
    choices = {d.title: d.choice for d in r.design.decisions}
    assert choices["Primary store"] != "SQLite" and "cli_tool" not in r.analysis.stated_constraints   # "--submits-->"
    names = {c.name for c in r.design.components}
    assert "Payment provider" not in names and "Payments" not in names                                  # "pays for"
    r4 = _design("04_public_wcag_benefits")
    names4 = {c.name for c in r4.design.components}
    assert "Chat provider" not in names4                                                                 # "support-centre teams"
    assert "Command line" in names4                                                                     # benefits-admin is a real (side) CLI
    assert {d.title: d.choice for d in r4.design.decisions}["Primary store"] != "SQLite"
    assert {d.title: d.choice for d in r4.design.decisions}["Caller authentication"].startswith("No account")


def test_modality_main_clause():                                        # M5
    assert T.modality("Availability 99.9 % for submission; the payout step may degrade.") == ""
    assert T.modality("assigns credentials (phone, PIN, or both) with optional schedules.") == ""
    assert T.modality("Users can archive projects they no longer need; archived projects are not deleted.") == ""
    r = _design("03_hw_fw_cloud_lock")
    cl1 = next(q for q in r.design.requirements if "optional schedules" in q.statement)
    assert cl1.priority == "must"


def test_status_columns_and_erp_table():                                # M6
    r = _design("02_erp_change_table")
    stmts = [q.statement for q in r.design.requirements if not q.rationale.startswith("assumed")]
    assert not any("Script reader" == c.name for c in r.design.components)
    assert any("second approver" in s for s in stmts)


def test_contradiction_candidates_are_reported():                       # M8
    rt = RT.run((REAL4 / "06_research_platform_diagrams.md").read_text(encoding="utf-8"))
    msgs = [f.message for f in rt.findings if f.rule == "RT05"]
    assert any("retention vs deletion" in m or "anonymity" in m or "residency" in m or "forbidden practice" in m for m in msgs), msgs


def test_diff_after_two_added_requirements():                           # M9
    d1 = _design("03_hw_fw_cloud_lock").design
    d2 = _design("03b_hw_fw_cloud_lock_v2").design
    changes = DF.diff(d1, d2)
    assert [c for c in changes if c.kind == "added" and c.collection == "requirements"]
    assert not [c for c in changes if c.collection == "requirements" and c.kind == "changed"]
    affected = DF.affected_packages(d2, changes)
    assert len(affected) < len(d2.work_packages)


def test_residency_multi_jurisdiction_and_tokyo():                      # M10
    r = _design("03_hw_fw_cloud_lock")
    choices = {d.title: d.choice for d in r.design.decisions}
    assert "per jurisdiction" in choices.get("Where personal data may live", "").lower()
    r3 = design((REAL4.parent / "real3" / "03_rfp_nougyou.md").read_text(encoding="utf-8"))
    assert any("Tokyo" in q.statement for q in r3.design.requirements)
    assert "data_residency" in r3.analysis.constraints


def test_names_and_temperatures_are_not_quantities():                   # M11
    assert not [q for q in T.quantities("operated in accordance with IEC 62443-3-3 Security Level 2") if q.value == 62443]
    assert not [q for q in T.quantities("21 CFR Part 11 applies") if q.value == 21]
    assert T.quantities("stored at −20 °C") == []
