"""Regressions from the 2026-09-11 evaluation on three unseen specifications (examples/eval)."""
from __future__ import annotations

from pathlib import Path

from sekkei.engine import design

EVAL = Path(__file__).parent.parent / "examples" / "eval"


def load(name: str) -> str:
    return (EVAL / f"{name}.md").read_text(encoding="utf-8")


def test_ride_dispatch_gets_an_api_a_geo_index_entities_and_the_implied_rate():
    r = design(load("ride"))
    assert r.ok
    names = {c.name for c in r.design.components}
    assert {"Public HTTP API", "Geospatial index", "Payments", "Payment provider", "Push gateway"} <= names
    api = next(i for i in r.design.interfaces if i.name.startswith("Public HTTP API"))
    ops = {o.name for o in api.operations}
    assert {"POST /offers/{id}/accept", "POST /offers/{id}/decline", "POST /trips/{id}/rate"} <= ops
    assert {"Ride", "Trip"} <= {e.name for e in r.design.entities}
    assert not any("History processor" in c.name for c in r.design.components)
    cap = {e.name: e for e in r.notes.capacity.estimates}
    assert cap["implied update rate"].value == "400/s" and "every 5 s" in cap["implied update rate"].inputs
    assert next(a for a in r.answers if a.question_id == "Q-rate").answer.startswith("400 updates/s")
    assert {x.title: x.choice for x in r.design.decisions}["Caller authentication"].startswith("OAuth2 / OIDC")


def test_document_search_exposes_the_use_cases_and_has_no_geo_false_positive():
    r = design(load("docsearch"))
    assert r.ok
    names = {c.name for c in r.design.components}
    assert {"Search index", "Model server", "File storage", "Cache", "Public HTTP API"} <= names
    assert "Geospatial index" not in names
    api = next(i for i in r.design.interfaces if i.name.startswith("Public HTTP API"))
    ops = {o.name for o in api.operations}
    assert "POST /pdfs" in ops and "DELETE /documents/{id}" in ops and any(o.startswith("GET /") for o in ops)
    assert "Document" in {e.name for e in r.design.entities}


def test_telemetry_uses_mqtt_sms_sftp_and_a_broker_that_carries_the_rate():
    r = design(load("telemetry"))
    assert r.ok
    names = {c.name for c in r.design.components}
    assert {"MQTT consumer", "MQTT broker", "SMS provider", "SFTP server", "Reading domain"} <= names
    assert "Ingest API" not in names
    q = {x.title: x for x in r.design.decisions}["Work queue technology"]
    assert q.choice.startswith("Managed broker") and "exceeds" in q.rationale
    reading = next(e for e in r.design.entities if e.name == "Reading")
    assert {"speed", "fuel_level", "engine_temperature", "position"} <= {f.name for f in reading.fields}
    mqtt = next(i for i in r.design.interfaces if i.name.startswith("MQTT consumer"))
    assert mqtt.operations[0].name == "on_message" and "persisted" in mqtt.operations[0].post
    api = next(i for i in r.design.interfaces if i.name.startswith("Public HTTP API"))
    assert not any("batch" in o.name for o in api.operations)  # trucks are devices, not people
