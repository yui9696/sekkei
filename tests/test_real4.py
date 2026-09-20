"""The fourth red team: over-corrections of earlier fixes, and what it found on its own six specs."""
from __future__ import annotations

from pathlib import Path

import pytest
import subprocess
import sys

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


# ---- sixth red team: bugs (not phrasings) ------------------------------------------------------

def test_optional_priority_row_is_not_dropped_as_status():
    r = design((REAL4.parent / "real2" / "04_youken_medical.md").read_text(encoding="utf-8"))
    assert any(q.priority == "could" for q in r.design.requirements if not q.rationale.startswith("assumed"))
    assert not any("status '任意'" in n for n in r.analysis.structure.notes)


def test_japanese_state_adjectives_and_arrows():
    from sekkei.engine import ja
    assert ja.rewrite_sentence("発送済みの注文はキャンセルしてはならない").english == "The system must not cancel shipped orders."
    assert "cancel orders before shipped" in ja.rewrite_sentence("発送前であれば注文をキャンセルできる").english
    assert "accepted -> shipped -> completed" in ja.rewrite_sentence("注文は 受付→発送→完了 の状態を持つ").english


def test_non_nouns_never_seed_components_and_rules_go_to_the_aggregate():
    text = ("# Billing\n## Requirements\n- Customers can create an invoice with a number, a date and lines.\n- An invoice cannot be issued for a customer whose account is closed.\n"
            "- A refund amount cannot exceed the captured amount of the invoice.\n- An invoice total must equal the sum of its lines.\n## Constraints\n- Python, PostgreSQL. Team of 2.\n")
    r = design(text)
    names = {c.name for c in r.design.components}
    assert not any(n.startswith(("Cannot", "Line", "Refund")) and n.endswith(("processor", "reader", "controller")) for n in names), names


def test_terminal_states_do_not_continue_in_arrow_lists():
    from sekkei.engine import domain
    r = design((REAL4.parent / "real3" / "02_prd_petclaims.md").read_text(encoding="utf-8"))
    claim = next(e for e in domain.extract(r.analysis) if e.name == "claim")
    assert ("rejected", "paid") not in {(a, b) for a, b, _ in claim.edges}
    assert ("approved", "paid") in {(a, b) for a, b, _ in claim.edges}


def test_verbatim_routes_survive_without_an_actor_and_duplicates_are_merged():
    from sekkei import export as X
    text = "# Q\n## Requirements\n- The queue is left with DELETE /v2/queue/{ticket}; status is read with GET /v2/queue/{ticket}.\n- Players can join a queue.\n## Constraints\n- Go, Redis. Team of 3.\n"
    r = design(text)
    ops = {o.name for i in r.design.interfaces for o in i.operations}
    assert "DELETE /v2/queue/{ticket}" in ops and "GET /v2/queue/{ticket}" in ops
    spec = X.openapi(r.design)
    assert not any(p.endswith("-2") for p in spec["paths"])


def test_nbsp_numbers_html_comments_and_images():
    text = "# W\n## Requirements\n- Search responds within 2 000 ms p95 for 1 500 orders/s.\n<!-- Customers can delete all data instantly. -->\n- ![mockup](mockup.png) Staff can see the [dashboard](https://x) daily.\n## Constraints\n- Python. Team of 2.\n"
    r = design(text)
    stmts = " ".join(q.statement for q in r.design.requirements)
    assert "delete all data" not in stmts and "mockup" not in stmts
    m = next(q.metric for q in r.design.requirements if q.metric and "latency" in q.metric.name)
    assert "2000" in m.target
    assert not any("mockup" in o.name for i in r.design.interfaces for o in i.operations)


# ---- seventh red team (held-out): recurring defect classes, fixed structurally ------------------

