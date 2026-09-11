"""The design engine, exercised with the fake backend (no network, no API key, no CLI)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from sekkei import llm, model as M
from sekkei.examples import starter_design


def fenced(obj) -> str:
    return "Here it is:\n```json\n" + json.dumps(obj) + "\n```\nDone."


GOOD = M.to_dict(starter_design())
INCOMPLETE = {"sekkei": "1", "name": "x", "requirements": [{"id": "R-1", "statement": "Something specific must happen."}]}


def test_draft_feeds_lint_errors_back_and_stops_when_clean():
    be = llm.FakeBackend([fenced(INCOMPLETE), fenced(GOOD)])
    events = []
    result = llm.draft("build a todo api", backend=be, rounds=3, on_event=lambda k, d: events.append((k, d["round"])))
    assert result.ok and result.rounds == 2 and events == [("round", 1), ("round", 2)]
    assert result.design.name == "todo-api"
    second = be.calls[1]["messages"]
    assert second[-1]["role"] == "user" and "S008" in second[-1]["content"]
    assert "JSON Schema" in be.calls[0]["system"] and "<input>" in be.calls[0]["messages"][0]["content"]


def test_draft_gives_up_after_rounds_and_keeps_last_design():
    be = llm.FakeBackend([fenced({"sekkei": "1", "name": "x"})] * 2)
    result = llm.draft("x", backend=be, rounds=2)
    assert not result.ok and result.rounds == 2 and result.design is not None
    assert any(d.rule == "S008" for d in result.diagnostics)


def test_draft_handles_unparseable_reply():
    be = llm.FakeBackend(["no json here", fenced(GOOD)])
    result = llm.draft("x", backend=be, rounds=2)
    assert result.ok and result.rounds == 2
    assert "S000" in be.calls[1]["messages"][-1]["content"]


def test_review_parses_findings_and_tolerates_junk():
    be = llm.FakeBackend([fenced({"findings": [
        {"severity": "high", "area": "security", "finding": "No auth on the admin API.", "recommendation": "Add API keys.", "affects": ["C-2"]},
        {"finding": "minimal"},
        "junk", {"severity": "low"},
    ]})])
    fs = llm.review(starter_design(), "reqs", backend=be)
    assert [f.finding for f in fs] == ["No auth on the admin API.", "minimal"]
    assert fs[0].affects == ["C-2"] and fs[1].severity == "medium" and fs[1].area == "other"
    assert "<requirements>" in be.calls[0]["messages"][0]["content"] and "checklist" in be.calls[0]["system"]


def test_design_pipeline_draft_review_revise():
    revised = json.loads(json.dumps(GOOD))
    revised["risks"].append({"id": "K-2", "description": "Admin API is unauthenticated.", "mitigation": "API keys in v1."})
    be = llm.FakeBackend([
        fenced(GOOD),                                                   # draft round 1 (clean)
        fenced({"findings": [{"severity": "high", "area": "security",
                              "finding": "No auth.", "recommendation": "Add keys.", "affects": ["C-2"]}]}),
        fenced({"sekkei": "1", "name": "broken"}),                      # revise round 1: rejected by lint
        fenced(revised),                                                # revise round 2: clean
    ])
    events = []
    result = llm.design("reqs", backend=be, rounds=3, review_rounds=1, on_event=lambda k, d: events.append(k))
    assert result.ok and result.draft_rounds == 1 and result.revise_rounds == 2
    assert [f.finding for f in result.findings] == ["No auth."]
    assert any(r.id == "K-2" for r in result.design.risks)
    assert events == ["round", "review", "round", "round"]
    assert [e["event"] for e in result.log] == events
    assert "<findings>" in be.calls[2]["messages"][0]["content"]


def test_design_keeps_last_clean_design_when_revision_fails():
    be = llm.FakeBackend([
        fenced(GOOD),
        fenced({"findings": [{"finding": "x"}]}),
        fenced({"sekkei": "1", "name": "broken"}),
    ])
    result = llm.design("reqs", backend=be, rounds=1, review_rounds=1)
    assert result.ok and result.design.name == "todo-api"
    assert result.log[-1]["event"] == "revise_failed"


def test_design_skips_review_when_asked_and_stops_on_no_findings():
    be = llm.FakeBackend([fenced(GOOD)])
    assert llm.design("reqs", backend=be, review_rounds=0).ok
    be = llm.FakeBackend([fenced(GOOD), fenced({"findings": []})])
    r = llm.design("reqs", backend=be, review_rounds=2)
    assert r.ok and r.findings == [] and len(be.calls) == 2


def test_design_returns_early_when_draft_never_cleans():
    be = llm.FakeBackend([fenced({"sekkei": "1", "name": "x"})])
    r = llm.design("reqs", backend=be, rounds=1)
    assert not r.ok and r.findings == []


def test_fake_backend_exhaustion():
    with pytest.raises(RuntimeError):
        llm.FakeBackend([]).complete("s", [{"role": "user", "content": "x"}])


def test_claude_code_backend_renders_and_parses(monkeypatch):
    seen = {}

    def fake_run(cmd, input, capture_output, text, timeout, env, check):
        seen["cmd"], seen["input"], seen["env"] = cmd, input, env
        return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "PONG", "is_error": False, "terminal_reason": "completed"}), stderr="")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    monkeypatch.setenv("CLAUDECODE", "1")
    be = llm.ClaudeCodeBackend(model="claude-opus-5")
    out = be.complete("SYS", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}])
    assert out == "PONG"
    assert "--system-prompt" in seen["cmd"] and "SYS" in seen["cmd"] and "--model" in seen["cmd"]
    assert "<assistant>\nb\n</assistant>" in seen["input"] and seen["input"].endswith("<user>\nc\n</user>")
    assert "CLAUDECODE" not in seen["env"]
    assert be.render([{"role": "user", "content": "only"}]) == "only"


def test_claude_code_backend_errors(monkeypatch):
    def failing(cmd, **kw):
        return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "Credit balance is too low", "is_error": True}), stderr="")

    monkeypatch.setattr(llm.subprocess, "run", failing)
    with pytest.raises(RuntimeError, match="Credit balance"):
        llm.ClaudeCodeBackend().complete("s", [{"role": "user", "content": "x"}])

    def garbage(cmd, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(llm.subprocess, "run", garbage)
    with pytest.raises(RuntimeError, match="exited 1"):
        llm.ClaudeCodeBackend().complete("s", [{"role": "user", "content": "x"}])


def test_anthropic_backend_with_injected_client():
    class Stream:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get_final_message(self):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")], stop_reason="end_turn")

    calls = []
    client = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: (calls.append(kw), Stream())[1]))
    be = llm.AnthropicBackend(client=client)
    assert be.complete("s", [{"role": "user", "content": "x"}]) == "hi"
    assert calls[0]["model"] == llm.DEFAULT_MODEL and calls[0]["thinking"] == {"type": "adaptive"}

    class Refusal(Stream):
        def get_final_message(self):
            return SimpleNamespace(content=[], stop_reason="refusal")

    client = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: Refusal()))
    with pytest.raises(RuntimeError, match="refusal"):
        llm.AnthropicBackend(client=client).complete("s", [{"role": "user", "content": "x"}])


def test_get_backend_selection(monkeypatch):
    monkeypatch.setattr(llm.ClaudeCodeBackend, "available", staticmethod(lambda executable="claude": True))
    assert llm.get_backend().name == "claude-code"
    assert llm.get_backend("anthropic", "m").model == "m"
    monkeypatch.setattr(llm.ClaudeCodeBackend, "available", staticmethod(lambda executable="claude": False))
    monkeypatch.setattr(llm.AnthropicBackend, "available", staticmethod(lambda: False))
    with pytest.raises(RuntimeError, match="no model backend"):
        llm.get_backend()
    with pytest.raises(RuntimeError, match="unknown backend"):
        llm.get_backend("gpt")


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
