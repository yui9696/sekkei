"""Optional: ask Claude to draft a design, then lint it and feed the diagnostics back.

The core of sekkei never touches the network. This module needs the ``anthropic`` package
(``pip install "sekkei[llm]"``) and credentials resolved by the SDK (``ANTHROPIC_API_KEY``
or an ``ant auth login`` profile). ``draft`` takes an injectable ``client`` so the loop is
testable without an API call; the only thing the client must provide is
``client.messages.stream(**kwargs)`` returning a context manager whose
``get_final_message()`` has ``.content`` blocks (with ``.type``/``.text``) and
``.stop_reason``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import model as M
from . import rules as R

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MAX_TOKENS = 64000

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

Output exactly one JSON object conforming to the schema below, inside a ```json fence,
with no commentary before or after.
"""


def architect_prompt(include_schema: bool = True, include_rules: bool = True) -> str:
    parts = [PRINCIPLES]
    if include_rules:
        parts.append("The linter's rules (id, severity, rule, hint):\n\n" + R.rule_table())
    if include_schema:
        parts.append("JSON Schema of the design file:\n\n```json\n" + json.dumps(M.json_schema(), indent=1) + "\n```")
    return "\n".join(parts)


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


@dataclass
class DraftResult:
    design: Optional[M.Design]
    diagnostics: list[R.Diagnostic]
    rounds: int
    transcript: list[dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.design is not None and not R.has_errors(self.diagnostics)


def _text_of(message: Any) -> str:
    return "".join(getattr(b, "text", "") for b in message.content if getattr(b, "type", "") == "text")


def _make_client() -> Any:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError('the `draft` command needs the anthropic package: pip install "sekkei[llm]"') from exc
    return anthropic.Anthropic()


def draft(
    requirements_text: str,
    client: Any = None,
    model: str = DEFAULT_MODEL,
    rounds: int = 3,
    strict: bool = False,
    on_round: Optional[Callable[[int, list[R.Diagnostic]], None]] = None,
) -> DraftResult:
    """Ask the model for a design; lint; if errors remain, send them back; repeat up to ``rounds``."""
    client = client or _make_client()
    system = architect_prompt()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Design the system described below.\n\n<input>\n" + requirements_text + "\n</input>"}
    ]
    transcript: list[dict[str, str]] = []
    design: Optional[M.Design] = None
    diags: list[R.Diagnostic] = []
    for n in range(1, rounds + 1):
        with client.messages.stream(
            model=model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=messages,
        ) as stream:
            reply = stream.get_final_message()
        if getattr(reply, "stop_reason", None) == "refusal":
            raise RuntimeError("the model declined the request (stop_reason=refusal)")
        text = _text_of(reply)
        transcript.append({"role": "assistant", "content": text})
        messages.append({"role": "assistant", "content": text})
        try:
            design = M.from_dict(extract_json(text))
            diags = R.lint(design, strict=strict)
        except M.DesignError as exc:
            design = None
            diags = [R.Diagnostic("S000", "error", str(exc), "$", "Return one JSON object in a ```json fence.")]
        if on_round:
            on_round(n, diags)
        if not R.has_errors(diags):
            return DraftResult(design, diags, n, transcript)
        feedback = (
            "The linter rejected the design. Fix every error below and return the complete corrected JSON "
            "(the whole document, not a patch).\n\n" + R.format_text(diags)
        )
        transcript.append({"role": "user", "content": feedback})
        messages.append({"role": "user", "content": feedback})
    return DraftResult(design, diags, rounds, transcript)
