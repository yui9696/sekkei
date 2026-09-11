# How good are the designs? An evaluation on three unseen specifications (2026-09-11)

The engine was developed against four fixtures (webhooks, inventory, CLI tool, greenhouse).
To measure it rather than admire it, three new specifications in different domains were
written *after* the engine was finished and run through `sekkei design` unchanged:

| spec | domain | why it is hard for a catalogue |
|---|---|---|
| `examples/eval/ride.md` | ride dispatch: matching, offers with timeouts, live positions, Stripe, operator alerts | geospatial matching, a state machine (offer → accept/decline), real-time fan-out |
| `examples/eval/docsearch.md` | internal document search with LLM summaries | an asynchronous processing pipeline (extract → chunk → embed → index), an external API with a rate limit, per-team visibility |
| `examples/eval/telemetry.md` | fleet telemetry over MQTT, alerts by SMS, nightly CSV to SFTP | non-HTTP transport, time-series store, 20,000 readings/s |

Scoring: ten criteria a senior architect would apply, each 0 (missing/wrong), 1 (partly),
2 (what I would have drawn). Scores are my judgement (the author's), stated with the
evidence so they can be disputed. "Before" is the engine as committed at `c214afe`;
"after" is after the fixes the evaluation itself motivated (same day, listed below).

## Scores

| criterion | ride | docsearch | telemetry |
|---|---|---|---|
| 1. Requirements fidelity (every bullet verbatim, classified right) | 2 → 2 | 2 → 2 | 2 → 2 |
| 2. Numbers preserved as metrics / preconditions | 1 → 1 | 2 → 2 | 1 → 1 |
| 3. Component decomposition (no major omission, no spurious component) | 0 → 1 | 1 → 1 | 0 → 2 |
| 4. Interfaces and operations (use cases become operations, names sensible) | 0 → 1 | 0 → 1 | 1 → 1 |
| 5. Decisions correct for the constraints, rationale meaningful | 2 → 2 | 2 → 2 | 1 → 2 |
| 6. Data model (entities the domain needs) | 0 → 1 | 0 → 1 | 1 → 2 |
| 7. Work packages (grouping, dependencies, acceptance) | 1 → 1 | 1 → 1 | 1 → 1 |
| 8. Architect's notes (questions relevant, answers sane, capacity right) | 1 → 2 | 1 → 1 | 1 → 1 |
| 9. Threats and risks relevant | 2 → 2 | 2 → 2 | 2 → 2 |
| 10. Honesty (what it could not do is flagged, nothing invented silently) | 2 → 2 | 1 → 2 | 2 → 2 |
| **total / 20** | **11 → 15** | **12 → 15** | **12 → 16** |

## Evidence, per spec

### Ride dispatch (11 → 15)

Before: no API surface at all (the text never says "API"; requests come from "the mobile
app"), so riders' use cases were placed on the push gateway. No geospatial component. No
Trip/Ride entity. "Riders can rate a trip …" was synthesised into a "History processor"
because *rider* was not in the actor lexicon. The rate was assumed at 20 requests/s
although the text implies 2,000 drivers × one position every 5 s = 400/s. Right from the
start: OIDC (stated), PostgreSQL, optimistic concurrency, redundancy for the availability
target, a Payments component with the provider, the 30-day retention as a metric.

After: a Public HTTP API with `POST /rides/{id}/request`, `POST /drivers/{id}/accept|decline`,
`POST /trips/{id}/rate`, `GET /trips/{id}`; a Geospatial index (`update_position`, `nearest`);
Ride and Trip entities; the implied rate derived and shown with its formula (`2,000 drivers ÷
every 5 s`), and used as the answer to the rate question. Still missing: the **offer state
machine** (15 s acceptance window, three declines, next batch) is nowhere in a contract — the
numbers stay in the requirement text only; Redis is available but no decision uses it; some
derived operation names are noise (`POST /batchs/{id}/request`, `GET /histories/{id}`).

### Document search (12 → 15)

Before: search, file storage, ML inference, batch report and notification all recognised,
but the HTTP API exposed a single operation because operations were only derived from
sentences of the API's own pattern. `caches it` did not match the cache pattern. A
Geospatial index appeared by mistake (`within 800 ms` matched `within N m`). "rate limit
of 60 requests per minute" — an *external* API's limit — activated our own rate limiter.

After: the API has upload, tag, search, passages, delete; the cache is recognised; the
geo false positive is fixed; a Document entity exists. Still missing: the **asynchronous
pipeline** ("must not block uploads") — there is no queue/worker between upload and
embedding, which is the one component a human would insist on; the rate-limiter
misreading remains (it should be a client-side throttle on the outbound calls to the
embedding API); chunks/embeddings are not entities.

### Fleet telemetry (12 → 16)

Before: ingestion was an HTTP "Ingest API" although the text says MQTT with an existing
broker; SMS became an email provider; SFTP export had no target; the queue decision picked
a PostgreSQL table at 20,000 readings/s; "validates readings, drops duplicates" produced a
"Drops processor" because *drop* was not a verb.

After: an MQTT consumer with an idempotent `on_message` contract acknowledging only after
persistence, the MQTT broker as an external component, an SFTP server target and an SMS
provider, the managed broker (Kafka is available) chosen because the stated rate exceeds
the PostgreSQL option's ceiling, a Reading entity with `speed, fuel_level,
engine_temperature, position` taken from the parenthesis in the text, and a "Readings
processor" for validation/de-duplication. Still missing: TimescaleDB is not recognised as a
time-series store (a decision point is missing), the 5-minute threshold rule is not a
contract, and the 90-days/5-years retention pair is mangled into one metric.

## What the evaluation changed in the engine (same day)

- Actor lexicon: riders, passengers, fleet managers, team leads, trucks/vehicles (as
  non-human subjects), and more.
- Every use case with a human subject becomes an operation of the primary surface,
  regardless of which pattern the sentence matched.
- Domain entities are extracted from the text (objects of create/request/upload/…
  verbs, determiner+noun, frequent plurals), with attributes read from a parenthesis
  after the noun.
- New archetypes and patterns: MQTT consumer + broker, SFTP target, SMS provider,
  geospatial index; the HTTP ingest surface is dropped when devices publish over MQTT.
- Options carry a rate ceiling; the stated peak rate rules out a queue that cannot carry it.
- Implied rates (`N things every T seconds`) are derived for the capacity estimate and the
  rate answer.
- Verbs added: request, accept, decline, offer, charge, tag, extract, split, index, drop.

## What a human architect still adds (honest list)

1. **State machines and timing rules** inside a use case (offer windows, retry-after-N,
   threshold-for-M-minutes). The numbers are kept verbatim but no contract carries them
   unless a pattern has a designated sink.
2. **Pipelines implied by a non-functional sentence** ("must not block uploads" ⇒ a queue
   and a worker). The engine reacts to capability words, not to consequences.
3. **Technology the catalogue does not know** (TimescaleDB, pgvector as a vector store,
   Redis as a geo index). Unknown names are inert.
4. **Naming.** Derived operation and entity names are mechanical (`/batchs`, `Duplicate`);
   they are correct enough to brief an agent, not to publish.
5. **Judgement about redundancy of components.** 12–16 components for a team of 3–5 is on
   the heavy side; the notes say so, the engine does not merge.

Where this leaves the claim: on business back-ends with recognisable capabilities the
engine produces the skeleton a senior architect would draw, with the decisions right for
the stated constraints and the honest gaps listed. It does not replace the architect's
reading of consequences and timing; it makes that reading a review of a finished draft
instead of a blank page. Deterministic, 0.1–0.5 s per design.

## Debugging pass (same day, after the evaluation)

A stress harness ran 221 synthetic and deliberately malformed documents through the
engine and every downstream tool (lint, JSON round-trip, DESIGN.md, every brief, plan,
diff, drift check, interview): no exception, no lint error, byte-identical output across
runs and across three `PYTHONHASHSEED` values. What it found and what changed:

- An empty or title-only input produced a full design made of assumptions. Now refused
  (`S008: no requirements in the input`).
- The CLI raised tracebacks on a missing file, a non-UTF-8 file and an output path in a
  missing directory. Now one-line errors; parent directories are created.
- Work packages batched unrelated components of one layer (authentication + scheduler +
  a domain processor). Only infrastructure may share a package now; domain and
  synthesised components get their own.
- Entry-point interfaces (jobs, screens, command lines, the MQTT consumer) were reported
  as orphans. Exempted.
- Synthesised contracts had every type as `…`; parameters whose name matches an entity
  now carry the entity type.
- Timing rules inside a use case ("accept within 15 seconds") reach the derived
  operation's precondition.
- TimescaleDB and pgvector are recognised; a time-series storage decision and a vector
  index decision exist.
- The interview ran the engine three times per turn; the result is memoised.
- A bullet without a space after the dash is still a bullet.
