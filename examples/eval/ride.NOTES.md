# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions the engine answered for you (confirm or override)

Each answer is a proposed decision in the design and a bullet in the augmented requirements. To override, state the real answer in your requirements and run again.

| # | topic | question answered | engine's answer | basis | if the real answer differs |
|---|---|---|---|---|---|
| 1 | load | Q-rate | 400 updates/s sustained (derived); no peak factor assumed for a fixed-interval feed. | evidence: 2,000 drivers (R-7) ÷ every 5 s (R-3) — Derived from the text: 2,000 drivers (R-7) ÷ every 5 s (R-3). | State the measured rate; capacity estimates and the queue decision change. |
| 2 | load | Q-payload | 2 KB typical, 256 KB maximum per record. | default — Typical JSON record sizes; the maximum bounds request bodies. | State the sizes; storage growth and body limits change. |
| 3 | quality | Q-availability | 99.9 % monthly; during an outage work is delayed, nothing accepted is lost. | default — Three nines is achievable with two instances and health-based restarts; anything higher needs multi-region. | State the target and what may be lost; topology and queue durability change. |
| 4 | data | Q-retention | Domain records kept indefinitely; logs and audit history 1 year, then deleted by a nightly job. | default — Deleting domain data is never a safe default; bounded retention for logs and history limits growth and satisfies most data-minimisation rules. | State the retention per record class; the deletion job and capacity change. |
| 5 | data | Q-backup | Daily backups; RPO 24 h, RTO 4 h. | default — The store's own daily backup is the cheapest credible baseline. | State RPO/RTO; the store decision and a restore drill change. |
| 6 | resilience | Q-external | 10 s timeout, 5 retries with exponential backoff, work queued while the external system is down. | default — Bounded retries with a durable queue keep the system responsive during a one-hour outage. | State the policy; the outbound client and scheduler contracts change. |
| 7 | cost | Q-budget | Existing infrastructure only; no new managed services. | default — The cheapest assumption; every decision already prefers the option needing no new infrastructure. | State the budget; options adding infrastructure become available. |
| 8 | data | Q-migration | Greenfield; no existing data to migrate. | default — Nothing in the text names an existing system. | Name the existing system; a migration package and risk are added. |

## 1b. Requirements placed without a catalogue pattern

