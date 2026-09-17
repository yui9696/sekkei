from __future__ import annotations

import pytest

from sekkei import graph as G
from sekkei import model as M
from sekkei.examples import starter_design


def test_component_graph_follows_interface_ownership():
    d = starter_design()
    assert G.component_graph(d) == {"C-1": set(), "C-2": {"C-1"}}
    assert G.layers(d) == [["C-1"], ["C-2"]]


def test_find_cycle_and_waves():
    assert G.find_cycle({"a": {"b"}, "b": {"c"}, "c": set()}) is None
    assert G.find_cycle({"a": {"b"}, "b": {"a"}}) == ["a", "b", "a"]
    assert G.waves({"a": {"b"}, "b": {"c"}, "c": set(), "d": set()}) == [["c", "d"], ["b"], ["a"]]
    with pytest.raises(ValueError, match="cycle"):
        G.waves({"a": {"b"}, "b": {"a"}})
    assert G.transitive({"a": {"b"}, "b": {"c"}, "c": set()}, "a") == {"b", "c"}


def test_critical_path_uses_size_weights():
    d = starter_design()  # WP-1 (S=2) -> WP-2 (M=5), person-days: one table with the notes
    assert G.critical_path(d) == (7, ["WP-1", "WP-2"])
    d.work_packages[1].size = "L"
    assert G.critical_path(d) == (12, ["WP-1", "WP-2"])
    d.work_packages.append(M.WorkPackage("WP-3", "x", size="L"))
    assert G.critical_path(d) == (12, ["WP-1", "WP-2"])  # WP-3 alone is 10; ties broken deterministically
    assert G.critical_path(M.Design(name="empty")) == (0, [])


def test_implied_edges_and_ready():
    d = starter_design()
    assert G.implied_package_edges(d) == []
    d.work_packages[1].depends_on.clear()
    assert G.implied_package_edges(d) == [("WP-2", "WP-1", "I-1")]
    assert G.ready_packages(d, []) == ["WP-1", "WP-2"]
    d.work_packages[1].depends_on.append("WP-1")
    assert G.ready_packages(d, []) == ["WP-1"]
    assert G.ready_packages(d, ["WP-1"]) == ["WP-2"]
    assert G.ready_packages(d, ["WP-1", "WP-2"]) == []


def test_traceability_includes_metric_checks():
    d = starter_design()
    tr = G.traceability(d)
    assert tr["R-3"] == {"components": ["C-1"], "packages": ["WP-1"], "acceptance": ["A-1", "A-2"]}
    assert tr["R-1"]["packages"] == ["WP-2"]


@pytest.mark.parametrize("path,scope,expected", [
    ("app/store.py", "app/store.py", True),
    ("app/store.py", "app", True),
    ("app/store.py", "app/", True),
    ("app/store.py", "app/store", False),
    ("app/storex.py", "app/store.py", False),
    ("apps/x.py", "app", False),
    ("/app/x.py", "app", True),
])
def test_in_scope(path, scope, expected):
    assert G.in_scope(path, scope) is expected
