# sekkei

**A solution-architecture engine and a design-first harness for LLM coding agents.**
sekkei (設計, "design") takes a requirements text and produces a complete architecture —
components, contracts, entities, flows, scored decisions, risks, work packages with
acceptance checks — **without calling a model**, then holds the line while agents build it:
it lints the design, hands each agent a self-contained brief, refuses stale briefs, and
checks the code against the design afterwards.

Pure Python standard library, 3.11+ (the optional `draft` command imports the `anthropic` SDK only when you choose that backend). Deterministic: same text, same design, byte for byte.

```
requirements.md ──sekkei design──▶ design.json ──lint/plan──▶ brief WP-n ──(agent)──▶ accept ──▶ check
                                       │
                                       └── DESIGN.md · NOTES.md (answers, sizing, threats, effort) · trace.json
```

## Quick start

```sh
pip install git+https://github.com/yui9696/sekkei
sekkei template -o requirements.md          # fill in the blanks (or write free text)
sekkei design requirements.md --render DESIGN.md --review NOTES.md
sekkei plan             # waves of work packages, critical path, what is ready now
sekkei brief WP-1       # hand this to a coding agent
sekkei accept report.json
sekkei check --root .   # does the code still match the design?
```

Try it on the bundled specs — a page ([`examples/webhooks/requirements.md`](examples/webhooks/requirements.md))
and two lines ([`examples/minimal/requirements.md`](examples/minimal/requirements.md)):

```sh
sekkei design examples/webhooks/requirements.md --render /tmp/DESIGN.md --review /tmp/NOTES.md
sekkei ask examples/minimal/requirements.md   # just the questions an architect would ask
```

## What to write

The engine reads **structure, modality and numbers**, not prose
([docs/WRITING_REQUIREMENTS.md](docs/WRITING_REQUIREMENTS.md)). The shape that works:

```markdown
# Warehouse inventory service
## Functional
- Staff can add, move and remove stock items (SKU, quantity, warehouse, bin) through a REST API.
- Managers receive an email when any SKU falls below its reorder level.
## Non-functional
- Search returns within 300 ms p95 for a catalogue of 200,000 items.
- Stock counts are never lost or double-applied under concurrent updates.
## Constraints
- TypeScript on Node 20, PostgreSQL available. Team of 2. Containers behind an existing ingress.
## Out of scope
- Purchasing and supplier management.
```

One bullet per requirement; an actor at the front makes it an operation; numbers with
units become metrics and contract preconditions; technology and team constraints steer
every decision. Two lines are enough to start: the engine designs what it can and the
notes list the questions it would have asked, each with the assumption it used meanwhile.
Answer a question by adding a bullet and run again; only the parts the answer touches
change.

## Or design in dialogue

```sh
sekkei interview            # or: sekkei interview requirements.md
```

Describe the system in sentences (English); the engine turns each into a classified
requirement, re-designs after every turn, and asks **one thing at a time in the order an
architect would**: owners to confirm for sentences no pattern knows, then stack (language,
store, deployment, team), load and quality, data/security/operations/cost, and finally the
decisions whose top two options score within 0.15 of each other. Every prompt shows the
engine's proposal with its evidence or default; Enter accepts it, a typed answer is
normalised into a canonical bullet (`Team of 3.`, `PostgreSQL available.`,
`Operations complete within 200 ms p95.`), `skip` leaves it to the engine. The transcript
*is* `requirements.md`, so the design is reproducible without the dialogue; the session
resumes from `.sekkei/interview.json`. `/add`, `/status`, `/design`, `/undo`, `/done`.
`--script replies.txt` replays a session non-interactively.

## Nothing is left to a human by default

Two things an architect normally does in the meeting room, the engine does on its own:

- **It answers its own questions.** For every gap (no database stated, no latency target,
  no retention, no authentication, …) an answer rule looks for evidence in the text first
  (a command-line tool with `no network` → SQLite; staff and an identity provider → OIDC;
  counts ≥ 10,000 → PostgreSQL) and falls back to a defensible default (team of 2; p95
  300 ms reads / 1 s writes; 99.9 % monthly; 90-day retention; daily backups). The answers
  are appended to the requirements so they shape the design through the normal path, and
  each becomes a **proposed decision** recording the options, the evidence and what to
  change if the real answer differs (`--augmented REQ.md` writes the augmented text;
  `--no-assume` keeps the questions open instead).
