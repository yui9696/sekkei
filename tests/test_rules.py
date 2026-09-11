"""Planted-defect battery: one valid design with zero diagnostics, and for every rule a
mutation that must trigger exactly that rule id. The meta-test fails if a rule has no
planted defect, so the linter cannot be vacuously green."""
from __future__ import annotations

import pytest

from sekkei import model as M
from sekkei import rules as R
from sekkei.examples import starter_design

PLANTED: dict[str, object] = {}


def planted(rule_id: str):
    def deco(fn):
        PLANTED[rule_id] = fn
        return fn

    return deco


# --- S ---------------------------------------------------------------------
@planted("S001")
def _(d): d.components[1].id = "C-1"
@planted("S002")
def _(d): d.requirements[0].id = "1 bad id"
@planted("S003")
def _(d): d.risks[0].id = "RISK-1"
@planted("S004")
def _(d): d.components[1].requires.append("I-99")
@planted("S005")
def _(d): d.work_packages[0].size = "XL"
@planted("S006")
def _(d): d.unknown_keys.append(("$", "workpackages"))
@planted("S007")
def _(d): d.components[0].responsibility = ""
@planted("S008")
def _(d): d.work_packages.clear()
# --- C ---------------------------------------------------------------------
@planted("C001")
def _(d): d.components[0].requires.append("I-1")
@planted("C002")
def _(d): d.components[0].requires.append("I-2")
@planted("C003")
def _(d): d.flows[0].steps[0].to = "C-2"
@planted("C004")
def _(d): d.components[1].requires.remove("I-1")
@planted("C005")
def _(d): d.work_packages[0].depends_on.append("WP-2")
@planted("C006")
def _(d): d.work_packages[1].implements.append("I-1")
@planted("C007")
def _(d): d.work_packages[1].depends_on.clear()
@planted("C008")
def _(d): d.decisions[0].choice = "postgres"
@planted("C009")
def _(d): d.work_packages[0].depends_on.append("WP-1")
# --- V ---------------------------------------------------------------------
@planted("V001")
def _(d): d.components[1].satisfies.remove("R-1")
@planted("V002")
def _(d): d.work_packages[1].satisfies.remove("R-1")
@planted("V003")
def _(d): d.components.append(M.Component("C-3", "Cache", "Caches listings.", satisfies=["R-2"]))
@planted("V004")
def _(d): d.work_packages[0].implements.clear()
@planted("V005")
def _(d): d.work_packages[1].acceptance.clear()
@planted("V006")
def _(d): d.requirements[2].metric = None
@planted("V007")
def _(d): d.risks[0].mitigation = ""
@planted("V008")
def _(d):
    d.interfaces.append(M.Interface("I-3", "Unused", owner="C-1"))
    d.work_packages[0].implements.append("I-3")
@planted("V009")
def _(d): d.components[0].satisfies.clear()
@planted("V010")
def _(d): d.work_packages[0].acceptance[0].command = ""
@planted("V011")
def _(d): d.decisions[0].options.pop()
# --- A ---------------------------------------------------------------------
@planted("A001")
def _(d): d.work_packages[0].files.clear()
@planted("A002")
def _(d):
    d.work_packages[1].depends_on.clear()
    d.work_packages[1].files.append("app/store.py")
@planted("A003")
def _(d): d.work_packages[0].components += ["C-2"] * 4
@planted("A004")
def _(d): d.work_packages[0].acceptance[1].metric = "R-1"
@planted("A005")
def _(d): d.conventions.test_command = ""
# --- Q ---------------------------------------------------------------------
@planted("Q001")
def _(d): d.requirements[0].statement = "The API must be fast and robust for every client."
@planted("Q002")
def _(d): d.requirements[0].statement = "Create a todo."
@planted("Q003")
def _(d): d.work_packages[0].goal = "Store."


def fired(design: M.Design) -> set[str]:
    return {x.rule for x in R.lint(design)}


def test_valid_fixture_has_zero_diagnostics():
    assert R.lint(starter_design()) == []


@pytest.mark.parametrize("rule_id", sorted(PLANTED))
def test_planted_defect_triggers_its_rule(rule_id):
    d = starter_design()
    PLANTED[rule_id](d)
    assert rule_id in fired(d), f"{rule_id} did not fire on its planted defect"


def test_every_rule_has_a_planted_defect():
    assert set(PLANTED) == set(R.RULES), {
        "rules without a planted defect": sorted(set(R.RULES) - set(PLANTED)),
        "planted defects for unknown rules": sorted(set(PLANTED) - set(R.RULES)),
    }


def test_severity_follows_priority_for_coverage_rules():
    d = starter_design()
    d.requirements[0].priority = "could"
    d.components[1].satisfies.remove("R-1")
    d.work_packages[1].satisfies.remove("R-1")
    sev = {x.rule: x.severity for x in R.lint(d) if x.where == "R-1"}
    assert sev == {"V001": "info", "V002": "info"}
    d.requirements[0].priority = "should"
    sev = {x.rule: x.severity for x in R.lint(d) if x.where == "R-1"}
    assert sev == {"V001": "warning", "V002": "warning"}


def test_strict_promotes_warnings_and_disable_filters():
    d = starter_design()
    d.risks[0].mitigation = ""  # V007 warning
    assert [x.severity for x in R.lint(d)] == ["warning"]
    assert [x.severity for x in R.lint(d, strict=True)] == ["error"]
    assert R.lint(d, disable=["V007"]) == []
    assert R.lint(d, disable=["V"]) == []
    assert R.has_errors(R.lint(d, strict=True)) and not R.has_errors(R.lint(d))


def test_diagnostics_are_sorted_and_carry_hints():
    d = starter_design()
    d.risks[0].mitigation = ""  # warning
    d.work_packages[0].files.clear()  # error A001
    diags = R.lint(d)
    assert [x.severity for x in diags] == ["error", "warning"]
    assert all(x.hint for x in diags)
    text = R.format_text(diags)
    assert "A001" in text and "hint:" in text and "1 error(s), 1 warning(s)" in text
    assert R.format_text([]) == "OK: no diagnostics\n"


def test_rule_table_lists_every_rule():
    table = R.rule_table()
    assert all(rid in table for rid in R.RULES)


def test_vague_word_rule_is_silenced_by_a_metric():
    d = starter_design()
    d.requirements[2].statement = "Listing must be fast."
    assert "Q001" not in fired(d)  # R-3 has a metric
    d.requirements[0].statement = "Creating must be fast."
    assert "Q001" in fired(d)
