from __future__ import annotations

import json

import pytest

from sekkei import model as M
from sekkei.examples import starter_design


def test_json_round_trip_is_lossless():
    d = starter_design()
    text = M.dumps(d)
    d2 = M.loads(text)
    assert M.to_dict(d2) == M.to_dict(d)
    assert M.dumps(d2) == text
    assert json.loads(text)["sekkei"] == "1"
    assert "from" in json.loads(text)["flows"][0]["steps"][0]  # alias restored


def test_tolerant_loading_records_unknown_keys_and_coerces_scalars():
    d = M.from_dict({
        "sekkei": "1", "name": "x", "version": 2,
        "components": [{"id": "C-1", "name": "a", "responsibility": "r", "requires": "I-1", "bogus": True}],
        "workpackages": [],
    })
    assert d.version == "2"
    assert d.components[0].requires == ["I-1"]
    assert sorted(d.unknown_keys) == [("$", "workpackages"), ("$.components[0]", "bogus")]


def test_missing_fields_default_instead_of_raising():
    d = M.from_dict({"sekkei": "1", "requirements": [{"id": "R-1"}]})
    assert d.name == "" and d.requirements[0].statement == "" and d.requirements[0].metric is None


@pytest.mark.parametrize("bad", [
    {"components": [["not", "an", "object"]]},
    {"components": {"id": "C-1"}},
    {"requirements": [{"id": "R-1", "metric": "fast"}]},
    {"name": ["list"]},
])
def test_type_mismatch_raises_design_error_with_path(bad):
    with pytest.raises(M.DesignError) as exc:
        M.from_dict({"sekkei": "1", **bad})
    assert "$." in str(exc.value)


def test_loads_rejects_non_json_and_non_object():
    with pytest.raises(M.DesignError):
        M.loads("not json")
    with pytest.raises(M.DesignError):
        M.loads("[1, 2]")


def test_load_and_dump_files(tmp_path):
    p = tmp_path / "d.json"
    M.dump(starter_design(), p)
    assert M.load(p).name == "todo-api"


def test_lookups_and_single_source_of_ownership():
    d = starter_design()
    assert [i.id for i in d.provided_by("C-1")] == ["I-1"]
    assert d.get("A-1").description
    assert d.index()["WP-1"][0] == "work_packages"
    assert d.component("nope") is None and d.interface("nope") is None


def test_json_schema_is_generated_from_the_dataclasses():
    s = M.json_schema()
    assert s["properties"]["sekkei"]["const"] == "1"
    assert s["$defs"]["Requirement"]["properties"]["kind"]["enum"] == list(M.REQUIREMENT_KINDS)
    assert s["$defs"]["Step"]["properties"]["from"]  # alias, not from_
    assert "unknown_keys" not in s["properties"]
    assert s["additionalProperties"] is False
    # every dataclass field is in the schema (no drift between model and schema)
    from dataclasses import fields
    for name in (f.name for f in fields(M.WorkPackage)):
        assert name in s["$defs"]["WorkPackage"]["properties"]