def test_assumed_answer_is_the_decision():                              # class 4
    t = "# Portal\n## Requirements\n- Applicants can submit a form and see its status.\n- Staff can review a form and approve or reject it.\n## Constraints\n- Python, PostgreSQL. Team of 3.\n"
    r = design(t)
    auth = {d.title: d.choice for d in r.design.decisions}["Caller authentication"]
    assumed = next(a for a in r.answers if a.question_id == "Q-auth").options[0]
    assert ("OIDC" in assumed) == auth.startswith("OAuth2 / OIDC"), (assumed, auth)


def test_patterns_do_not_activate_from_background_prose():             # class 3
    t = "# Market\n\n## Background\nSearch, messaging and push notifications already exist and are not part of this work.\n\n## Requirements\n- Sellers can list an item with a title and a price.\n- Buyers can pay for an item; the money is held in escrow until delivery is confirmed.\n## Constraints\n- Python, PostgreSQL. Team of 4.\n"
    r = design(t)
    names = {c.name for c in r.design.components}
    assert "Search index" not in names and "Push gateway" not in names and "Chat provider" not in names, names


def test_team_from_label_line_and_people_count():                       # class 2
    r = design("# T\n## Requirements\n- Users can create a note.\n\nTeam: 3 platform engineers, 1 SRE, 1 designer.\n")
    assert r.analysis.team_size == 5
    r2 = design("# T\n## Requirements\n- Users can create a note.\n## Constraints\n- 6 people (4 backend, 2 mobile), Kotlin.\n")
    assert r2.analysis.team_size == 6


def test_not_in_this_lines_are_non_goals_and_not_chopped():              # class 5
    t = "# T\n## Requirements\n- Users can create a note.\n- NOT in this release: sharing notes with other users, and exporting to PDF.\n- We will NOT build a mobile app, a browser extension or an API.\n## Constraints\n- Python. Team of 2.\n"
    r = design(t)
    assert len(r.design.non_goals) >= 2 and not any("sharing notes" in q.statement for q in r.design.requirements)
    assert any("mobile app" in g for g in r.design.non_goals)


def test_state_list_on_its_own_line_and_from_to_rows():                  # class 1
    from sekkei.engine import domain
    t = "# T\n## Requirements\n- Coordinators can register a patient visit with a chief complaint and an acuity.\n- Lifecycle: waiting -> in_triage -> in_treatment -> discharged.\n- From waiting, a nurse can start triage, which moves the visit to in_triage.\n## Constraints\n- Python. Team of 2.\n"
    r = design(t)
    visit = next(e for e in domain.extract(r.analysis) if e.name == "visit")
    assert {"waiting", "in_triage", "in_treatment", "discharged"} <= set(visit.states)
    assert ("waiting", "in_triage") in {(a, b) for a, b, _ in visit.edges}


def test_capacity_not_from_reconcile_interval_or_money_per_day():         # class 6
    t = "# T\n## Requirements\n- The ledger reconciles every 30 seconds against 400 accounts.\n- A listing fee of $4 per day is charged.\n- Users can create a listing.\n## Constraints\n- Python. Team of 2.\n"
    r = design(t)
    assert not any("implied" in e.name for e in r.notes.capacity.estimates)
    assert not any("per day" in e.name and "4" == e.value for e in r.notes.capacity.estimates)


def test_multiword_subject_and_identified_by_fields():                   # class 7
    from sekkei.engine import domain
    t = "# T\n## Requirements\n- Warehouse staff can create a receipt.\n- A goods receipt is identified by a receipt number and carries a supplier, a delivery date and a pallet count.\n## Constraints\n- Python. Team of 2.\n"
    r = design(t)
    rec = next(e for e in domain.extract(r.analysis) if e.name == "receipt")
    assert {"receipt_number", "supplier", "delivery_date", "pallet_count"} <= {f[0] for f in rec.fields}


def test_unicode_comparators_and_directory_arg(tmp_path):
    assert [q.comparator for q in T.quantities("p95 ≤ 400 ms")] == ["≤"]
    r = subprocess.run([sys.executable, "-m", "sekkei.cli", "issues", "-d", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode != 0 and "is a directory" in (r.stderr + r.stdout) and "Traceback" not in r.stderr
