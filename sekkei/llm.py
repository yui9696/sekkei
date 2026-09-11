"""The design engine: sekkei designs by driving a model through its own checks.

Pipeline (``design``)::

    requirements text ──draft──▶ design.json ──lint──▶ diagnostics fed back (rounds)
                                      │
                                      ▼
                        senior-architect review (semantic checklist) ──▶ findings
                                      │
                                      ▼
                          revise ──lint──▶ final design (+ findings kept as risks)

The deterministic core (``rules``, ``graph``) never calls a model. This module does, through
a small ``Backend`` protocol with three implementations:

- ``ClaudeCodeBackend`` — the local ``claude`` CLI in print mode (uses the user's Claude Code
  login; no API key). Default when ``claude`` is on PATH.
- ``AnthropicBackend`` — the ``anthropic`` SDK (``pip install "sekkei[llm]"``).
- ``FakeBackend`` — scripted replies, for tests and dry runs.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from . import model as M
from . import rules as R

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MAX_TOKENS = 64000

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PRINCIPLES = """\
You are a solution architect. You produce a design, not code. The design is a graph:
requirements -> components -> interfaces -> work packages -> acceptance checks, plus
decisions and risks. It will be checked by a deterministic linter; a design that does
not pass is rejected regardless of how good the prose is.

Principles:
1. Every requirement is satisfied by at least one component and delivered by at least one
   work package. Nonfunctional requirements carry a measurable metric (name + target).
2. A component provides an interface by being its `owner`. There is no `provides` list.
   A component lists in `requires` every interface it calls. No cycles between components.
3. Interfaces carry operations with named inputs, an output, and errors. These are the
   contracts that separate agents will code against; be concrete (types, error names).
4. Work packages are units that one coding agent can finish in one session: at most
   ~4 components and ~6 interfaces each. Every package has a write scope (`files`), at
   least one executable acceptance check (`kind: test|command` with a shell `command`),
   `satisfies` requirement ids, and `depends_on` for every package whose interfaces it
   consumes. Packages that could run in parallel must not share files.
5. Every decision lists at least two options and names the chosen one. Every risk has a
   mitigation.
6. Ids: R-n requirements, C-n components, I-n interfaces, E-n entities, F-n flows,
   D-n decisions, K-n risks, WP-n work packages, A-n acceptance checks. Unique across
   the whole document.
7. Do not invent requirements that the input does not state or clearly imply. If the input
   is silent on something a design needs (e.g. persistence), record it as a decision with
   the assumption in `context`.
8. Each requirement in the input becomes its own requirement entry, in the input's words.
   Numbers in the input (rates, latencies, limits, retry schedules) become metrics or
   operation pre/post-conditions, never prose.

Output exactly one JSON object conforming to the schema below, inside a ```json fence,
with no commentary before or after.
"""

REVIEW_PROMPT = """\
You are a senior solution architect reviewing a design produced by a colleague. The design
already passes a structural linter (references resolve, no cycles, every requirement has a
component and a work package). Your job is what the linter cannot do: judge the design.

Go through this checklist against the ORIGINAL REQUIREMENTS and the DESIGN:

1. Requirements fidelity: is every statement in the requirements represented, with its
   numbers? Is anything invented that the requirements do not imply?
2. Decomposition: is any component doing two unrelated jobs (God component)? Is any split
   artificial? Does each component have one clear owner of its data?
3. Interfaces: are the contracts concrete enough for two separate agents to build both
   sides without talking? Missing error cases, idempotency, pagination, timeouts, units?
4. Data: entities, ownership, keys, retention, migration path, what happens on crash.
5. Failure modes: partial failure, retries, duplicates, ordering, back-pressure,
   poison messages, isolation between tenants/endpoints.
6. Security: authentication, authorization, secrets handling and rotation, input
   validation, SSRF/injection where user-supplied URLs or bodies are involved.
7. Operability: metrics, logs, health checks, deploy/rollback, configuration.
8. Work packages: can each one really be finished by one agent in one session? Are the
   acceptance checks strong enough to prove the requirement (not just "tests pass")?
9. Decisions and risks: is any consequential choice undocumented? Any risk missing?

Report only findings that would change the design or its acceptance checks. Be specific:
name ids. Output exactly one JSON object inside a ```json fence:

