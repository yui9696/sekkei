# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions the engine answered for you (confirm or override)

Each answer is a proposed decision in the design and a bullet in the augmented requirements. To override, state the real answer in your requirements and run again.

| # | topic | question answered | engine's answer | basis | if the real answer differs |
|---|---|---|---|---|---|
| 1 | load | Q-payload | 2 KB typical, 256 KB maximum per record. | default — Typical JSON record sizes; the maximum bounds request bodies. | State the sizes; storage growth and body limits change. |
| 2 | quality | Q-availability | 99.9 % monthly; during an outage work is delayed, nothing accepted is lost. | default — Three nines is achievable with two instances and health-based restarts; anything higher needs multi-region. | State the target and what may be lost; topology and queue durability change. |
| 3 | data | Q-retention | Domain records kept indefinitely; logs and audit history 1 year, then deleted by a nightly job. | default — Deleting domain data is never a safe default; bounded retention for logs and history limits growth and satisfies most data-minimisation rules. | State the retention per record class; the deletion job and capacity change. |
| 4 | data | Q-backup | Daily backups; RPO 24 h, RTO 4 h. | default — The store's own daily backup is the cheapest credible baseline. | State RPO/RTO; the store decision and a restore drill change. |
| 5 | security | Q-auth | Single sign-on with the company's identity provider (OIDC). | evidence: staff/employees mentioned — Internal staff systems normally sit behind the company's SSO. | State the scheme; the authentication decision is rescored. |
| 6 | cost | Q-budget | Existing infrastructure only; no new managed services. | default — The cheapest assumption; every decision already prefers the option needing no new infrastructure. | State the budget; options adding infrastructure become available. |
| 7 | data | Q-migration | Greenfield; no existing data to migrate. | default — Nothing in the text names an existing system. | Name the existing system; a migration package and risk are added. |
| 8 | security | Q-authz | Callers see only resources they own; an admin role may see everything. | default — Ownership scoping is the minimum that prevents cross-tenant access. | State the roles; core operations and acceptance checks change. |
| 9 | resilience | Q-external | 10 s timeout, 5 retries with exponential backoff, work queued while the external system is down. | default — Bounded retries with a durable queue keep the system responsive during a one-hour outage. | State the policy; the outbound client and scheduler contracts change. |
| 10 | operations | Q-alerting | Alert the team channel when the error rate exceeds 1 % for 5 minutes or a queue grows for 10 minutes. | default — Two alerts catch most incidents without paging on noise. | State the rules and the on-call; observability conventions change. |

## 1b. Requirements placed without a catalogue pattern

