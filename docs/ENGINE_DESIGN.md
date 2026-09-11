# The design engine — design document

`sekkei design REQ.md` turns a requirements text into a complete, lint-clean design
without calling a model. This document is the design of that engine. It was written
before the code; the code is checked against it (`examples/self/design.json`).

## 1. What a solution architect actually does

Strip the job to its mechanics and it is five steps, each of which can be made
deterministic to a useful degree:

| step | the architect's act | the engine's act |
|---|---|---|
| 1 analyse | read the requirements; separate function, quality, constraint; find the numbers; find the actors and the things | `engine.analysis`: sentence model with modality, kind, quantities, actors, nouns, verbs, quality signals |
| 2 recognise | "this is an async delivery problem with signing and an admin API" | `engine.catalog`: capability patterns matched by signals; each pattern brings components, interfaces, entities, flows, decisions, risks |
| 3 synthesise | draw the boxes and the arrows; write the contracts | `engine.synthesis`: instantiate and merge patterns, wire `requires`, map requirements to components, derive entities from nouns and numbers |
| 4 decide | pick the queue, the store, the integration style; write down why | `engine.evaluate`: each decision point scores its options against the constraints and quality weights of *this* input; the winner and the trade-off become a `Decision` |
| 5 package | cut the work so that people can start | `engine.synthesis.package`: layer the component graph, cut it into ≤4-component packages, assign write scopes from the language layout, derive acceptance checks from metrics |

Then the architect reviews. The engine reviews too (`engine.evaluate.review`): unaddressed
quality attributes, unrecognised sentences, assumptions it had to make. It says what it
does not know.

## 2. What the engine refuses to pretend

- It has no understanding of English. It has a sentence segmenter, a modality lexicon,
  a quantity grammar, a verb lexicon and a set of *signals* per pattern. A requirement
  it cannot classify is still a requirement (it is never dropped), but it is tagged
  `unrecognised` in the review and gets the generic decomposition.
- Its catalogue is finite. Twenty-odd patterns cover the bulk of business back-ends,
  CLIs and pipelines. A novel domain gets the layered fallback (surface / core / storage /
  integration / operations) plus every quality tactic that the signals justify, and the
  review says so. This is exactly the point at which a human architect earns their pay,
  and the engine says that in its output rather than hiding it.
- Every element it emits carries a trace: which sentences and which catalogue rules
  produced it (`trace.json`, and `rationale`/`description` fields). No element exists
  without a cause.
- Same input, same output, byte for byte. That is a test.

## 3. Modules

```
sekkei/engine/
  text.py       sentence segmentation, quantities, modality, actors, nouns/verbs, signals
  analysis.py   Analysis = requirements + qualities + constraints + capabilities matched
  catalog.py    the knowledge base: patterns, tactics, technology rules, layouts
  synthesis.py  Analysis + catalogue -> Design (components, interfaces, entities, flows,
                requirement mapping, packages, acceptance)
  evaluate.py   decision scoring (utility per option), coverage review, assumptions
  repair.py     lint -> deterministic fixes -> lint, until clean
  __init__.py   design(text) -> EngineResult(design, analysis, review, trace)
```

Dependency direction: `__init__ → repair → {synthesis, evaluate} → {analysis, catalog} →
text → model`. `repair` uses `rules`. Nothing in the engine imports `llm`.

## 4. The knowledge base (catalog)

A **pattern** is a record:

```
Pattern(id, name, signals=[keywords/regexes], components=[Archetype], entities=[...],
        flows=[...], decisions=[DecisionPoint], risks=[...], requires=[pattern ids])
Archetype(key, name, kind, responsibility, layer, operations=[...], needs=[archetype keys],
          quality_tactics=[...])
DecisionPoint(key, title, context, options=[Option(name, pros, cons, fit={quality: score},
              needs=[constraint tokens], excludes=[...])], affects=[archetype keys])
```

Patterns are merged by archetype key, so two patterns that both need a `store` produce
one Store component with the union of operations. Archetype `needs` become `requires`
edges to the interface of the needed archetype.

**Quality tactics** map a quality attribute (performance, availability, durability,
isolation, security, operability, scalability, maintainability, compliance, cost) to
archetypes, operations, decision preferences and acceptance-check templates. A quality
is *active* when the text carries its signals; its weight grows with the number of
sentences and with `must` modality.

**Technology rules** read the constraints (languages, stores, queues, platforms, team
size, deployment) and restrict the options at decision points: an option whose `needs`
are not in the constraints is unavailable; an option in `excludes` conflict is dropped.

**Layouts** map a language to a file layout for write scopes and test commands.

## 5. Decisions as scored trade-offs

For a decision point with options *o* and the active qualities *q* with weights *w*:

    utility(o) = Σ_q w_q · fit_o(q)  −  penalty(o, constraints)

The best option wins; the `Decision.rationale` states the scores and the two strongest
qualities that decided it; `consequences` states what the losing options would have
bought. Ties break by catalogue order (documented default). Rejected options stay in the
record with their pros and cons. This is the ATAM utility tree, mechanised.

## 6. Packaging

