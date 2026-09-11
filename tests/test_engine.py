"""The design engine: deterministic, faithful to the input, lint-clean, and honest about its limits."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sekkei
from sekkei import rules as R
from sekkei.brief import render_brief
from sekkei.engine import analyse, design
from sekkei.engine import text as T

FIX = Path(__file__).parent / "fixtures"
FIXTURES = sorted(p.stem for p in FIX.glob("*.md"))


def load(name: str) -> str:
    return (FIX / f"{name}.md").read_text(encoding="utf-8")


# --- text -------------------------------------------------------------------

def test_quantities_grammar():
    qs = {q.raw: q for q in T.quantities("p95 latency under 5 s at 1,000 events/s; 5,000 endpoints; 2 GB; 99.9 %; HMAC-SHA256; 429 Retry-After")}
    assert qs["1,000"].kind == "rate" and qs["1,000"].value == 1000 and qs["1,000"].unit == "events /s"
    assert qs["5 s"].comparator == "under" and qs["5 s"].target() == "< 5 s"
    assert qs["5,000"].kind == "count" and qs["5,000"].noun == "endpoints"
    assert qs["2 GB"].kind == "size" and qs["99.9 %"].kind == "percent"
    assert "256" not in qs and qs["429"].kind == "code"


def test_segmentation_sections_bullets_and_modality():
    text = "# Title\n\nIntro sentence.\n\nFunctional\n- Users can create items.\n- Items may be tagged.\n\nNon-functional\n- Search returns within 300 ms.\n\nOut of scope\n- Billing.\n"
    ss = T.segment(text)
    assert [(s.section, s.is_bullet, s.modality) for s in ss] == [
        ("", False, ""), ("functional", True, ""), ("functional", True, "could"), ("nonfunctional", True, ""), ("nongoal", True, "")]
    assert T.verb_of("delivered") == "deliver" and T.verb_of("retried") == "retry" and T.verb_of("delivery") == ""
    assert T.title_of(text) == "Title"


# --- analysis ---------------------------------------------------------------

def test_analysis_of_the_webhook_spec():
    an = analyse(load("webhooks"))
    assert {"async_delivery", "signing", "admin_api", "event_ingest", "observability", "health_policy", "notification"} <= set(an.patterns)
    assert {"durability", "isolation", "performance", "operability"} <= set(an.qualities)
    assert {"postgres", "redis", "containers"} <= an.constraints and an.languages == ["python"] and an.team_size == 3
    kinds = {u.id: u.kind for u in an.requirements}
    assert list(kinds.values()).count("constraint") == 2 and list(kinds.values()).count("nonfunctional") >= 3
    nf = [u for u in an.requirements if u.kind == "nonfunctional" and u.metric and "p95" in u.metric[0]]
    assert nf and nf[0].metric[1] == "< 5 s"
    assert an.unrecognised == []
    assert [u for u in an.requirements if u.sentence.text.startswith("#")] == []


def test_non_goals_are_kept_out_of_requirements_and_pattern_matching():
    an = analyse(load("inventory"))
    assert "Purchasing and supplier management." in an.non_goals
    assert all("supplier" not in u.sentence.text for u in an.requirements)
    assert "payments" not in an.patterns


# --- engine -----------------------------------------------------------------

@pytest.mark.parametrize("name", FIXTURES)
def test_every_fixture_yields_a_lint_clean_design(name):
    r = design(load(name))
    assert r.ok, R.format_text(r.diagnostics)
    assert [d for d in R.lint(r.design, strict=True, disable=["Q"]) if d.severity != "info"] == []


@pytest.mark.parametrize("name", FIXTURES)
def test_engine_is_deterministic(name):
    a = sekkei.dumps(design(load(name)).design)
    b = sekkei.dumps(design(load(name)).design)
    assert a == b


@pytest.mark.parametrize("name", FIXTURES)
def test_fidelity_every_bullet_is_a_requirement_verbatim(name):
    text = load(name)
    r = design(text)
    statements = {q.statement for q in r.design.requirements}
    an = r.analysis
    for s in an.sentences:
        if s.is_bullet and s.section in ("functional", "nonfunctional", "constraint"):
            assert s.text in statements, s.text
    for s in an.sentences:
        if s.section == "nongoal":
            assert s.text not in statements
    # every element has a trace
    for coll in ("requirements", "components", "interfaces", "decisions", "risks", "work_packages"):
        for obj in getattr(r.design, coll):
            assert obj.id in r.trace, obj.id


def test_webhook_design_has_the_architecture_a_human_would_draw():
    r = design(load("webhooks"))
    d = r.design
    names = {c.name for c in d.components}
    assert {"Work queue", "Worker", "Scheduler", "Signer", "Secret store", "Admin HTTP API", "Ingest API",
            "Outbound HTTP client", "Health policy", "Notifier", "Observability", "Customer endpoint"} <= names
    assert "Public HTTP API" not in names  # the admin API is the surface; no redundant public API
    titles = {x.title: x.choice for x in d.decisions}
    assert titles["Primary store"] == "PostgreSQL"
    assert titles["Work queue technology"].startswith("PostgreSQL table")
    assert titles["Per-target isolation of outbound work"].startswith("Partition the queue")
    assert titles["Outbound request safety"].startswith("Resolve and block")
    assert titles["Process topology"].startswith("One image")
    # the backoff schedule from the text lands in the scheduler contract, not in prose
    sched = next(i for i in d.interfaces if i.name.startswith("Scheduler"))
    assert "1 min" in sched.operations[0].pre and "12 h" in sched.operations[0].pre and "5 attempts" in sched.operations[0].pre
    secrets = next(i for i in d.interfaces if i.name.startswith("Secret store"))
    assert "24 h" in secrets.operations[1].pre
    admin = next(i for i in d.interfaces if i.name.startswith("Admin"))
    ops = {o.name for o in admin.operations}
    assert {"POST /endpoints", "GET /endpoints", "DELETE /endpoints/{id}", "POST /secrets/{id}/rotate"} <= ops
    assert not any("json" in o for o in ops)
    # entities and flows from the patterns
    assert {"Event", "WorkItem", "DeliveryAttempt", "Endpoint", "Secret"} <= {e.name for e in d.entities}
    assert any(f.name == "Deliver a work item" for f in d.flows)
    # non-functional requirements get metric checks in the packages that carry them
    metric_checks = [a for w in d.work_packages for a in w.acceptance if a.kind == "metric"]
    assert metric_checks and all(d.requirement(a.metric).kind == "nonfunctional" for a in metric_checks)
    # every package is small and its files are unique across packages
    files = [f for w in d.work_packages for f in w.files]
    assert len(files) == len(set(files)) and all(len(w.components) <= 3 for w in d.work_packages)
    assert not r.review.unrecognised and not r.review.unaddressed and not r.review.generic


def test_inventory_design_uses_the_stated_identity_provider_and_concurrency_control():
    r = design(load("inventory"))
    titles = {x.title: x.choice for x in r.design.decisions}
    assert titles["Caller authentication"].startswith("OAuth2 / OIDC")
    assert titles["Concurrency control for conflicting writes"].startswith("Optimistic")
    assert r.design.conventions.language == "typescript" and r.design.conventions.test_command == "npx vitest run"
    assert all(f.endswith((".ts",)) for w in r.design.work_packages for f in w.files)
    api = next(i for i in r.design.interfaces if i.name.startswith("Public HTTP API"))
    assert {"POST /items", "DELETE /items/{id}", "POST /items/{id}/move"} <= {o.name for o in api.operations}
    assert any(c.name == "Audit log" for c in r.design.components)
    assert not r.review.unrecognised


def test_cli_tool_design_is_a_cli_with_a_persistent_preset_store():
    r = design(load("cli_tool"))
    d = r.design
    assert any(c.kind == "cli" for c in d.components) and not any(c.kind == "service" for c in d.components)
    assert {x.title: x.choice for x in d.decisions}["Primary store"] in ("SQLite", "Files (JSON/CSV on disk)")
    assert "Standard library only; no third-party runtime dependencies." in d.conventions.rules
    cli = next(i for i in d.interfaces if i.kind == "cli")
    assert any(o.name.startswith("run ") for o in cli.operations) and any(o.name.startswith("print ") for o in cli.operations)
    assert any(rid == "R-5" for rid, _ in r.review.unrecognised)  # "save a named filter preset": honestly unrecognised


def test_novel_domain_is_placed_by_synthesis_and_says_so():
    r = design(load("novel"))
    assert r.ok
    assert r.review.unrecognised and r.placements
    assert any(p.how == "synthesised" for p in r.placements)
    md = r.review.to_markdown()
    assert "did not recognise" in md
    # a text that matches nothing at all gets the layered fallback and says so
    r0 = design("# Hive counter\n\nFunctional\n- The device counts bees entering the hive and keeps the tally on an SD card.\n", assume=False)
    assert r0.ok and r0.review.generic and "Generic components" in r0.review.to_markdown()
    assert {x.title: x.choice for x in r.design.decisions}["Primary store"].startswith("Files")  # "no database"
    assert r.design.conventions.language == "rust"
    assert any(k.description.startswith("Parts of the requirements were not recognised") for k in r.design.risks)


def test_engine_output_feeds_the_rest_of_the_toolchain():
    r = design(load("webhooks"))
    d = r.design
    text = render_brief(d, d.work_packages[-1].id)
    assert "## 4. Use, do not modify" in text and "## 7. Acceptance" in text
    md = sekkei.render_markdown(d)
    assert "## Decisions" in md and "```mermaid" in md
    tj = r.trace_json()
    assert set(tj) >= {"patterns", "qualities", "elements", "sentences"}
    json.dumps(tj)  # serialisable


def test_cli_design_command(tmp_path, monkeypatch, capsys):
    from sekkei.cli import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / "req.md").write_text(load("webhooks"), encoding="utf-8")
    code = main(["design", "req.md", "-o", "d.json", "--render", "D.md", "--review", "R.md", "--trace", "t.json"])
    out = capsys.readouterr().out
    assert code == 0 and "OK: no diagnostics" in out and "recognised patterns" in out
    assert (tmp_path / "d.json").exists() and (tmp_path / "D.md").exists() and (tmp_path / "R.md").exists()
    assert "elements" in json.loads((tmp_path / "t.json").read_text())
    assert main(["lint", "-d", "d.json"]) == 0
    assert main(["plan", "-d", "d.json"]) == 0
    assert main(["brief", "WP-1", "-d", "d.json", "--no-record"]) == 0
