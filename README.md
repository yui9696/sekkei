# sekkei

**A solution-architecture engine and a design-first harness for LLM coding agents.**
sekkei (設計, "design") takes a requirements text and produces a complete architecture —
components, contracts, entities, flows, scored decisions, risks, work packages with
acceptance checks — **without calling a model**, then holds the line while agents build it:
it lints the design, hands each agent a self-contained brief, refuses stale briefs, and
checks the code against the design afterwards.

Pure Python standard library, 3.11+. Deterministic: same text, same design, byte for byte.

```
requirements.md ──sekkei design──▶ design.json ──lint/plan──▶ brief WP-n ──(agent)──▶ accept ──▶ check
                                       │
                                       └── DESIGN.md · REVIEW.md (what the engine could not decide) · trace.json
```

## Quick start

```sh
pip install git+https://github.com/yui9696/sekkei
sekkei design requirements.md --render DESIGN.md --review REVIEW.md
sekkei plan             # waves of work packages, critical path, what is ready now
sekkei brief WP-1       # hand this to a coding agent
sekkei accept report.json
sekkei check --root .   # does the code still match the design?
```

Try it on the bundled webhook-delivery spec:

```sh
sekkei design examples/webhooks/requirements.md --render /tmp/DESIGN.md --review /tmp/REVIEW.md
```

## The engine

A solution architect's job, mechanised into five deterministic steps
([docs/ENGINE_DESIGN.md](docs/ENGINE_DESIGN.md)):

| step | what happens | where |
|---|---|---|
| analyse | sentences → requirement units with modality (must/should/could), kind (functional / non-functional / constraint), the numbers as metrics (`p95 latency < 5 s`, `>= 1000 events/s`), actors, verbs, objects | `engine/text.py`, `engine/analysis.py` |
| recognise | 22 capability patterns (async delivery with retries, request signing, admin API, event ingest, audit log, batch pipeline, CLI tool, …) and 12 quality attributes matched by signals in the text | `engine/catalog.py` |
| synthesise | patterns bring archetypes (31), which merge into components with interfaces and operations; entities, flows, requirement-to-component mapping; operations are derived from the verbs and objects of the input sentences | `engine/synthesis.py` |
| decide | 12 decision points with 36 options (queue technology, store, isolation strategy, retry scheduling, process topology, auth scheme, secret storage, outbound safety, concurrency control, …) scored ATAM-style: `utility = Σ quality weight × fit`, options ruled out or favoured by the stated constraints; the rationale and the trade-off are written into the decision record | `engine/evaluate.py` |
| package | components are layered, cut into ≤3-component work packages with unique write scopes, ordered by the interfaces they consume; acceptance checks derived from the metrics | `engine/synthesis.py` |

Then the engine **reviews its own output**: requirements it did not recognise, quality
attributes it has no tactic for, generic components from the fallback, assumptions made.
It says what it does not know instead of hiding it. Every element carries a trace to the
sentences and catalogue rules that produced it (`--trace`).

What the engine produced for the webhook spec (`examples/webhooks/`): 16 components
including a partitioned durable queue, worker, retry scheduler carrying the backoff
schedule from the text as a precondition, HMAC signer with a rotation-window secret store,
SSRF-safe outbound client, health policy with notifier, admin and ingest APIs with
operations derived from the sentences (`POST /endpoints`, `DELETE /endpoints/{id}`,
`POST /secrets/{id}/rotate`, `POST /events`), observability; 10 scored decisions; 7 work
packages in 5 waves; zero lint diagnostics; nothing unrecognised. Time: 0.05–0.3 s.

**Limits, stated plainly.** The engine has no understanding of prose. Its catalogue is
finite; a domain outside it (the bundled greenhouse-controller fixture) gets a layered
fallback (surface / core / store / config) and a review that names every unrecognised
sentence. Operation names come from a verb/object heuristic and carry the sentence they
came from so a wrong one is easy to spot. This is where a human architect — or a model —
still earns their keep, and sekkei tells you exactly where that is.

## The harness

| command | what you get |
|---|---|
| `lint` | 36 deterministic rules (structure, consistency, coverage, agent-fitness, wording) with stable ids and fix hints; every rule has a planted-defect test |
| `plan` | parallel-safe waves (no two concurrent packages share a file), size-weighted critical path, ready packages, `--json` for orchestrators |
| `brief WP-n` | a self-contained brief: goal, requirements verbatim, contracts to implement, contracts to consume (do not modify), write scope, conventions, acceptance checks, completion-report template |
| `check --root .` | drift between design and Python code: missing paths/operations, parameter mismatches, **undeclared imports between components** |
| `scope`, `accept`, `status`, `next`, `diff` | write-scope check for changed files; completion-report validation (all checks passed, files in scope, **brief not stale**); design-version diff naming the packages whose briefs it invalidates |
| `render`, `graph`, `matrix`, `schema`, `rules` | `DESIGN.md` with Mermaid, DOT, traceability matrix, JSON Schema, the rule table |
| `draft` (optional) | let a model draft instead: local Claude Code CLI or the `anthropic` SDK, lint feedback rounds, `--review` for a senior-architect review-and-revise pass. Tested with a fake backend only |

Hand-authoring is also possible: JSON (`sekkei schema`) or a Python DSL (`sekkei.dsl`).

## Dogfood and numbers

sekkei's own architecture is [`examples/self/design.json`](examples/self/design.json)
(19 components including the engine's seven; prose in [DESIGN.md](DESIGN.md)). The
test-suite lints it in strict mode and runs `sekkei check` against this repository, so an
import that violates the declared dependency direction fails the build.

Measured on this repository (Apple Silicon laptop, CPython 3.14):

| what | value |
|---|---|
| tests | 153 |
| engine fixtures that must lint clean, be deterministic and be faithful (every bullet a verbatim requirement) | 4 (webhooks, inventory, CLI tool, out-of-catalogue greenhouse) |
| `sekkei design` on the webhook spec | 0.05–0.3 s |
| `lint` + `check` on the self design | 0.16–0.32 s |
| catalogue | 22 patterns, 31 archetypes, 12 decision points / 36 options, 12 quality tactics, 13 risks, 9 language layouts |

## Prior art

Spec Kit, Kiro, OpenSpec and BMAD supply templates and prompts; their consistency analysis
is done by the model reading Markdown. Requirements-traceability suites are deterministic
but not built around agents, briefs or write scopes. Rule-based architecture synthesis
with ATAM-style scoring exists in the literature; a dependency-free, tested implementation
wired to an agent harness is what this repository adds. See [docs/PRIOR_ART.md](docs/PRIOR_ART.md).

## Development

```sh
pip install -e ".[dev]"
pytest -q
python examples/self/build_design.py     # regenerate the self design after changing it
sekkei lint -d examples/self/design.json --strict && sekkei check -d examples/self/design.json --root .
```

MIT. Moe Tabei.