| requirement | owner(s) | how | detail |
|---|---|---|---|
| R-5 | C-13 Trip domain | aggregate | the sentence speaks of trip, owned by Trip domain |
| R-6 | C-11 Public HTTP API, C-3 Domain core | surface+core | human actor 'driver': a use case |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| implied update rate | 400/s | count × items per report ÷ interval | 2,000 drivers (R-7) ÷ every 5 s (R-3) |
| implied updates per day | 34.56 M | implied rate × 86,400 s | 2,000 drivers (R-7) ÷ every 5 s (R-3) |
| storage growth per day (updates) | 70.78 GB | implied rate × 86,400 × record size | 2,000 drivers (R-7) ÷ every 5 s (R-3); 2 KB stated in R-14 |
| updates per day | 34.56 M | rate × 86,400 s | 400 (R-13) |
| storage growth per day (updates) | 70.78 GB | rate × 86,400 × record size | 400 (R-13); 2 KB stated in R-14 |
| storage after 30 days (updates) | 2.12 TB | daily growth × 30 | same inputs |
| backlog after a 1 h downstream outage | 1.44 M updates | rate × outage seconds | 400 (R-13); outage length assumed |
| concurrent handlers to sustain the rate (updates) | 80 | Little's law: rate × mean service time | 400 (R-13); mean service time assumed 200 ms |
| in-flight items at the latency target | 800 | rate × latency target (Little's law upper bound) | 400 (R-13) × 2 s (R-7) |
| number of drivers | 2 k | stated | 2,000 drivers (R-7) |
| average rate per driver (if evenly spread) | 0.2/s | rate ÷ count | 400 ÷ 2,000 |
| number of drivers | 2 k | stated | 2,000 drivers (R-13) |
| average rate per driver (if evenly spread) | 0.2/s | rate ÷ count | 400 ÷ 2,000 |

- Assumption: Record size: 2 KB stated in R-14.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **42 person-days**; critical path **27 days**; with a team of 4: **about 30 working days** (6 weeks).
- Wave 1: WP-1, WP-2
- Wave 2: WP-3, WP-4, WP-5, WP-6
- Wave 3: WP-7
- Wave 4: WP-10, WP-8, WP-9
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 4; packages in one wave run in parallel up to the team size; a wave lasts max(longest package, person-days ÷ team) and waves run one after another.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-5 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-5 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-7 Payments | tampering | Double charge on retry. | Idempotency keys on every charge; reconcile provider webhooks. | retrying a charge with the same key charges once |
| C-11 Public HTTP API | spoofing | Requests without a verified caller identity reach domain operations. | Authenticate every route in one middleware; deny by default. | every route returns 401 without credentials |
| C-11 Public HTTP API | tampering | Malformed or oversized bodies reach the core. | Schema-validate and size-limit at the surface; reject before parsing fully. | fuzz the body; oversize returns 413 |
| C-11 Public HTTP API | denial_of_service | A single caller saturates the service. | Per-caller rate limit and request timeouts. | burst from one key returns 429; others unaffected |
| C-11 Public HTTP API | information_disclosure | Stack traces or internal ids leak in error responses. | Map exceptions to fixed error shapes; log details server-side only. | no traceback text in any 4xx/5xx body |
| C-12 Push gateway | denial_of_service | Unbounded connections. | Cap connections per principal; idle timeouts. | connection cap enforced |

## 5. What the engine could not decide

### Requirements the catalogue did not recognise

These are kept as requirements and assigned to the generic core/surface; refine their components and interfaces.

- **R-5**: Riders can rate a trip and see their trip history; operators can view all active trips on a dashboard.
- **R-6**: Operators receive an alert when no driver accepts a request within 2 minutes.

### Assumptions made

- 1 sentence(s) were read but not taken as requirements (listed in the notes §6b); if one of them is a requirement, make it a bullet.

### Decisions taken (scored trade-offs)

- D-1 Caller authentication: **OAuth2 / OIDC with the platform's identity provider**
- D-2 Primary store: **PostgreSQL**
- D-3 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-4 Concurrency control for conflicting writes: **Optimistic concurrency: version column checked on every update; conflict returns 409 and the caller retries**
- D-5 Redundancy for the availability target: **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
- D-6 Assumed answer: load (Q-rate): **400 updates/s**
- D-7 Assumed answer: load (Q-payload): **2 KB / 256 KB**
- D-8 Assumed answer: quality (Q-availability): **99.9 %**
- D-9 Assumed answer: data (Q-retention): **indefinite / 1 year**
- D-10 Assumed answer: data (Q-backup): **daily / 24 h / 4 h**
- D-11 Assumed answer: resilience (Q-external): **10 s / 5 retries / queue**
- D-12 Assumed answer: cost (Q-budget): **existing only**
- D-13 Assumed answer: data (Q-migration): **greenfield**

## 5b. Domain model read from the text

Entities with the fields, relations, states and invariants the reader found in the sentences named in the last column. It reads a fixed set of phrasings (attribute lists, 'has/records/carries A, B and C', possessives, 'set its X', transactional and state verbs, 'then'/'until'/'otherwise' sequences, arrow lists, 'never/cannot' rules); a fact stated another way is not here, and a field or state that is here may still be misread — check each row against its requirement. Each aggregate is a component.

| entity | fields (type) | relations | states | invariants | from |
|---|---|---|---|---|---|
| Trip | — | — | active; transitions not stated | — | R-5 |
| Ride | — | — | — | — | R-1 |

## 6. How the text was read

- Patterns recognised: observability, auth, batch_pipeline, geo, realtime, payments
- Quality attributes (weight): consistency 0.57, durability 1.0, performance 0.83, availability 0.83, operability 0.74, simplicity 0.8
- Constraint tokens: containers, durable_required, idp, nightly_batch, postgres, redis, single_region; languages: go; team: 4

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | geo | — | — |
| R-2 | functional | must | batch_pipeline | performance | — |
| R-3 | functional | must | realtime | — | — |
| R-4 | functional | must | payments | — | — |
| R-5 | functional | must | **none** | operability | — |
| R-6 | functional | must | **none** | performance, operability | — |
| R-7 | nonfunctional | must | — | consistency, performance | p95 latency at 300, 2,000 <= 2 s |
| R-8 | nonfunctional | should | — | durability | occurrences of the forbidden action (request, complete) = 0 occurrences |
| R-9 | nonfunctional | should | — | — | time 30 days |
| R-10 | constraint | must | geo | simplicity | — |
| R-11 | constraint | must | auth | security | — |
| R-12 | functional | must | batch_pipeline | operability, compliance | — |
| R-13 | nonfunctional | must | — | performance | sustained rate at 2,000, 5 s 400 updates /s |
| R-14 | nonfunctional | must | — | — | size at 2 KB <= 256 kb |
| R-15 | nonfunctional | must | — | durability, availability | ratio 99.9 % |
| R-16 | nonfunctional | should | — | — | time at 4 h 24 h |
| R-17 | nonfunctional | should | — | durability | time at 5 10 s |
| R-18 | constraint | must | — | — | — |
| R-19 | constraint | must | — | — | — |

## 6b. What the structure pass found

- **Sentences read but not taken as requirements** (make one a bullet if it is a requirement):
    - “A city taxi cooperative needs a backend that matches ride requests to nearby drivers and tracks each trip.” — introduction before the first heading
