"""The domain model: typed fields, relations, state machines and invariants read from the sentences; aggregates as components."""
from __future__ import annotations

from pathlib import Path

from sekkei.engine import analyse, design, domain as DM

EX = Path(__file__).parent.parent / "examples"


def _ents(path: str):
    an = analyse((EX / path).read_text(encoding="utf-8"))
    return {e.name: e for e in DM.extract(an, [u for u in an.requirements if u.kind != "constraint"])}


def test_fields_states_and_invariants_from_the_trading_spec():
    e = _ents("real2/01_confluence_trading.md")
    order = e["order"]
    names = {f[0] for f in order.fields}
    assert {"instrument", "notional", "strike", "expiry", "direction", "limit_price"} <= names
    types = dict((f[0], f[1]) for f in order.fields)
    assert types["notional"] == "Money" and types["expiry"] == "timestamp" and types["direction"] == "enum"
    assert {"working", "submitted", "cancelled"} <= set(order.states)
    assert e["fill"].states and any("immutable" in t for t, _ in e["fill"].invariants)
    assert "venue" not in e or not e["venue"].states          # "from a venue are booked": the subject is fills
    assert "precision" not in e and "london" not in e and "bank" not in e


def test_proper_nouns_verbs_and_adjectives_are_not_entities():
    e = _ents("real4/03_hw_fw_cloud_lock.md")
    assert "credential" in e and "building" in e
    assert not {"fail", "effect", "take", "hallway", "wifi", "certified"} & set(e)


def test_actor_as_object_and_verb_as_determined_noun():
    e = _ents("real3/06_notion_trials.md")
    assert "participant" in e and "randomised" in e["participant"].states
    e2 = _ents("real2/02_jira_epic_streaming.md")
    assert "clip" in e2                                       # "create a clip": a verb used as a thing
    e3 = _ents("real3/04_rfc_matchmaking.md")
    assert "ticket" in e3 and "match" in e3


def test_aggregates_become_components_with_transitions_and_own_packages():
    r = design((EX / "real2/01_confluence_trading.md").read_text(encoding="utf-8"))
    assert r.ok
    names = {c.name for c in r.design.components}
    assert "Order domain" in names and "Fill domain" in names
    od = next(i for i in r.design.interfaces if i.name == "Order domain interface")
    assert {"submit_order", "cancel_order", "get_order"} <= {o.name for o in od.operations}
    order = next(e for e in r.design.entities if e.name == "Order")
    assert order.owner == next(c.id for c in r.design.components if c.name == "Order domain")
    assert any(f.name == "status" and f.type.startswith("enum(") for f in order.fields)
    assert not any(e.name == "Record" for e in r.design.entities)
    wps = {w.title: w.size for w in r.design.work_packages}
    assert "Order domain" in wps and wps["Order domain"] in ("M", "L")
    assert not any(c.name.endswith(("processor", "controller")) and c.name.split()[0] in ("Precision", "Officer") for c in r.design.components)
    assert all(p.how == "aggregate" for p in r.placements if p.requirement in ("R-1", "R-2", "R-4"))


def test_resources_follow_the_entity_not_the_attribute():
    r = design((EX / "real2/01_confluence_trading.md").read_text(encoding="utf-8"))
    api = next(i for i in r.design.interfaces if "HTTP API" in i.name)
    ops = {o.name for o in api.operations}
    assert "POST /orders/{id}/amend" in ops and "POST /orders/{id}/cancel" in ops
    assert not any(o.startswith("POST /prices") for o in ops)


def test_sizes_follow_scope():
    r = design((EX / "real2/01_confluence_trading.md").read_text(encoding="utf-8"))
    sizes = {w.size for w in r.design.work_packages}
    assert "L" in sizes and "S" in sizes