{"findings": [{"severity": "high|medium|low", "area": "requirements|decomposition|interfaces|data|failure|security|operability|packages|decisions",
               "finding": "...", "recommendation": "...", "affects": ["C-1", "I-2"]}]}

An empty list is a valid answer if the design is genuinely sound.
"""

REVISE_PROMPT = """\
Revise the design below to address the review findings. Rules:
- Keep every existing id whose meaning does not change; add new ids for new elements.
- A finding that adds a requirement is allowed only if the original requirements imply it;
  otherwise record it as a decision (with the assumption in `context`) or a risk.
- Every accepted finding must be visible in the design: a changed interface, a new
  component, a stronger acceptance check, a new decision, or a risk with a mitigation.
- A finding you reject must appear as a decision with status "rejected" and the reason.
Return the complete revised JSON design in a ```json fence, nothing else.
"""


def architect_prompt(include_schema: bool = True, include_rules: bool = True) -> str:
    parts = [PRINCIPLES]
    if include_rules:
        parts.append("The linter's rules (id, severity, rule, hint):\n\n" + R.rule_table())
    if include_schema:
        parts.append("JSON Schema of the design file:\n\n```json\n" + json.dumps(M.json_schema(), indent=1) + "\n```")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class Backend(Protocol):
    name: str

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        """Return the assistant's reply text for a conversation (``messages`` alternate user/assistant)."""
        ...


class FakeBackend:
    """Scripted replies in order; records every request. For tests and dry runs."""

    name = "fake"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        self.calls.append({"system": system, "messages": json.loads(json.dumps(messages))})
        if not self.replies:
            raise RuntimeError("FakeBackend ran out of scripted replies")
        return self.replies.pop(0)


class ClaudeCodeBackend:
    """The local ``claude`` CLI in print mode. Uses the user's Claude Code login, not an API key.

    ``claude -p`` is one-shot, so the conversation is rendered into a single prompt.
    """

    name = "claude-code"

    def __init__(self, model: Optional[str] = None, executable: str = "claude", timeout: int = 1800):
        self.model = model
        self.executable = executable
        self.timeout = timeout

    @staticmethod
    def available(executable: str = "claude") -> bool:
        return shutil.which(executable) is not None

    @staticmethod
    def render(messages: list[dict[str, str]]) -> str:
        if len(messages) == 1:
            return messages[0]["content"]
        parts = ["The conversation so far (you are the ASSISTANT); continue with the next assistant turn only.\n"]
        for m in messages:
            parts.append(f"<{m['role']}>\n{m['content']}\n</{m['role']}>")
        return "\n\n".join(parts)

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        cmd = [self.executable, "-p", "--output-format", "json", "--bare", "--no-session-persistence",
               "--system-prompt", system]
        if self.model:
            cmd += ["--model", self.model]
        # A nested invocation from inside a Claude Code session inherits variables that route
        # the child through the parent's session; drop them so the CLI uses its own login.
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        try:
            proc = subprocess.run(cmd, input=self.render(messages), capture_output=True, text=True,
                                  timeout=self.timeout, env=env, check=False)
        except FileNotFoundError as exc:
            raise RuntimeError(f"{self.executable!r} not found; install Claude Code or use --backend anthropic") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"claude did not answer within {self.timeout}s") from exc
        if proc.returncode != 0 and not proc.stdout.strip():
            raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:500]}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"unexpected claude output: {proc.stdout[:300]!r}") from exc
        if data.get("is_error") or data.get("terminal_reason") not in (None, "completed", "end_turn", "stop_sequence"):
            raise RuntimeError(f"claude reported an error: {data.get('result') or data.get('terminal_reason')}")
        result = data.get("result")
        if not isinstance(result, str) or not result.strip():
            raise RuntimeError(f"claude returned no text (terminal_reason={data.get('terminal_reason')!r})")
        return result


class AnthropicBackend:
    """The ``anthropic`` SDK. ``client`` is injectable for tests."""

    name = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL, client: Any = None):
        self.model = model
        self._client = client

    @staticmethod
    def available() -> bool:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError('the anthropic backend needs the anthropic package: pip install "sekkei[llm]"') from exc
            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=messages,
        ) as stream:
            reply = stream.get_final_message()
        if getattr(reply, "stop_reason", None) == "refusal":
            raise RuntimeError("the model declined the request (stop_reason=refusal)")
        return "".join(getattr(b, "text", "") for b in reply.content if getattr(b, "type", "") == "text")


def get_backend(name: Optional[str] = None, model: Optional[str] = None) -> Backend:
    """Pick a backend: explicit name, else ``claude`` on PATH, else the anthropic SDK."""
    if name in (None, "auto"):
        if ClaudeCodeBackend.available():
            return ClaudeCodeBackend(model)
        if AnthropicBackend.available():
            return AnthropicBackend(model or DEFAULT_MODEL)
        raise RuntimeError("no model backend: install Claude Code (`claude` on PATH) or `pip install \"sekkei[llm]\"`")
    if name == "claude-code":
        return ClaudeCodeBackend(model)
    if name == "anthropic":
        return AnthropicBackend(model or DEFAULT_MODEL)
    raise RuntimeError(f"unknown backend {name!r} (use claude-code or anthropic)")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)


