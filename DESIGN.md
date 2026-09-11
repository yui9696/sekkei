# sekkei — design document

*sekkei* (設計, "design") is a design-first harness for LLM coding agents. It plays the
part of a solution architect: it holds the architecture as a **checkable graph**, refuses
designs that do not check, hands each coding agent a **self-contained work-package brief**,
and later verifies that the code still matches the design.

This document is the design of sekkei itself. It was written before the code, and the
code is checked against it (`examples/self/design.json` is sekkei's own design, and the
test-suite runs `sekkei check` on the repository).

---

## 1. Problem

LLM coding agents implement quickly and design poorly:

1. They start writing code before the architecture is settled, so the architecture is
   whatever the first file happened to be.
2. Requirements stated at the beginning of a session are silently lost by the end of it,
   and are invisible to the next session.
3. Components built in separate sessions (or by parallel agents) meet at interfaces that
   were never written down, so they do not fit.
4. The "design document", when one exists, is prose. Nothing can check it, so it drifts
   from the code within days.
5. Existing spec-driven workflows (GitHub Spec Kit, AWS Kiro, OpenSpec, BMAD-METHOD) supply
   templates and prompts. Their consistency analyses are themselves performed by the model
   reading Markdown ("build an internal representation", "infer task-to-requirement mapping
   by keyword"), so a wrong analysis fails silently. See `docs/PRIOR_ART.md`.

## 2. Thesis

A solution architect's deliverable is not prose. It is a **graph with contracts**:

```
requirements ──satisfied by──▶ components ──own──▶ interfaces
      ▲                             ▲                  ▲
      └──── work packages ──build───┘──implement───────┘
                  │
                  └── acceptance checks ── prove the requirement
```

plus the decisions that shaped the graph and the risks that threaten it.

If that graph is a data structure, a deterministic program can:

- **check** it (coverage, dangling references, cycles, contracts, measurability);
- **order** it (which work packages can run now, which in parallel, what the critical
  path is);
- **brief** it (emit, for each work package, exactly the contracts, constraints and
  acceptance checks an agent needs — and nothing else);
- **verify** it later against the code (declared modules exist, declared operations exist,
  no undeclared dependency between components, no edits outside a package's scope).

The model's job is to *propose* the design and to *implement* work packages. sekkei's job
is to hold the line: it never guesses, it never infers, and every diagnostic it emits is
reproducible.

## 3. Goals and non-goals

**Goals**

- G1. A design schema rich enough to describe a real system (components, interfaces with
  operations, entities, flows, decisions, risks, work packages, acceptance checks) and
  small enough that an LLM writes it correctly in one shot.
- G2. A linter whose every rule is deterministic, has a stable identifier, a severity, and
  a fix hint, and whose rules are individually covered by a planted-defect test.
- G3. Briefs that let an agent implement a work package without reading the rest of the
  design, and that state what it must *not* touch.
- G4. A plan: topological waves of work packages, parallel-safe (no two concurrent
  packages may write the same file).
- G5. Drift detection against real code, for Python, using only the standard library.
- G6. A closed loop: brief → implementation → completion report → acceptance → next
  packages become ready.
- G7. Zero runtime dependencies. Python 3.11+. Optional LLM drafting behind an extra.

**Non-goals**

- Not a code generator. sekkei emits stubs of *documents*, never application code.
- Not an orchestrator. It computes the plan; running agents is someone else's job
  (Claude Code, a CI matrix, a shell loop). The plan is exported as JSON for them.
- Not a requirements-elicitation chat. The optional `draft` command asks a model for a
  design once and lints it; it does not converse.
- No semantic judgement. sekkei will not tell you a component is badly named or a
  requirement is unwise. It tells you the graph is inconsistent.

## 4. The model

The design file is JSON (`design.json`). JSON was chosen over YAML/TOML because it is the
format LLMs emit most reliably, it round-trips exactly, and Python reads it without
dependencies. A Python DSL (`sekkei.dsl`) is provided for humans who prefer typing less.

Identifiers are free strings but a prefix convention is enforced as a warning so that
agents converge on `R-1`, `C-2`, `I-3`, `E-4`, `F-5`, `D-6`, `K-7` (risk), `WP-8`, `A-9`.
Identifiers are unique across the whole document, not just their collection, so that a
reference is never ambiguous.

| Collection | Element | Key fields | Meaning |
|---|---|---|---|
| `requirements` | `Requirement` | `kind` (functional / nonfunctional / constraint), `priority` (must / should / could), `statement`, `metric` | What must be true. Non-functional ones need a measurable metric. |
| `components` | `Component` | `kind`, `responsibility`, `path`, `requires[]` (interfaces), `satisfies[]` (requirements) | A unit of ownership. `path` is a repo-relative file or directory. |
| `interfaces` | `Interface` | `kind`, `owner` (component), `operations[]` | A contract. Ownership is single-source: a component *provides* an interface iff it is its `owner`. |
| `entities` | `Entity` | `owner`, `fields[]` | A data model owned by a component. |
| `flows` | `Flow` | `trigger`, `steps[] {from, to, via}` | A scenario as a sequence of calls across interfaces. |
| `decisions` | `Decision` | `options[]`, `choice`, `rationale`, `affects[]` | An architecture decision record. |
| `risks` | `Risk` | `likelihood`, `impact`, `mitigation` | What could break the design. |
| `work_packages` | `WorkPackage` | `components[]`, `implements[]`, `depends_on[]`, `satisfies[]`, `files[]`, `size`, `acceptance[]` | A unit of agent work. `files` is its write scope. |
| `conventions` | `Conventions` | `language`, `test_command`, `lint_command`, `rules[]`, `definition_of_done[]` | Project-wide constraints copied into every brief. |

Design decisions embodied in the schema:

- **D1 — single source of truth for ownership.** There is no `provides` list on a
  component; it is derived from `interface.owner`. Two lists that must agree will not.
- **D2 — work packages carry a write scope (`files`).** This is what makes parallel agents
  safe and what makes "you touched a file you did not own" detectable.
- **D3 — acceptance checks are executable where possible.** `kind: test|command` checks
  carry a shell command. `kind: metric` checks must name a non-functional requirement.
  `kind: review` is allowed but the linter says so.
- **D4 — requirements are the root.** Everything traces back to them; a component or a
  work package that satisfies no requirement is flagged (YAGNI is a lint rule).
- **D5 — the schema is versioned** (`"sekkei": "1"`). Unknown keys are a warning, not an
  error, so an older tool can read a newer file, but typos (`workpackages`) are caught.

## 5. The rules

Every rule has an id `XNNN`, a fixed severity (error / warning / info), a one-line message
and a fix hint. Errors block `brief` and `plan` unless `--force`. `--strict` promotes
warnings to errors. Rules are grouped by what they protect:

| Group | Protects | Examples |
|---|---|---|
| **S** structure | the document is well-formed | duplicate id (S001), invalid id (S002), prefix convention (S003), dangling reference (S004), invalid enum value (S005), unknown key (S006), missing required text (S007) |
| **C** consistency | the graph agrees with itself | component depends on itself (C001), component dependency cycle (C002), flow step uses an interface its target does not own (C003) or its source does not require (C004), work-package cycle (C005), package implements an interface but does not build its owner (C006), implicit package dependency through an interface (C007), decision's choice is not one of its options (C008), package depends on itself (C009) |
| **V** coverage | nothing falls through | requirement with no component (V001) / no package (V002), component in no package (V003), interface implemented by no package (V004), package without acceptance (V005), non-functional requirement without metric (V006), risk without mitigation (V007), orphan interface (V008), component satisfying nothing (V009), test/command acceptance without a command (V010), decision with fewer than two options (V011) |
| **A** agent-fitness | a package is implementable by one agent in one session | package with no write scope (A001), two unordered packages sharing a file (A002), package too large (A003), metric acceptance not naming an NFR (A004), no test command in conventions (A005) |
| **Q** wording | the text is not vacuous | vague adjective without a metric (Q001), one-line requirement (Q002), one-line package goal (Q003). These are heuristics and are documented as such. |

Rule severities for coverage rules follow the requirement's priority: a `must`
requirement with no component is an error, a `should` is a warning, a `could` is info.

**Testing the rules.** `tests/test_rules.py` holds one valid fixture that must produce
zero diagnostics, and for every rule id a *planted defect*: a mutation of the fixture that
must trigger exactly that rule. A rule without a planted defect fails the meta-test.
This is how we know the linter is not vacuously green.

## 6. Computations (`sekkei.graph`)

- Component dependency graph: `A → B` iff A requires an interface owned by B.
- Work-package graph: explicit `depends_on`, plus the *implied* edges (A's components
  require an interface implemented by B) which C007 asks the author to make explicit.
- Topological order and **waves** (Kahn layers): wave *n* is every package whose
  dependencies are all in waves < *n*. Packages in one wave may run in parallel — which is
  why A002 forbids them to share files.
- Critical path, weighted by `size` (S=1, M=2, L=4).
- Traceability matrix: requirement × {components, packages, acceptance checks}.

All graph code uses `graphlib` from the standard library.

## 7. Outputs

| Command | Produces |
|---|---|
| `sekkei lint` | diagnostics (text or `--json`), exit 1 on errors |
| `sekkei render` | `DESIGN.md`: overview, requirement table, component catalogue, interface contracts, entities, flows, ADRs, risks, packages, traceability matrix, Mermaid graphs |
| `sekkei brief WP-n` | a self-contained Markdown brief (see §8) |
| `sekkei plan` | waves, critical path, ready packages; `--json` for orchestrators |
| `sekkei graph` | Mermaid (default) or DOT of the component or package graph |
| `sekkei matrix` | the traceability matrix |
| `sekkei check --root DIR` | drift report against code (see §9) |
| `sekkei scope WP-n FILE...` | which of the given files are outside the package's scope |
| `sekkei accept REPORT.json` | validates a completion report and marks the package done; refuses a stale brief |
| `sekkei status` / `sekkei next` | package states (with stale-brief markers) / packages whose dependencies are done |
| `sekkei diff OLD.json` | element-level changes since an older design and the packages whose briefs they invalidate |
| `sekkei schema` | the JSON Schema of the design file |
| `sekkei prompt` | the architect system prompt (schema + rules), for use with any model |
| `sekkei draft FILE` | (optional extra) ask Claude for a design, lint, feed back, repeat |
| `sekkei init` | a starter `design.json` |

## 8. The brief

A brief is what an implementing agent receives. It is generated, not written, so it is
always complete and always current. Sections, in order:

1. **Goal** and the requirements it satisfies, quoted verbatim (so the agent sees the
   words the customer used, not a paraphrase).
2. **Build**: the components in scope with their responsibility and path.
3. **Implement**: every interface the package implements, with the full operation table
   (inputs, output, errors, pre/post-conditions).
4. **Use, do not modify**: interfaces the components consume. The contract is included
   so the agent can code against it; the owner is named so the agent knows who to blame.
5. **Write scope**: the allowed files. Anything else is out of bounds.
6. **Conventions** and definition of done, copied from the design.
7. **Acceptance**: the checks, with commands. The package is not done until they pass.
8. **Dependencies**: what this package waits on and whether it is done (from state).
9. **Report back**: the JSON completion-report template the agent must fill
   (files touched, each acceptance id with pass/fail and output tail, deviations from the
   design, proposed decisions). `sekkei accept` validates it.

The brief deliberately omits everything else in the design. Context is a budget.

## 9. Drift check (`sekkei.drift`)

Runs against a repository root. Standard-library `ast` only; Python only (other languages
report "not checkable" rather than pretending).

- **Presence**: every component `path` exists.
- **Symbols**: for interfaces of kind `function`, `class` or `module` whose owner has a
  Python path, each operation name must appear as a `def`/`class` in the owner's files.
  For `class` interfaces the class itself must exist and operations are looked up as
  methods. Parameter names are compared to the declared inputs (warning on mismatch).
- **Undeclared dependencies**: imports are resolved to files, files to components. If a
  file of component A imports a file of component B and A requires no interface owned by
  B, that is an undeclared dependency (error). Declared-but-unused dependencies are info.
- **Scope**: `sekkei scope` compares a list of changed files (e.g. from `git diff
  --name-only`) with a package's `files`.

## 10. State and the loop (`sekkei.state`)

`.sekkei/state.json` maps package id → `{status, report, updated, brief_fingerprint}`
with statuses `todo | in_progress | done | blocked`. `accept` requires that the report
covers every acceptance id of the package, that every check passed, and that touched
files are in scope; then it marks the package `done`. `next` lists packages whose
dependencies are all `done`. The loop is therefore:

```
design.json ──lint──▶ plan ──next──▶ brief WP ──(agent)──▶ report.json ──accept──▶ next …
                                                     └──check/scope──┘
```

**Stale briefs.** A brief is a function of the design. When `brief` is issued, sekkei
records a fingerprint (a hash of the brief with statuses removed) in the state. If the
design changes afterwards, the fingerprint no longer matches: `status` marks the package
`(stale brief)`, `diff OLD.json` names the packages a change touches and why, and
`accept` refuses the report unless `--force`. This is the control that keeps "the design
changed under the agent" from becoming "the agent implemented a design nobody has".

## 11. Package layout

```
sekkei/
  model.py     dataclasses, from_dict/to_dict, JSON Schema           (component C-1)
  rules.py     Diagnostic, rule registry, all rules                   (C-2)
  graph.py     graphs, cycles, waves, critical path, traceability     (C-3)
  render.py    DESIGN.md                                              (C-4)
  brief.py     work-package briefs and the report template            (C-5)
  drift.py     code checks                                            (C-6)
  state.py     progress state, report acceptance                      (C-7)
  dsl.py       Python authoring DSL                                   (C-8)
  llm.py       optional Claude drafting loop                          (C-9)
  cli.py       argparse front end                                     (C-10)
  examples.py  the starter design written by `sekkei init`            (C-11)
  diff.py      design-version diff and affected packages              (C-12)
```

Dependency direction is strictly downward: `cli → {render, brief, drift, state, llm,
diff, graph, rules} → model`. `graph` depends on `model` only; `rules`, `render`, `drift` and
`state` depend on `graph` and `model`; `brief` depends on `render` (interface tables) and
`state` (report template, statuses); `llm` depends on `rules` and `model`; `dsl` on
`model` only. This is declared in `examples/self/design.json` (regenerated by
`examples/self/build_design.py`) and enforced by `sekkei check` in the test-suite: an
import that violates it fails the build.

## 12. Trade-offs recorded

- **Determinism over cleverness.** No fuzzy matching anywhere. The price is that the
  author must write ids explicitly; the reward is that a green lint means something.
- **JSON over Markdown.** Harder for humans to read, which is why `render` exists.
- **Python-only drift.** A polyglot symbol checker needs parsers we would have to vendor.
  The presence and scope checks are language-independent; the symbol and import checks
  say "not checkable" for anything else.
- **No orchestration.** Agent runtimes change monthly. A JSON plan is the stable contract.
- **Heuristic wording rules exist but are quarantined** in group Q with fixed vocabulary
  lists, so a user can `--disable Q` without losing anything structural.

## 13. What "done" means for sekkei itself

- `sekkei lint examples/self/design.json` is clean.
- `sekkei check examples/self/design.json --root .` reports no drift.
- Every rule id has a planted-defect test; the meta-test enforces it.
- The CLI round-trip (init → lint → render → plan → brief → accept → next) is a test.
- CI on Python 3.11, 3.12, 3.13.