- **It owns every requirement.** A sentence no pattern recognises is placed by word
  overlap with a specific component, or — for a human use case — on the surface and the
  core, or a **new component is synthesised** from the sentence's verb class and object
  ("The controller reads temperature from four sensors" → `Temperature reader`; "It opens
  or closes the roof vents" → `Vents controller`), with an interface, a path and a work
  package. Every placement is listed in the notes with how it was made.

## The whole hand-over, and its own red team

```sh
sekkei deliver requirements.md -o deliverables/ [--prices prices.json]
sekkei redteam requirements.md
```

`deliver` writes what a solution architect hands over besides the design: an executive
summary, one ADR per decision (MADR), C4 context and container diagrams (Mermaid), a risk
register scored and owned by work package, an FMEA computed from the dependency graph
(which requirements stop being met when a component fails), a roadmap by wave with one
calendar formula shared with the notes, a RACI, SLOs with error budgets and burn-rate
alerts, a cost model, and runbooks per running component. Every number is either in the
text, computed by a formula printed next to it, or marked as an assumption. **Unit prices
are never guessed**: the cost model lists quantities and formulas and takes prices from a
file you supply; without one the total is a formula.

`redteam` attacks the design with the requirements as the oracle and exits 1 on a high
finding: a sentence whose deletion changes nothing in the design (recorded, not honoured),
a number that reaches no metric or contract, a `can` and a `must not` on the same verb and
object, a metric with two targets, more decisions guessed than taken from the text, and
which decisions flip when every rate is doubled or a constraint is dropped. On the
document-search evaluation spec it finds the gap the evaluation had found by hand
(per-team visibility is recorded and ignored) in 19 engine runs.

## Specifications as engineers actually write them

The template above is the easiest shape, not the only one. A structure pass
(`engine/structure.py`) reads what teams really hand over and folds it into that shape,
reporting every fold in the notes:

| you write | the engine reads |
|---|---|
| a 要件定義書 with `2. 機能要件` numbered headings and a `\| No \| 機能 \| 内容 \| 優先度 \|` table | sections; one requirement per row, priority from the 優先度 column (必須/推奨/任意 → must/should/could), row ids kept |
| a Jira/GitHub epic: `### RET-101 — As a customer, I want … so that …` + Given/When/Then | `Customers can …` with the *so that* as rationale; `I` in the criteria becomes the story's actor |
| meeting notes: `Ana: …`, `DECIDED: Postgres`, `TODO Ana: ask …`, `out of scope: …`, `team: Bo + Chen`, `maybe alerts?` | speaker labels dropped; decisions become constraints; TODOs and questions are lifted into the notes (not designed); inline out-of-scope becomes a section; the team is counted; tentative sentences get priority *could* |
| an RFC with Motivation / Goals / Non-goals / Requirements / Alternatives considered | background is not a requirement; a generic *Requirements* heading lets content decide functional vs non-functional; rejected alternatives become rejected decisions |
| checkboxes, nested bullets, `3.1 性能: …` labels, front matter (author, date, version), one sentence with no structure at all | stripped / kept as their own requirement / label dropped / skipped / every sentence taken as a requirement |
| a stated deadline (`MVP in 6 weeks`, `2027 年 3 月リリース`) | compared with the engine's own calendar estimate in the notes |
| `Systems affected: checkout-api, ledger-service`, `Team: 5 engineers, 1 SRE`, `team is me + Lena`, an `Open questions` / `Actions` section, a `\| Field \| Value \|` header table, a glossary table | a constraint naming the existing systems; the team counted (6, 2); questions and actions lifted into the notes and counted in the summary; metadata and glossary tables skipped, not designed |
| text pasted from a PDF (page headers repeated, lines hard-wrapped, `auto-` / `approved`) | headers and page markers dropped, wrapped lines re-joined |

Eleven such specifications (Japanese RFP, Jira export, Slack notes, RFC, a monolith split,
an ETL pipeline, a field app, IoT cold chain, an engineer's TODO list, a one-liner) live in
[`examples/real/`](examples/real/), and thirteen more written by an independent reviewer
posing as an adopting team (a Confluence design doc with a metadata table, a Jira epic whose
stories are prose lines with Given/When/Then underneath, meeting notes with speakers, a
Japanese 要件定義書 with a glossary table, a Slack paragraph, a brownfield change request
naming five existing services, a PDF paste with page headers and hard wraps, a two-line
table header, …) in [`examples/real2/`](examples/real2/). Each must design lint-clean and
deterministically, a fuzz test mutates them (deleted, duplicated, truncated, nested and junk
lines) and requires the same, and every finding of that review is a test
([`tests/test_real2.py`](tests/test_real2.py)). The notes list every sentence the engine read
but did not take as a requirement, and every Japanese rewrite that may have lost a negation.

## Into the tools the team already uses

| command | what you get |
|---|---|
| `sekkei issues -o .` | one Markdown issue body per work package (goal, requirements verbatim, components, interfaces, write scope, acceptance checklist, blockers), `issues/create_issues.sh` for the GitHub CLI in dependency order, `issues/issues.csv` for Jira/Linear import |
| `sekkei openapi -o openapi.json` | an OpenAPI 3.0 skeleton from the design's HTTP interfaces: stated `POST /orders/{id}/cancel` operations become path items, other operations get conventional paths, inputs become bodies or query parameters, listed error codes become responses, entities become schemas (field names only) |
| CI | `sekkei lint` and `sekkei check --root .` on every pull request; `sekkei diff old.json design.json` names the packages whose briefs a design change invalidates. See [docs/CI.md](docs/CI.md) |

## Japanese input

Requirements may be written in Japanese. A glossary (actors, verbs, domain nouns,
qualities, technologies), a number grammar (「300ms以内」→ `within 300 ms`, 「毎秒1万件」→
`10000 requests/s`, 「チームは3名」→ `Team of 3`) and a particle-driven reorder
(「利用者は注文を登録できる」→ `Users can register orders`) rewrite each sentence into the
engine's canonical English. No translation is claimed: the notes print every rewrite next
to its source so the reader checks what was actually designed, words the glossary does not
know are listed and dropped rather than guessed, and each requirement keeps its Japanese
sentence as `source (ja)`. [`examples/ja/zaiko.md`](examples/ja/zaiko.md) is a Japanese
inventory spec that designs lint-clean.

## What you get

| file | contents |
|---|---|
| `design.json` | the checkable design: requirements (verbatim), components, interfaces with operations, entities, flows, scored decisions, risks (including the threat model), conventions, work packages with acceptance checks |
| `DESIGN.md` | the same as a document: component graph, layers, contracts, sequence diagram per flow, ADRs with rationale and consequences, traceability matrix |
| `NOTES.md` | **the architect's notes**: (1) the questions the text left open and the engine's answer to each, with its evidence or default and what changes if the real answer differs (or the open questions themselves with `--no-assume`); (1b) requirements placed without a pattern and how; (2) capacity estimates with formula and inputs (Little's law, storage growth, outage backlog, fan-out); (3) effort and schedule from package sizes, waves and team size; (4) STRIDE-lite threat model per component with a proof for each mitigation; (5) what the engine could not decide; (6) how it read the text |
| `trace.json` | every element → the sentences and catalogue rules that produced it |

## The engine

A solution architect's job, mechanised into five deterministic steps
([docs/ENGINE_DESIGN.md](docs/ENGINE_DESIGN.md)):

| step | what happens | where |
|---|---|---|
| analyse | sentences → requirement units with modality (must/should/could), kind (functional / non-functional / constraint), the numbers as metrics (`p95 latency < 5 s`, `>= 1000 events/s`), actors, verbs, objects | `engine/text.py`, `engine/analysis.py` |
| recognise | 40 capability patterns (async delivery with retries, request signing, admin API, event ingest, audit log, batch pipeline, CLI tool, …) and 12 quality attributes matched by signals in the text | `engine/catalog.py` |
| synthesise | patterns bring archetypes (52), which merge into components with interfaces and operations; entities, flows, requirement-to-component mapping; operations are derived from the verbs and objects of the input sentences | `engine/synthesis.py` |
| decide | 26 decision points with 76 options (queue technology, store, isolation strategy, retry scheduling, process topology, auth scheme, secret storage, outbound safety, concurrency control, …) scored ATAM-style: `utility = Σ quality weight × fit`, options ruled out or favoured by the stated constraints; the rationale and the trade-off are written into the decision record | `engine/evaluate.py` |
| package | components are layered, cut into ≤3-component work packages with unique write scopes, ordered by the interfaces they consume; acceptance checks derived from the metrics | `engine/synthesis.py` |

Then the engine does the rest of the architect's job (`--review NOTES.md`): asks the
questions the text left open (`engine/gaps.py`, 18 gap rules with the default taken
meanwhile), sizes the system from the stated numbers (`engine/sizing.py`), estimates
effort and calendar, builds a STRIDE-lite threat model whose threats become risks in the
design (`engine/threats.py`, 44 threat rules over 23 archetypes), and **reviews its own
output**: requirements it did not recognise, quality attributes it has no tactic for,
generic components from the fallback. It says what it does not know instead of hiding it.
Every element carries a trace to the sentences and catalogue rules that produced it.

What the engine produced for the webhook spec (`examples/webhooks/`): 16 components from
the text (plus an audit log and a log-retention job from its own assumed answers), including a partitioned durable queue, worker, retry scheduler carrying the backoff
schedule from the text as a precondition, HMAC signer with a rotation-window secret store,
SSRF-safe outbound client, health policy with notifier, admin and ingest APIs with
operations derived from the sentences (`POST /endpoints`, `DELETE /endpoints/{id}`,
`POST /secrets/{id}/rotate`, `POST /events`), observability; 11 scored decisions; 13 work
packages in 4 waves; zero lint diagnostics; nothing unrecognised. Time: 0.05–0.3 s.

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
(31 components including the engine's twelve, Japanese input, deliverables and the red team; prose in [DESIGN.md](DESIGN.md)). The
test-suite lints it in strict mode and runs `sekkei check` against this repository, so an
import that violates the declared dependency direction fails the build.

Measured on this repository (Apple Silicon laptop, CPython 3.14):

| what | value |
|---|---|
| tests | 279 (incl. 11 real-world specs, 13 specs written by an independent red team, and a mutation fuzz) |
| engine fixtures that must lint clean, be deterministic and be faithful (every bullet a verbatim requirement) | 5 (webhooks, inventory, CLI tool, out-of-catalogue greenhouse, multi-tenant expense SaaS) + the two-line minimal spec + a Japanese spec |
| `sekkei design` on the webhook spec | 0.05–0.3 s |
| `lint` + `check` on the self design | 0.16–0.32 s |
| catalogue | 43 patterns (one more: webhook delivery split from asynchronous delivery), 56 archetypes, 28 decision points / 84 options, 12 quality tactics, 26 risks, 9 language layouts, 44 threats |
| `sekkei deliver` on the SaaS fixture | 32 files (18 ADRs) in about 0.5 s |
| `sekkei redteam` on the SaaS fixture | 18 engine runs in 1–3 s (one engine run per stated sentence, capped at 80) |

## How good is it, measured

[docs/EVALUATION_2026-09-11.md](docs/EVALUATION_2026-09-11.md): three specifications written
after the engine was finished (ride dispatch, document search with LLM summaries, fleet
telemetry over MQTT), scored on ten architect's criteria with the evidence. Result 15/20,
15/20, 16/20 after the fixes that the evaluation itself motivated (11, 12, 12 before). What
a human still adds is listed there: state machines and timing rules inside a use case,
pipelines implied by a consequence ("must not block uploads"), technologies the catalogue
does not know, and naming.

[docs/EVALUATION_2026-09-17.md](docs/EVALUATION_2026-09-17.md): three more unseen specs,
two in Japanese (hospital booking, corporate LMS) and one in English (loan origination
with KYC and an underwriter workflow): 13/12/13 → 15/15/16 after the fixes they motivated.
Japanese lands two points lower on fidelity and operation naming — the cost of a glossary
instead of a parser — and the same everywhere else.

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
