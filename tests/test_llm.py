"""The drafting loop, exercised with a fake client (no network, no API key)."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from sekkei import llm, model as M
from sekkei.examples import starter_design


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeClient:
    """Replies with the scripted texts in order and records every request."""

    def __init__(self, replies, stop_reason="end_turn"):
        self.replies = list(replies)
        self.calls = []
        self.stop_reason = stop_reason
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))  # snapshot: draft() keeps mutating its messages list
        text = self.replies.pop(0)
        msg = SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
            stop_reason=self.stop_reason,
        )
        return FakeStream(msg)


def fenced(obj) -> str:
    return "Here is the design:\n```json\n" + json.dumps(obj) + "\n```\nDone."


def test_draft_feeds_lint_errors_back_and_stops_when_clean():
    incomplete = {"sekkei": "1", "name": "x", "requirements": [{"id": "R-1", "statement": "Something specific must happen."}]}
    good = M.to_dict(starter_design())
    client = FakeClient([fenced(incomplete), fenced(good)])
    rounds = []
    result = llm.draft("build a todo api", client=client, rounds=3, on_round=lambda n, d: rounds.append(n))
    assert result.ok and result.rounds == 2 and rounds == [1, 2]
    assert result.design.name == "todo-api"
    # second request carried the diagnostics of the first
    second = client.calls[1]["messages"]
    assert second[-1]["role"] == "user" and "S008" in second[-1]["content"]
    assert client.calls[0]["model"] == llm.DEFAULT_MODEL
    assert client.calls[0]["thinking"] == {"type": "adaptive"}
    assert "JSON Schema" in client.calls[0]["system"]


def test_draft_gives_up_after_rounds_and_keeps_last_design():
    incomplete = {"sekkei": "1", "name": "x"}
    client = FakeClient([fenced(incomplete)] * 2)
    result = llm.draft("x", client=client, rounds=2)
    assert not result.ok and result.rounds == 2 and result.design is not None
    assert any(d.rule == "S008" for d in result.diagnostics)


def test_draft_handles_unparseable_reply():
    client = FakeClient(["no json here", fenced(M.to_dict(starter_design()))])
    result = llm.draft("x", client=client, rounds=2)
    assert result.ok and result.rounds == 2
    assert "S000" in client.calls[1]["messages"][-1]["content"]


def test_refusal_raises():
    client = FakeClient(["..."], stop_reason="refusal")
    with pytest.raises(RuntimeError, match="refusal"):
        llm.draft("x", client=client)


def test_extract_json_variants():
    assert llm.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.extract_json('text {"a": {"b": 2}} more') == {"a": {"b": 2}}
    with pytest.raises(M.DesignError):
        llm.extract_json("nothing")
    with pytest.raises(M.DesignError):
        llm.extract_json("```json\n[1]\n```")


def test_architect_prompt_carries_schema_and_rules():
    p = llm.architect_prompt()
    assert "S001" in p and '"$defs"' in p and "solution architect" in p
    assert '"$defs"' not in llm.architect_prompt(include_schema=False)