def extract_json(text: str) -> dict[str, Any]:
    """Take the JSON object out of a model reply (fenced or bare)."""
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text[text.find("{") : text.rfind("}") + 1]
    if not candidate:
        raise M.DesignError("no JSON object found in the reply")
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise M.DesignError(f"reply is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise M.DesignError("reply JSON is not an object")
    return data


# ---------------------------------------------------------------------------
# Draft: model -> lint -> feedback -> model ...
# ---------------------------------------------------------------------------


@dataclass
class DraftResult:
    design: Optional[M.Design]
    diagnostics: list[R.Diagnostic]
    rounds: int
    transcript: list[dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.design is not None and not R.has_errors(self.diagnostics)


Progress = Optional[Callable[[str, dict[str, Any]], None]]


def _emit(on_event: Progress, kind: str, **data: Any) -> None:
    if on_event:
        on_event(kind, data)


def _lint_loop(
    backend: Backend,
    system: str,
    messages: list[dict[str, str]],
    rounds: int,
    strict: bool,
    on_event: Progress,
    phase: str,
) -> DraftResult:
    """Send ``messages``; parse + lint the reply; feed errors back; repeat up to ``rounds``."""
    transcript: list[dict[str, str]] = []
    design: Optional[M.Design] = None
    diags: list[R.Diagnostic] = []
    for n in range(1, rounds + 1):
        text = backend.complete(system, messages)
        transcript.append({"role": "assistant", "content": text})
        messages.append({"role": "assistant", "content": text})
        try:
            design = M.from_dict(extract_json(text))
            diags = R.lint(design, strict=strict)
        except M.DesignError as exc:
            design = None
            diags = [R.Diagnostic("S000", "error", str(exc), "$", "Return one JSON object in a ```json fence.")]
        _emit(on_event, "round", phase=phase, round=n, diagnostics=diags)
        if not R.has_errors(diags):
            return DraftResult(design, diags, n, transcript)
        feedback = (
            "The linter rejected the design. Fix every error below and return the complete corrected JSON "
            "(the whole document, not a patch).\n\n" + R.format_text(diags)
        )
        transcript.append({"role": "user", "content": feedback})
        messages.append({"role": "user", "content": feedback})
    return DraftResult(design, diags, rounds, transcript)


def draft(
    requirements_text: str,
    backend: Optional[Backend] = None,
    rounds: int = 3,
    strict: bool = False,
    on_event: Progress = None,
) -> DraftResult:
    """Ask the model for a design; lint; if errors remain, send them back; repeat up to ``rounds``."""
    backend = backend or get_backend()
    messages = [{"role": "user", "content": "Design the system described below.\n\n<input>\n" + requirements_text + "\n</input>"}]
    return _lint_loop(backend, architect_prompt(), messages, rounds, strict, on_event, "draft")


# ---------------------------------------------------------------------------
# Review and revise
# ---------------------------------------------------------------------------


@dataclass
class ReviewFinding:
    severity: str
    area: str
    finding: str
    recommendation: str = ""
    affects: list[str] = field(default_factory=list)


def review(design: M.Design, requirements_text: str, backend: Optional[Backend] = None) -> list[ReviewFinding]:
    """Semantic review by the model against the checklist in ``REVIEW_PROMPT``."""
    backend = backend or get_backend()
    user = (
        "<requirements>\n" + requirements_text + "\n</requirements>\n\n"
        "<design>\n" + M.dumps(design) + "</design>"
    )
    text = backend.complete(REVIEW_PROMPT, [{"role": "user", "content": user}])
    data = extract_json(text)
    out: list[ReviewFinding] = []
    for f in data.get("findings") or []:
        if not isinstance(f, dict) or not f.get("finding"):
            continue
        out.append(ReviewFinding(
            severity=str(f.get("severity", "medium")),
            area=str(f.get("area", "other")),
            finding=str(f["finding"]),
            recommendation=str(f.get("recommendation", "")),
            affects=[str(a) for a in (f.get("affects") or [])],
        ))
    return out


def revise(
    design: M.Design,
    findings: list[ReviewFinding],
    requirements_text: str,
    backend: Optional[Backend] = None,
    rounds: int = 3,
    strict: bool = False,
    on_event: Progress = None,
) -> DraftResult:
    """Ask the model to incorporate the findings; lint the result with feedback rounds."""
    backend = backend or get_backend()
    findings_text = "\n".join(
        f"- [{f.severity}/{f.area}] {f.finding} -> {f.recommendation} (affects: {', '.join(f.affects) or '-'})"
        for f in findings
    )
    user = (
        REVISE_PROMPT + "\n<requirements>\n" + requirements_text + "\n</requirements>\n\n"
        "<findings>\n" + findings_text + "\n</findings>\n\n<design>\n" + M.dumps(design) + "</design>"
    )
    messages = [{"role": "user", "content": user}]
    return _lint_loop(backend, architect_prompt(), messages, rounds, strict, on_event, "revise")


# ---------------------------------------------------------------------------
# The whole thing
# ---------------------------------------------------------------------------


@dataclass
class DesignResult:
    design: Optional[M.Design]
    diagnostics: list[R.Diagnostic]
    findings: list[ReviewFinding]
    draft_rounds: int
    revise_rounds: int
    log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.design is not None and not R.has_errors(self.diagnostics)


def design(
    requirements_text: str,
    backend: Optional[Backend] = None,
    rounds: int = 3,
    review_rounds: int = 1,
    strict: bool = False,
    on_event: Progress = None,
) -> DesignResult:
    """Draft, lint-loop, review, revise, lint-loop. ``review_rounds=0`` skips the review."""
    backend = backend or get_backend()
    log: list[dict[str, Any]] = []

    def log_event(kind: str, data: dict[str, Any]) -> None:
        entry = {"event": kind, **{k: v for k, v in data.items() if k != "diagnostics"}}
        if "diagnostics" in data:
            entry["summary"] = R.summary(data["diagnostics"])
        log.append(entry)
        _emit(on_event, kind, **data)

    first = draft(requirements_text, backend, rounds, strict, log_event)
    if first.design is None or not first.ok:
        return DesignResult(first.design, first.diagnostics, [], first.rounds, 0, log)
    current, diags = first.design, first.diagnostics
    all_findings: list[ReviewFinding] = []
    revise_rounds = 0
    for k in range(review_rounds):
        findings = review(current, requirements_text, backend)
        log_event("review", {"pass_": k + 1, "findings": len(findings)})
        all_findings.extend(findings)
        if not findings:
            break
        revised = revise(current, findings, requirements_text, backend, rounds, strict, log_event)
        revise_rounds += revised.rounds
        if revised.design is None or not revised.ok:
            log_event("revise_failed", {"pass_": k + 1})
            break  # keep the last clean design rather than a broken revision
        current, diags = revised.design, revised.diagnostics
    return DesignResult(current, diags, all_findings, first.rounds, revise_rounds, log)
