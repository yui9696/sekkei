"""The second red team's specifications (written by an independent reviewer as engineers write them) and what it found."""
from __future__ import annotations

from pathlib import Path

import pytest

from sekkei import deliverables as DV
from sekkei import model as M
from sekkei.engine import design, structure as S, text as T

REAL2 = Path(__file__).parent.parent / "examples" / "real2"


def _design(name: str):
    return design((REAL2 / f"{name}.md").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(p.stem for p in REAL2.glob("*.md")))
def test_specs_design_lint_clean_and_deterministic(name):
    text = (REAL2 / f"{name}.md").read_text(encoding="utf-8")
    r = design(text)
    assert r.ok, [str(d) for d in r.diagnostics if d.severity == "error"]
    assert M.dumps(r.design) == M.dumps(design(text).design)


def test_jira_epic_stories_as_prose_are_requirements():           # B1
    r = _design("02_jira_epic_streaming")
    stmts = " ".join(q.statement for q in r.design.requirements)
    for needle in ("create a clip of the last 30 seconds", "within 10 seconds", "highlights rail within 2 minutes", "starts within 3 seconds",
                   "geo-blocked", "removed automatically", "500 clip requests per second", "30 days"):
        assert needle in stmts, needle
    assert r.design.name == "live-to-vod-clipping-and-playback-for-the-sports-app"
    assert r.analysis.team_size == 6
    assert "go" in r.analysis.languages
    assert "Geospatial index" not in {c.name for c in r.design.components}
    assert "Signer" not in {c.name for c in r.design.components}
    api = [i for i in r.design.interfaces if i.kind == "http" and r.design.component(i.owner).kind != "external"]
    assert any(i.operations for i in api), "the public API must carry the viewers' and editors' operations"


def test_status_code_shaped_rates_are_rates():                      # B2
    qs = {q.value: q for q in T.quantities("up to 500 clip requests per second; 400 orders per second; returns 429 with Retry-After")}
    assert qs[500].kind == "rate" and qs[400].kind == "rate" and qs[429].kind == "code"


def test_20ms_and_nearest_comparator():                             # B3
    q = T.quantities("need <20ms p99")[0]
    assert (q.value, q.unit, q.kind, q.comparator) == (20.0, "ms", "latency", "<")
    q = T.quantities("sent to suppliers over EDI (AS2) within 15 minutes of approval")[0]
    assert q.comparator == "within"


def test_japanese_prohibition_keeps_its_polarity():                 # B4
    from sekkei.engine import ja
    r = ja.rewrite_sentence("測定値は改ざん不可であること。")
    assert "never" in r.english or "not" in r.english
    d = _design("04_youken_medical")
    md = d.notes.to_markdown()
    assert "Readings allowed" not in md
    assert "attending physicians" in md.lower()


def test_brownfield_change_request_is_not_greenfield():             # B5
    r = _design("06_brownfield_cr")
    assert not any("Feature flag per marketplace" in g for g in r.design.non_goals)
    assert not any("existing PaymentIntents" in g for g in r.design.non_goals)
    assert "legacy_integration" in r.analysis.patterns
    assert not any("greenfield" in d.choice.lower() for d in r.design.decisions)
    choices = {d.title: d.choice for d in r.design.decisions}
    assert "In-process timers" not in choices.get("Where delayed retries wait", "")
    assert choices["Work queue technology"].startswith("Managed broker")
    stmts = " ".join(q.statement for q in r.design.requirements)
    assert "never double-pay" in stmts and "300 ms p95" in stmts


def test_metadata_table_and_open_questions():                       # M1, M11
    r = _design("01_confluence_trading")
    stmts = [q.statement for q in r.design.requirements]
    assert not any("Priya" in s or "DRAFT" in s for s in stmts)
    assert not any("processor" in c.name and c.name.split()[0] in ("Draft", "Go-live", "Platform") for c in r.design.components)
    assert r.analysis.team_size == 6                                # 5 engineers, 1 SRE
    assert r.analysis.structure.todos and "barrier orders" in r.analysis.structure.todos[0]
    summary = DV.executive_summary(r.design, r.notes)
    assert "Open questions: 2" in summary
    choices = {d.title: d.choice for d in r.design.decisions}
    assert "In-memory" not in choices["Work queue technology"]
    assert choices["Caller authentication"].startswith("OAuth2 / OIDC")     # EntitleX is an entitlement service
    assert "data_residency" in r.analysis.constraints                       # "must not leave the UK region"
    assert "feature_flags" not in r.analysis.patterns                       # a kill switch is not a rollout flag


def test_meeting_notes_paragraphs_are_read():                       # M2, B1
    r = _design("03_meeting_notes_mlplatform")
    stmts = " ".join(q.statement for q in r.design.requirements)
    assert "<20ms p99" in stmts and "Scoring job must finish" in stmts and "model lineage is mandatory" in stmts
    assert r.analysis.team_size == 3
    assert "Mobile app" not in {c.name for c in r.design.components}    # "offline training reads" is not a mobile app
    assert "no_network" not in r.analysis.constraints
    assert any("GPU training" in g or "AutoML" in g for g in r.design.non_goals)


def test_slack_paragraph_every_sentence_read():
    r = _design("05_slack_devtool")
    assert len([q for q in r.design.requirements if not q.rationale.startswith("assumed")]) >= 7
    assert r.analysis.team_size == 2
    assert any("<100ms" in q.statement for q in r.design.requirements)


def test_pdf_paste_cleanup():                                        # M9
    c = S.canonicalise((REAL2 / "pdf_paste.md").read_text(encoding="utf-8"))
    assert "Page 2 of 3" not in c.text and "auto-approved at 09:00" in c.text
    assert "within 15 minutes of approval" in c.text
    r = design((REAL2 / "pdf_paste.md").read_text(encoding="utf-8"))
    assert not any(q.statement.strip() in ("00.", "3") for q in r.design.requirements)
    assert r.analysis.team_size == 6


def test_two_line_table_header_and_table_only():
    c = S.canonicalise((REAL2 / "table_2line_header.md").read_text(encoding="utf-8"))
    assert "(should)" in c.text
    r = design((REAL2 / "table_only.md").read_text(encoding="utf-8"))
    assert r.ok and len(r.design.requirements) >= 3


def test_deliver_twice_removes_stale_files(tmp_path):              # M10
    from sekkei.engine import design as run
    big = run((REAL2 / "02_jira_epic_streaming.md").read_text(encoding="utf-8"))
    DV.package(big).write(tmp_path)
    (tmp_path / "MY_NOTES.md").write_text("mine", encoding="utf-8")
    n_adr = len(list((tmp_path / "adr").glob("*.md")))
    small = run((REAL2.parent / "real" / "tiny.md").read_text(encoding="utf-8"))
    pk = DV.package(small)
    pk.write(tmp_path)
    assert len(list((tmp_path / "adr").glob("*.md"))) < n_adr
    assert (tmp_path / "MY_NOTES.md").read_text(encoding="utf-8") == "mine"
    assert pk.removed_stale


def test_slo_rows_are_availability_latency_or_loss_only():           # M8
    r = _design("06_brownfield_cr")
    slo = DV.slos(r.design)
    assert "1.2M payments/day" not in slo.split("| source |")[0] if "| source |" in slo else True
    for line in slo.splitlines():
        if line.startswith("| R-"):
            assert "ms ms" not in line and "seconds seconds" not in line
            assert "Volume:" not in line and "7 years" not in line
    r2 = _design("01_confluence_trading")
    slo2 = DV.slos(r2.design)
    assert "stated window 07:00–18:00" in slo2 or "stated window" in slo2
