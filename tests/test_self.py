"""Dogfood: sekkei's own design must lint clean and match the code in this repository."""
from __future__ import annotations

import time
from pathlib import Path

import sekkei
from sekkei import drift, rules

ROOT = Path(__file__).resolve().parent.parent
SELF = ROOT / "examples" / "self" / "design.json"


def test_self_design_lints_clean_even_in_strict_mode():
    d = sekkei.load(SELF)
    assert rules.lint(d, strict=True) == []


def test_self_design_matches_the_code():
    d = sekkei.load(SELF)
    findings = drift.check(d, ROOT)
    assert [f for f in findings if f.severity != "info"] == [], [str(f) for f in findings]


def test_drift_check_is_not_vacuous_on_this_repo():
    d = sekkei.load(SELF)
    d.component("C-5").requires.remove("I-7")  # brief.py really imports state.py
    kinds = {(f.kind, f.where) for f in drift.check(d, ROOT) if f.severity == "error"}
    assert ("undeclared_dependency", "C-5") in kinds
    d = sekkei.load(SELF)
    d.interface("I-3").operations[0].name = "no_such_function"
    kinds = {(f.kind, f.where) for f in drift.check(d, ROOT) if f.severity == "error"}
    assert ("missing_symbol", "I-3") in kinds


def test_self_design_is_reproducible_from_its_source():
    import runpy

    ns = runpy.run_path(str(SELF.with_name("build_design.py")))
    assert sekkei.to_dict(ns["b"].build()) == sekkei.to_dict(sekkei.load(SELF))


def test_r8_lint_plus_check_time_budget():
    d = sekkei.load(SELF)
    t0 = time.perf_counter()
    rules.lint(d)
    drift.check(d, ROOT)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, elapsed  # R-8 target is 1 s on a laptop; 5 s guards against CI noise
