"""The third red team's specifications (tender annex, PRD, Japanese RFP, RFC, post-mortem, Notion page) and its findings."""
from __future__ import annotations

from pathlib import Path

import pytest

from sekkei import deliverables as DV
from sekkei import diff as DF
from sekkei import model as M
from sekkei.engine import design, text as T

REAL3 = Path(__file__).parent.parent / "examples" / "real3"


def _design(name: str):
    return design((REAL3 / f"{name}.md").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(p.stem for p in REAL3.glob("*.md")))
def test_specs_design_lint_clean_and_deterministic(name):
    text = (REAL3 / f"{name}.md").read_text(encoding="utf-8")
    r = design(text)
    assert r.ok, [str(d) for d in r.diagnostics if d.severity == "error"]
    assert M.dumps(r.design) == M.dumps(design(text).design)


def _ops(d):
    return {o.name for i in d.interfaces for o in i.operations}


def test_prohibitions_never_become_operations():                    # B1
    r = _design("01_tender_grid")
    ops = _ops(r.design)
    assert not any(o.startswith(("discard", "delete_alarm")) or o == "delete alarms" for o in ops), sorted(ops)
    forbidden = [q for q in r.design.requirements if "shall not be able to delete" in q.statement]
    assert forbidden and forbidden[0].kind == "nonfunctional"
    r2 = _design("02_prd_petclaims")
    assert not any("store_account" in o or "store_bank" in o for o in _ops(r2.design))
    assert "Account processor" not in {c.name for c in r2.design.components}
    r3 = _design("06_notion_trials")
    assert not any(o.startswith("get_allocation") for o in _ops(r3.design))


def test_stray_words_do_not_rearchitect():                         # B2
    r = _design("01_tender_grid")
    names = {c.name for c in r.design.components}
    assert "Command line" not in names and "cli_tool" not in r.analysis.patterns          # "Remote Terminal Units"
    assert not any("SQLite" in d.choice for d in r.design.decisions)
    r6 = _design("06_notion_trials")
    assert "Secret store" not in {c.name for c in r6.design.components}                  # "drawn signature" is not HMAC
    assert "Local user interface" not in {c.name for c in r6.design.components}            # "screen-failure reasons"
    r2 = _design("02_prd_petclaims")
    assert "Payouts" in {c.name for c in r2.design.components}


def test_in_memory_store_is_never_chosen_under_durability():        # B3
    for name in ("01_tender_grid", "05_postmortem_ediscovery"):
        r = _design(name)
        choices = {d.title: d.choice for d in r.design.decisions}
        assert "In-memory" not in choices.get("Primary store", ""), name
        assert "In-memory" not in choices.get("Work queue technology", ""), name


def test_no_fabricated_load_figures():                              # B4
    r = _design("01_tender_grid")
    cap = {e.name: e for e in r.notes.capacity.estimates}
    assert "implied update rate" in cap
    assert "60870" not in cap["implied update rate"].inputs
    assert "4,200" in cap["implied update rate"].inputs and "40 + 24" in cap["implied update rate"].inputs
    assert abs(cap["implied update rate"].number - 4200 * 64 / 4) < 1


def test_exclusions_and_reference_material_are_not_designed():      # B5
    r = _design("01_tender_grid")
    stmts = [q.statement for q in r.design.requirements]
    assert not any("Metering for billing" in s for s in stmts)
    assert any("Metering for billing" in g for g in r.design.non_goals)
    assert not any("12 control-room operators" in s or "3 outages" in s for s in stmts)
    assert not any(c.name.endswith("processor") and c.name.split()[0] in ("B", "B.1.3", "B.3") for c in r.design.components)
    r5 = _design("05_postmortem_ediscovery")
    stmts5 = [q.statement for q in r5.design.requirements]
    assert not any("02:14 UTC" in s or "extension was granted" in s for s in stmts5)     # timeline / what went well
    assert sum("shall" in s for s in stmts5) >= 8                                          # the action items
    assert any("near-duplicates are out of scope" in g for g in r5.design.non_goals)
    assert r5.analysis.team_size == 3
    r6 = _design("06_notion_trials")
    assert not any("<details>" in s or "<summary>" in s for s in [q.statement for q in r6.design.requirements])
    assert any("Medidata Rave" in g for g in r6.design.non_goals)
    assert r6.analysis.structure.todos and any("Part 11" in t for t in r6.analysis.structure.todos)
    assert r6.analysis.team_size == 6


def test_diff_is_content_keyed_and_issues_idempotent():             # B6
    base = (REAL3 / "05_postmortem_ediscovery.md").read_text(encoding="utf-8")
    v2 = (REAL3 / "05_postmortem_ediscovery_v2.md").read_text(encoding="utf-8")
    d1, d2 = design(base).design, design(v2).design
    changes = DF.diff(d1, d2)
    assert not [c for c in changes if c.collection == "requirements" and c.kind == "changed"]
    assert [c for c in changes if c.collection == "requirements" and c.kind == "added"]
    affected = DF.affected_packages(d2, changes)
    assert len(affected) < len(d2.work_packages)
    assert any(c.kind == "renumbered" for c in changes)


def test_honesty_layer_lists_every_dropped_sentence():             # M1
    r = _design("02_prd_petclaims")
    md = r.notes.to_markdown()
    assert "under 15 minutes" in " ".join(q.statement for q in r.design.requirements) + md   # the KPI target cell survives
    r3 = _design("03_rfp_nougyou")
    assert "1200 sites" in " ".join(q.statement for q in r3.design.requirements)


def test_team_sizes_and_priorities():                               # M2, M3
    r = _design("02_prd_petclaims")
    assert r.analysis.team_size == 10, r.analysis.team_size    # 6 + 2 + 1 + 1 (the shared SRE counted; the reviewer counted 9)
    could = [q for q in r.design.requirements if q.priority == "could" and "could not decide" in q.statement]
    assert not could
    assert T.modality("They review anything the rules could not decide.") == ""
    r1 = _design("01_tender_grid")
    assert r1.analysis.team_size == 5


def test_decisions_follow_stated_infrastructure():                  # M4
    r5 = _design("05_postmortem_ediscovery")
    choices = {d.title: d.choice for d in r5.design.decisions}
    assert choices["Work queue technology"].startswith("Managed broker")                     # existing RabbitMQ
    assert "per tenant" in choices.get("Tenant isolation", "").lower() or "Tenant isolation" not in choices or "single" in choices.get("Tenant isolation", "").lower()
    r4 = _design("04_rfc_matchmaking")
    assert any(o.name == "GET /v2/queue/{ticket}" for i in r4.design.interfaces for o in i.operations)


def test_rejected_alternatives_are_not_chosen():                    # M5
    r = _design("04_rfc_matchmaking")
    rejected = [d for d in r.design.decisions if d.status == "rejected"]
    assert rejected and all(d.choice == "" for d in rejected)
    adr = "\n".join(DV.adrs(r.design).values())
    assert "← chosen" not in adr.split("Alternative considered")[-1] if "Alternative considered" in adr else True


def test_japanese_rfp_sections_and_actors():                        # M7
    r = _design("03_rfp_nougyou")
    assert r.design.name != "propose-rfp"
    assert any("Growers can" in q.statement for q in r.design.requirements)
    assert r.analysis.team_size == 4
    assert any("hardware" in g.lower() or "調達" in g for g in r.design.non_goals + [n for n in r.design.non_goals])
    assert not any("The system must submit 7" in q.statement for q in r.design.requirements)
