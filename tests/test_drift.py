"""Drift checks against a synthetic repository built in a temp dir."""
from __future__ import annotations

from pathlib import Path

import pytest

from sekkei import drift as D
from sekkei.examples import starter_design

STORE = '''
class Store:
    def add(self, title):
        return 1

    def list_all(self):
        return []
'''
API = '''
from .store import Store

def app():
    return Store()
'''


def make_repo(tmp_path: Path, store: str = STORE, api: str = API) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "store.py").write_text(store)
    (tmp_path / "app" / "api.py").write_text(api)
    return tmp_path


def errors(findings):
    return [(f.kind, f.where) for f in findings if f.severity == "error"]


def test_consistent_repo_has_no_errors(tmp_path):
    root = make_repo(tmp_path)
    fs = D.check(starter_design(), root)
    assert errors(fs) == []
    assert ("not_checkable", "I-2") in [(f.kind, f.where) for f in fs]  # http interface, honestly reported


def test_missing_path_and_missing_symbol(tmp_path):
    root = make_repo(tmp_path, store="class Store:\n    def add(self, title):\n        return 1\n")
    (root / "app" / "api.py").unlink()
    fs = D.check(starter_design(), root)
    assert ("missing_path", "C-2") in errors(fs)
    assert ("missing_symbol", "I-1") in errors(fs)
    assert any("list_all" in f.message for f in fs)


def test_param_mismatch_is_a_warning(tmp_path):
    root = make_repo(tmp_path, store="class Store:\n    def add(self, name):\n        return 1\n    def list_all(self):\n        return []\n")
    fs = D.check(starter_design(), root)
    assert errors(fs) == []
    w = [f for f in fs if f.kind == "param_mismatch"]
    assert len(w) == 1 and "['title']" in w[0].message and "['name']" in w[0].message


def test_varargs_skip_param_check(tmp_path):
    root = make_repo(tmp_path, store="class Store:\n    def add(self, *args, **kw):\n        return 1\n    def list_all(self):\n        return []\n")
    assert [f for f in D.check(starter_design(), root) if f.kind == "param_mismatch"] == []


@pytest.mark.parametrize("import_line", [
    "from .store import Store",
    "from app.store import Store",
    "import app.store",
    "from app import store",
    "from . import store",
])
def test_undeclared_dependency_is_found_for_every_import_form(tmp_path, import_line):
    root = make_repo(tmp_path, api=import_line + "\n")
    d = starter_design()
    d.components[1].requires.clear()  # C-2 no longer declares I-1
    fs = D.check(d, root)
    assert ("undeclared_dependency", "C-2") in errors(fs), [str(f) for f in fs]


def test_declared_but_unused_dependency_is_info(tmp_path):
    root = make_repo(tmp_path, api="def app():\n    return None\n")
    fs = D.check(starter_design(), root)
    assert errors(fs) == []
    assert ("unused_dependency", "C-2") in [(f.kind, f.where) for f in fs]


def test_component_directories_and_longest_prefix(tmp_path):
    root = tmp_path
    (root / "pkg" / "sub").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "a.py").write_text("from pkg.sub import b\n")
    (root / "pkg" / "sub" / "__init__.py").write_text("")
    (root / "pkg" / "sub" / "b.py").write_text("def f(x):\n    return x\n")
    d = starter_design()
    d.components[0].path = "pkg/sub"      # C-1 = the sub-package
    d.components[1].path = "pkg"          # C-2 = everything else in pkg
    d.interfaces[0].kind = "module"
    d.interfaces[0].operations = d.interfaces[0].operations[:1]
    d.interfaces[0].operations[0].name = "f"
    d.interfaces[0].operations[0].inputs[0].name = "x"
    fs = D.check(d, root)
    assert errors(fs) == []  # pkg/a.py (C-2) imports pkg/sub/b.py (C-1) and C-2 requires I-1
    d.components[1].requires.clear()
    assert ("undeclared_dependency", "C-2") in errors(D.check(d, root))


def test_scope_violations():
    d = starter_design()
    assert D.scope_violations(d, "WP-1", ["app/store.py", "app/api.py", "tests/test_store.py"]) == ["app/api.py"]
    with pytest.raises(KeyError):
        D.scope_violations(d, "WP-9", [])


def test_format_findings():
    assert D.format_findings([]) == "OK: no drift\n"
    text = D.format_findings([D.Finding("missing_path", "error", "gone", "C-1")])
    assert "ERROR   missing_path [C-1]: gone" in text and "1 error(s)" in text