| requirement | owner(s) | how | detail |
|---|---|---|---|
| R-2 | C-16 Readings processor | synthesised | new component Readings processor (processor) from verb 'validate' and object 'readings' |
| R-3 | C-14 Public HTTP API, C-7 Domain core | surface+core | human actor 'fleet manager': a use case |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| readings per day | 1.73 G | rate × 86,400 s | 20,000 (R-6) |
| storage growth per day (readings) | 3.54 TB | rate × 86,400 × record size | 20,000 (R-6); 2 KB stated in R-13 |
| storage after 30 days (readings) | 106.17 TB | daily growth × 30 | same inputs |
| backlog after a 1 h downstream outage | 72 M readings | rate × outage seconds | 20,000 (R-6); outage length assumed |
| concurrent handlers to sustain the rate (readings) | 4 k | Little's law: rate × mean service time | 20,000 (R-6); mean service time assumed 200 ms |
| in-flight items at the latency target | 200 k | rate × latency target (Little's law upper bound) | 20,000 (R-6) × 10 s (R-6) |
| number of trucks | 5 k | stated | 5,000 trucks (R-6) |
| average rate per truck (if evenly spread) | 4/s | rate ÷ count | 20,000 ÷ 5,000 |

- Assumption: Record size: 2 KB stated in R-13.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **24 person-days**; critical path **13 days**; with a team of 5: **about 16 working days** (4 weeks).
- Wave 1: WP-1
- Wave 2: WP-2, WP-3, WP-4
- Wave 3: WP-5
- Wave 4: WP-6, WP-7
- Wave 5: WP-8, WP-9
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 5; packages in one wave run in parallel up to the team size; a wave lasts max(longest package, person-days ÷ team) and waves run one after another.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-2 Work queue | denial_of_service | A poison item is retried forever and blocks its partition. | Attempt cap and dead-letter; per-partition concurrency cap. | an always-failing item ends in the dead-letter after the cap |
| C-2 Work queue | tampering | Items are processed twice after a crash between call and ack. | Idempotent processing with the item id; ack only after the outcome is recorded. | kill the worker mid-call; the item is redelivered exactly once more |
| C-8 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-10 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-10 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-14 Public HTTP API | spoofing | Requests without a verified caller identity reach domain operations. | Authenticate every route in one middleware; deny by default. | every route returns 401 without credentials |
| C-14 Public HTTP API | tampering | Malformed or oversized bodies reach the core. | Schema-validate and size-limit at the surface; reject before parsing fully. | fuzz the body; oversize returns 413 |
| C-14 Public HTTP API | denial_of_service | A single caller saturates the service. | Per-caller rate limit and request timeouts. | burst from one key returns 429; others unaffected |
| C-14 Public HTTP API | information_disclosure | Stack traces or internal ids leak in error responses. | Map exceptions to fixed error shapes; log details server-side only. | no traceback text in any 4xx/5xx body |

## 5. What the engine could not decide

### Requirements the catalogue did not recognise

These are kept as requirements and assigned to the generic core/surface; refine their components and interfaces.

- **R-2**: The service validates readings, drops duplicates, and stores them.
- **R-3**: Fleet managers view the latest reading per truck and a 24-hour chart per sensor.

### Assumptions made

- 1 sentence(s) were read but not taken as requirements (listed in the notes §6b); if one of them is a requirement, make it a bullet.

### Decisions taken (scored trade-offs)

- D-1 Caller authentication: **API keys per customer, hashed at rest, sent as a bearer token**
- D-2 Primary store: **PostgreSQL**
- D-3 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-4 Work queue technology: **Managed broker (SQS/RabbitMQ/Kafka)**
- D-5 Time-series storage: **TimescaleDB hypertables in PostgreSQL (time partitioning, compression, retention policies)**
- D-6 Concurrency control for conflicting writes: **Optimistic concurrency: version column checked on every update; conflict returns 409 and the caller retries**
- D-7 Redundancy for the availability target: **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
- D-8 Assumed answer: load (Q-payload): **2 KB / 256 KB**
- D-9 Assumed answer: quality (Q-availability): **99.9 %**
- D-10 Assumed answer: data (Q-retention): **indefinite / 1 year**
- D-11 Assumed answer: data (Q-backup): **daily / 24 h / 4 h**
- D-12 Assumed answer: security (Q-auth): **OIDC**
- D-13 Assumed answer: cost (Q-budget): **existing only**
- D-14 Assumed answer: data (Q-migration): **greenfield**
- D-15 Assumed answer: security (Q-authz): **owner-scoped + admin role**
- D-16 Assumed answer: resilience (Q-external): **10 s / 5 retries / queue**
- D-17 Assumed answer: operations (Q-alerting): **error rate + queue growth**

## 6. How the text was read

- Patterns recognised: notification, batch_pipeline, mqtt_ingest, sftp_export, sms_notification, import_export, auth
- Quality attributes (weight): consistency 0.6, durability 1.0, performance 0.9, availability 0.9, operability 0.8, simplicity 0.7
- Constraint tokens: broker, containers, durable_required, idp, nightly_batch, on_prem, postgres, timeseries_db; languages: java; team: 5

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | batch_pipeline, mqtt_ingest | — | — |
| R-2 | functional | must | **none** | consistency | — |
| R-3 | functional | must | **none** | — | — |
| R-4 | functional | must | notification, sms_notification | — | — |
| R-5 | functional | must | batch_pipeline, sftp_export, import_export | — | — |
| R-6 | nonfunctional | must | — | performance | p95 latency at 5,000, 20,000 <= 10 s |
| R-7 | nonfunctional | must | — | consistency, durability | lost or duplicate updates under concurrent writes to one record = 0 updates |
| R-8 | nonfunctional | should | batch_pipeline | — | time at 5 years 90 days |
| R-9 | constraint | must | — | simplicity | — |
| R-10 | constraint | must | mqtt_ingest | — | — |
| R-11 | functional | must | batch_pipeline | operability, compliance | — |
| R-12 | functional | could | auth | operability | — |
| R-13 | nonfunctional | must | — | — | size at 2 KB <= 256 kb |
| R-14 | nonfunctional | must | — | durability, availability | ratio 99.9 % |
| R-15 | nonfunctional | should | — | — | time at 4 h 24 h |
| R-16 | nonfunctional | should | — | durability | time at 5 10 s |
| R-17 | nonfunctional | must | — | operability | ratio at 5 minutes, 10 minutes 1 % |
| R-18 | constraint | must | auth | security | — |
| R-19 | constraint | must | — | — | — |
| R-20 | constraint | must | — | — | — |

## 6b. What the structure pass found

- **Sentences read but not taken as requirements** (make one a bullet if it is a requirement): “Trucks send sensor readings to a central service that keeps the fleet manager in” (introduction before the first heading)
