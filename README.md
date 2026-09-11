# sekkei

**A design-first harness for LLM coding agents.** sekkei (設計, "design") plays the
solution architect: it holds the architecture as a *checkable graph*, refuses designs
that do not check, hands each coding agent a *self-contained brief* for one work package,
and later verifies that the code still matches the design.

Pure Python standard library, 3.11+. No model is required to use it; an optional extra
lets Claude draft the first version of a design.

```
requirements ──satisfied by──▶ components ──own──▶ interfaces
      ▲                             ▲                  ▲
      └──── work packages ──build───┘──implement───────┘
                  │
                  └── acceptance checks ── prove the requirement
```

## Why

LLM agents implement fast and design badly: they start coding before the architecture is
settled, lose requirements between sessions, and build components in parallel that meet at
interfaces nobody wrote down. Spec-driven workflows (Spec Kit, Kiro, OpenSpec, BMAD)
supply templates and prompts, but their "consistency analysis" is itself done by the model
reading Markdown, so a wrong analysis fails silently ([prior-art notes](docs/PRIOR_ART.md)).

sekkei's position: a design is a **graph with contracts**, and a deterministic program
should check it, order it, brief it, and verify it. The model proposes and implements;
sekkei holds the line. Every diagnostic is reproducible from the design file alone.

## What it does

| Command | What you get |
|---|---|
| `sekkei init` | a starter `design.json` that lints clean |
| `sekkei lint` | 36 deterministic rules with stable ids, severities and fix hints; exit 1 on errors |
| `sekkei plan` | work packages in parallel-safe *waves*, the size-weighted critical path, what is ready now |
| `sekkei brief WP-3` | a self-contained brief: goal, requirements verbatim, contracts to implement, contracts to consume (do not modify), write scope, conventions, acceptance checks, and the completion-report template |
| `sekkei check --root .` | drift between design and Python code: missing paths, missing operations, parameter mismatches, **undeclared imports between components** |
| `sekkei scope WP-3 $(git diff --name-only)` | files an agent touched outside its package |
| `sekkei accept report.json` | validates the agent's completion report (all checks passed, files in scope, brief not stale) and unlocks dependents |
| `sekkei diff old.json` | what changed in the design and which packages' briefs that invalidates |
| `sekkei render` / `graph` / `matrix` | `DESIGN.md` with Mermaid graphs, DOT output, the traceability matrix |
| `sekkei schema` / `rules` / `prompt` | JSON Schema, the rule table, an architect system prompt for any model |
| `sekkei draft spec.md` | (optional, `pip install "sekkei[llm]"`) ask Claude for a design, lint, feed the diagnostics back, repeat |

## Quick start

```sh
pip install git+https://github.com/yui9696/sekkei
sekkei init            # writes design.json (a tiny to-do API) — edit it or replace it
sekkei lint            # OK: no diagnostics
sekkei plan            # Waves: 1. WP-1   2. WP-2   Critical path (weight 3): WP-1 -> WP-2
sekkei brief WP-1      # hand this to the agent
# ... the agent implements WP-1 and returns report.json ...
sekkei accept report.json   # accepted WP-1; now ready: WP-2
sekkei check --root .       # does the code match the design?
```

With a coding agent such as Claude Code, the loop is: paste the output of `sekkei prompt`
plus your requirements, let the agent write `design.json`, run `sekkei lint` until clean,
then feed it one `sekkei brief` at a time and `sekkei accept` its reports. The agent never
needs to see the whole design.

## The rules

Rules are grouped by what they protect. A `must` requirement with no component is an
error; the same for a `should` is a warning, for a `could` an info.

| group | protects | examples |
|---|---|---|
| **S** structure | the file is well-formed | duplicate id, dangling reference, invalid enum value, unknown key (typo), empty design |
| **C** consistency | the graph agrees with itself | component dependency cycle, flow step through an interface its target does not own, package implements an interface whose owner it does not build, implicit package dependency |
| **V** coverage | nothing falls through | requirement with no component / no package, component in no package, package without acceptance checks, non-functional requirement without a metric |
| **A** agent-fitness | one agent can do one package in one session | package without a write scope, two unordered packages that may write the same file, package too large |
| **Q** wording | text is not vacuous (heuristic; `--disable Q`) | "fast", "robust" without a metric |

Full table: `sekkei rules` or [docs/RULES.md](docs/RULES.md). Every rule has a planted
defect in `tests/test_rules.py`, and a meta-test fails if one is missing, so the linter
cannot be vacuously green.

## Design file

JSON, versioned (`"sekkei": "1"`), schema from `sekkei schema`. One decision worth knowing:
a component *provides* an interface by being its `owner`; there is no separate `provides`
list, because two lists that must agree will not. Work packages carry `files`, their
write scope, which is what makes parallel waves safe and out-of-scope edits detectable.

Hand-authoring is easier in the Python DSL (`sekkei lint -d design.py` works directly):

```python
from sekkei.dsl import DesignBuilder, op, check

b = DesignBuilder("todo-api")
b.requirement("R-1", "A client can create a to-do item by POSTing a title and gets back its id.")
b.component("C-1", "Store", "Keeps items in memory in insertion order.", path="app/store.py", satisfies=["R-1"])
b.interface("I-1", "Store API", owner="C-1", kind="class",
            operations=[op("add", inputs=[("title", "str")], output="int", errors=["ValueError if empty"])])
b.work_package("WP-1", "Store", goal="Implement the in-memory store and its tests.",
               components=["C-1"], implements=["I-1"], satisfies=["R-1"],
               files=["app/store.py", "tests/test_store.py"],
               acceptance=[check("A-1", "tests pass", command="python -m pytest -q tests/test_store.py")])
design = b.build()
```

## Dogfood

sekkei's own architecture is [`examples/self/design.json`](examples/self/design.json)
(source: `examples/self/build_design.py`, prose: [DESIGN.md](DESIGN.md)). The test-suite
lints it in strict mode and runs `sekkei check` against this repository, so an import that
violates the declared dependency direction fails the build. The test-suite also plants a
defect into a copy of that design to prove the drift check is not vacuous on real code.

Measured on this repository (Apple Silicon laptop, CPython 3.14, 5 runs):
`lint` + `check` in-process 0.16–0.32 s; both commands through the CLI 0.56 s wall time.
122 tests.

## Limits, honestly

- Drift checking parses **Python only** (standard-library `ast`). Other languages get
  path-presence and scope checks; symbol and import checks report `not_checkable`.
- Dynamic imports (`importlib`, `__import__`) are invisible to the import check.
- The wording rules (group Q) are heuristics with a fixed vocabulary. They are warnings.
- `sekkei draft` needs the `anthropic` package and API credentials; it is tested with a
  fake client and has not been exercised against the live API in this repository.
- sekkei computes the plan; it does not run agents. `sekkei plan --json` is the contract
  for whatever does.

## Development

```sh
pip install -e ".[dev]"
pytest -q
python examples/self/build_design.py     # regenerate the self design after changing it
sekkei lint -d examples/self/design.json --strict && sekkei check -d examples/self/design.json --root .
```

MIT. Moe Tabei.