1. Component layers from the dependency graph (`graph.layers`).
2. Walk layers bottom-up; group components of the same layer and pattern into packages
   of at most 4 components; a package's `depends_on` is every package that implements an
   interface its components require.
3. Write scope: `layout.module(component)` and `layout.test(component)` per component,
   so no two packages share files.
4. Acceptance: one `test` check per package (`layout.test_command` on its test files);
   one `metric` check per non-functional requirement satisfied by the package;
   one `command` check for constraints that have a checkable form (e.g. dependency
   policies are turned into a grep).

## 7. Repair loop

`rules.lint` is run on the synthesised design. A small set of repairs is applied for
diagnostics that synthesis can legitimately fix (a requirement no component claims →
attach to the surface component of its capability and note it; an orphan interface →
attach a consumer or drop; an implicit package dependency → make it explicit). Anything
else is left as a diagnostic in the review. The final design must have zero errors or
the engine reports failure rather than returning a broken file.

## 7b. The architect's notes (what an architect delivers besides the diagram)

A design document is not the whole job. The engine also produces, deterministically:

| deliverable | module | method |
|---|---|---|
| **Questions** — what the requirements do not say and an architect would ask before committing | `engine/gaps.py` | gap rules over the analysis (no language, no store, no rate, no latency/availability target, no retention, no auth statement, no team size, no deployment target, external calls without failure policy, PII without compliance statement, …). Each question states the default assumption the engine used, so the design is usable before the answer arrives and the answer changes exactly one thing. |
| **Capacity estimates** — how big is this | `engine/sizing.py` | the stated rates, counts, latencies and durations run through Little's law and storage arithmetic under stated assumptions (payload size, mean service time, fan-out). Every number shows its formula and inputs; if a rate is missing, the estimate says so and the question above asks for it. |
| **Threat model** — STRIDE-lite | `engine/threats.py` | a table of threats per archetype (surfaces: spoofing, tampering, DoS, information disclosure; outbound client: SSRF, redirects, DNS rebinding; secrets: exposure at rest/in logs; queue: poison and replay; files: content-type and traversal; …). Threats become risks in the design with mitigations, so they reach the briefs. |
| **Effort and schedule** | `engine/sizing.py` | package sizes (S/M/L → person-days, an assumption), waves, critical path and team size → total effort and calendar length. |
| **Sequence diagrams** | `render.py` | every flow as a Mermaid `sequenceDiagram`. |

`sekkei design --review NOTES.md` writes all of these with the self-review;
`sekkei ask REQ.md` prints the questions alone; `sekkei template` prints the
requirements template that makes the engine's job easiest.

## 7c. Autonomy: answering its own questions and owning every requirement

Two things were left to a human in 7b. Both are now decided by the engine and marked
as decisions the human may override, which is what an architect does when the client is
not in the room.

**Answers (`engine/answers.py`).** Every gap question has an answer rule: first evidence
in the text (a CLI with `no network` → SQLite; customers and an admin surface → API keys;
staff and an identity provider → OIDC; counts ≥ 10,000 → PostgreSQL), else a defensible
default (team of 2; p95 300 ms reads / 1 s writes; 99.9 % monthly; 90-day retention;
daily backups RPO 24 h / RTO 4 h; timeouts 10 s with five retries; personal data →
deletion on request). Each answer is appended to the requirements as bullets under
engine-marked sections, the text is analysed again so the answer flows through the normal
path (constraint tokens, metrics, team size), and a `Decision` with status `proposed`
records the question, the options considered, the choice, the evidence and what to change
if the real answer differs. Requirements created this way carry `rationale: assumed by the
engine (Q-…)`. `sekkei design --no-assume` turns this off; `sekkei ask` still lists the
raw questions.

**Owners (`engine/owners.py`).** A functional requirement no pattern recognised is placed
by, in order: (1) lexical overlap between the sentence's nouns/verbs and each existing
component's name, responsibility and operation names — a score of at least two shared
tokens wins; (2) a human actor with a view/manage verb → the surface and the core;
(3) otherwise a **new component is synthesised** from the verb class and the object:
read/poll/measure/receive → "<Object> reader" (integration layer, required by the core),
open/close/switch/adjust/control → "<Object> controller" (integration layer), compute/
transform/aggregate/parse → "<Object> processor" (core layer), with an interface whose
operations come from the sentence's verbs and objects, a path from the layout, and a place
in a work package. Every placement is recorded in the trace and in the notes with how it
was made (`matched (score n)`, `surface+core`, `synthesised`), so a wrong owner is one
line to spot.

## 8. Tests

- Determinism: `design(text)` twice → identical JSON.
- Fidelity: every input sentence with modality appears as a requirement, verbatim; every
  quantity in the text appears in a metric or a pre/post condition.
- Lint: the output of every fixture is lint-clean (strict, all groups).
- Pattern expectations per fixture (e.g. the webhook spec yields signing with rotation,
  a retry scheduler carrying the backoff schedule, a per-endpoint isolation decision).
- Fallback: an out-of-catalogue text yields the layered design and an `unrecognised`
  review entry, and still lints clean.
- The whole pipeline end to end through the CLI, including briefs from the result.
