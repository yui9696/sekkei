from __future__ import annotations

import pytest

import sekkei
from sekkei import dsl, model as M
from sekkei.examples import starter_design


def test_builder_matches_json_model():
    d = starter_design()
    assert M.to_dict(M.loads(M.dumps(d))) == M.to_dict(d)
    assert sekkei.lint(d) == []


def test_helpers():
    o = dsl.op("f", inputs=["a", ("b", "int"), ("c", "str", "the c")], output="None")
    assert [p.name for p in o.inputs] == ["a", "b", "c"] and o.inputs[2].description == "the c"
    assert dsl.check("A-1", "d").kind == "test"
    assert dsl.option("x", pros=["p"]).pros == ["p"]
    assert dsl.step("C-1", "C-2", "I-1").from_ == "C-1"


def test_load_python_variants(tmp_path):
    src = "from sekkei.examples import starter_design\n"
    (tmp_path / "a.py").write_text(src + "design = starter_design('a')\n")
    (tmp_path / "b.py").write_text(src + "def build():\n    return starter_design('b')\n")
    (tmp_path / "c.py").write_text(src + "from sekkei.dsl import DesignBuilder\ndesign = DesignBuilder('c')\n")
    (tmp_path / "d.py").write_text("x = 1\n")
    assert dsl.load_python(tmp_path / "a.py").name == "a"
    assert sekkei.load(tmp_path / "b.py").name == "b"
    assert dsl.load_python(tmp_path / "c.py").name == "c"
    with pytest.raises(ValueError):
        dsl.load_python(tmp_path / "d.py")


def test_builder_save(tmp_path):
    b = dsl.DesignBuilder("x")
    b.requirement("R-1", "Something specific must happen when asked.")
    b.save(tmp_path / "x.json")
    assert sekkei.load(tmp_path / "x.json").requirements[0].id == "R-1"
