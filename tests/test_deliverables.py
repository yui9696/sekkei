"""The hand-over package: derived, deterministic, and never inventing a number."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from sekkei import deliverables as DV
from sekkei.engine import design

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def saas():
    return design((FIX / "saas.md").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pkg(saas):
    return DV.package(saas)


def test_package_has_every_document(pkg, saas):
    names = set(pkg.files)
    for n in ("design.json", "DESIGN.md", "NOTES.md", "00_EXECUTIVE_SUMMARY.md", "C4.md", "RISK_REGISTER.md", "FMEA.md",
              "ROADMAP.md", "RACI.md", "SLO.md", "COST_MODEL.md", "RUNBOOKS.md", "INDEX.md"):
        assert n in names
    assert sum(1 for n in names if n.startswith("adr/")) == len(saas.design.decisions)


def test_package_is_deterministic(saas):
    a = DV.package(saas).files
    b = DV.package(design((FIX / "saas.md").read_text(encoding="utf-8"))).files
    assert a == b


def test_slo_error_budget_is_computed_not_typed(pkg):
    slo = pkg.files["SLO.md"]
    assert "error budget 43.2 min / 30 days = (100 − 99.9) % × 43,200 min" in slo
    assert "<= 400 ms |" in slo and "ms ms" not in slo         # unit printed once


def test_cost_model_never_guesses_prices(saas):
    md = DV.cost_model(saas.design, saas.notes)
    assert "| ? | ? |" in md and "Total per month:" in md
    assert re.search(r"Total per month: [\d.]+ × instance_month", md)   # a formula, not a number
    lines = DV.cost_lines(saas.design, saas.notes, {"instance_month": 10, "db_month": 100, "storage_gb_month": 0.1})
    priced = [ln for ln in lines if ln.price is not None]
    assert priced and all(ln.monthly == ln.qty * ln.price for ln in priced)
    md2 = DV.cost_model(saas.design, saas.notes, {"instance_month": 10, "db_month": 100, "storage_gb_month": 0.1})
    assert "external_email_provider" in md2                    # still unknown: stays symbolic


def test_roadmap_and_summary_agree_on_the_calendar(pkg, saas):
    total = saas.notes.effort.calendar_days
    assert f"{total} working days end to end" in pkg.files["ROADMAP.md"]
    assert f"about **{total} working days**" in pkg.files["00_EXECUTIVE_SUMMARY.md"]
    assert sum(saas.notes.effort.phase_days) == total


def test_fmea_severity_follows_must_requirements(saas):
    md = DV.fmea(saas.design)
    store_rows = [ln for ln in md.splitlines() if ln.startswith("| C-1 ")]
    assert store_rows and all("| high |" in ln for ln in store_rows)   # the store carries must-haves transitively
    ext = [ln for ln in md.splitlines() if "Email provider" in ln and "| unavailable |" in ln]
    assert ext and "timeouts and retries" in ext[0]


def test_risk_register_is_sorted_by_score_and_owned(saas):
    md = DV.risk_register(saas.design)
    scores = [int(ln.split("|")[5].strip()) for ln in md.splitlines() if ln.startswith("| K-")]
    assert scores == sorted(scores, reverse=True)
    assert any("WP-" in ln for ln in md.splitlines() if ln.startswith("| K-"))


def test_c4_names_every_external_and_actor(saas):
    md = DV.c4_markdown(saas.design, saas.analysis.actors)
    for c in saas.design.components:
        if c.kind == "external":
            assert c.name in md
    assert "```mermaid" in md and "subgraph" in md


def test_raci_uses_the_team_size(saas):
    md = DV.raci(saas.design, saas.notes.effort)
    assert "Engineer 4" in md and "Engineer 5" not in md
    assert "Security reviewer" in md


def test_cli_deliver_writes_the_package(tmp_path):
    out = tmp_path / "dv"
    r = subprocess.run([sys.executable, "-m", "sekkei.cli", "deliver", str(FIX / "saas.md"), "-o", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (out / "INDEX.md").exists() and (out / "adr").is_dir()
    bad = tmp_path / "bad.json"
    bad.write_text("[1,2]", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "sekkei.cli", "deliver", str(FIX / "saas.md"), "-o", str(out), "--prices", str(bad)], capture_output=True, text=True)
    assert r.returncode == 2
    prices = tmp_path / "p.json"
    prices.write_text(json.dumps({"instance_month": 20}), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "sekkei.cli", "deliver", str(FIX / "saas.md"), "-o", str(out), "--prices", str(prices)], capture_output=True, text=True)
    assert r.returncode == 0
    assert "| 20 |" in (out / "COST_MODEL.md").read_text(encoding="utf-8")
