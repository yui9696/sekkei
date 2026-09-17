# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions the engine answered for you (confirm or override)

Each answer is a proposed decision in the design and a bullet in the augmented requirements. To override, state the real answer in your requirements and run again.

| # | topic | question answered | engine's answer | basis | if the real answer differs |
|---|---|---|---|---|---|
| 1 | stack | Q-deploy | Stateless containers behind an existing ingress, several instances. | default — The default for a networked service; keeps instances interchangeable. | State the deployment; topology, statelessness conventions and store options change. |
| 2 | quality | Q-availability | 99.9 % monthly; during an outage work is delayed, nothing accepted is lost. | default — Three nines is achievable with two instances and health-based restarts; anything higher needs multi-region. | State the target and what may be lost; topology and queue durability change. |
| 3 | data | Q-retention | Domain records kept indefinitely; logs and audit history 1 year, then deleted by a nightly job. | default — Deleting domain data is never a safe default; bounded retention for logs and history limits growth and satisfies most data-minimisation rules. | State the retention per record class; the deletion job and capacity change. |
| 4 | data | Q-backup | Daily backups; RPO 24 h, RTO 4 h. | default — The store's own daily backup is the cheapest credible baseline. | State RPO/RTO; the store decision and a restore drill change. |
| 5 | security | Q-authz | Callers see only resources they own; an admin role may see everything. | default — Ownership scoping is the minimum that prevents cross-tenant access. | State the roles; core operations and acceptance checks change. |
| 6 | resilience | Q-external | 10 s timeout, 5 retries with exponential backoff, work queued while the external system is down. | default — Bounded retries with a durable queue keep the system responsive during a one-hour outage. | State the policy; the outbound client and scheduler contracts change. |
| 7 | cost | Q-budget | Existing infrastructure only; no new managed services. | default — The cheapest assumption; every decision already prefers the option needing no new infrastructure. | State the budget; options adding infrastructure become available. |
| 8 | data | Q-migration | Greenfield; no existing data to migrate. | default — Nothing in the text names an existing system. | Name the existing system; a migration package and risk are added. |
| 9 | operations | Q-alerting | Alert the team channel when the error rate exceeds 1 % for 5 minutes or a queue grows for 10 minutes. | default — Two alerts catch most incidents without paging on noise. | State the rules and the on-call; observability conventions change. |

## 1b. Requirements placed without a catalogue pattern

| requirement | owner(s) | how | detail |
|---|---|---|---|
| R-1 | C-15 Public HTTP API, C-4 Domain core | surface+core | human actor 'employee': a use case |
| R-10 | C-15 Public HTTP API, C-4 Domain core | surface+core | human actor 'member': a use case |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| requests per day | 86.4 k | rate × 86,400 s | 60 (R-12) |
| storage growth per day (requests) | 1.81 TB | rate × 86,400 × record size | 60 (R-12); 20 MB stated in R-2 |
| storage after 30 days (requests) | 54.36 TB | daily growth × 30 | same inputs |
| backlog after a 1 h downstream outage | 3.6 k requests | rate × outage seconds | 60 (R-12); outage length assumed |
| concurrent handlers to sustain the rate (requests) | 0.2 | Little's law: rate × mean service time | 60 (R-12); mean service time assumed 200 ms |
| in-flight items at the latency target | 0.8 | rate × latency target (Little's law upper bound) | 60 (R-12) × 800 ms (R-8) |
| number of documents | 50 k | stated | 50,000 documents (R-8) |
| average rate per document (if evenly spread) | 0/s | rate ÷ count | 60 ÷ 50,000 |

- Assumption: Record size: 20 MB stated in R-2.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **28 person-days**; critical path **12 days**; with a team of 3: **about 14 working days** (3 weeks).
- Wave 1: WP-1, WP-2, WP-3, WP-4
- Wave 2: WP-5, WP-6, WP-7, WP-8
- Wave 3: WP-9
- Wave 4: WP-10, WP-11
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 3; packages in one wave run in parallel up to the team size; a wave lasts max(longest package, person-days ÷ team) and waves run one after another.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-3 File storage | tampering | Uploaded content is not what its type claims. | Sniff content type; reject executables; size limits. | renamed executable is rejected |
| C-3 File storage | elevation | Path traversal through user-supplied names. | Generate storage keys; never use client names as paths. | name '../x' cannot escape the store |
| C-5 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-7 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-7 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-11 Model server | denial_of_service | Adversarial or oversized inputs exhaust inference capacity. | Input size limits; batching with timeouts. | oversize input rejected before inference |
| C-14 Reporting | information_disclosure | Aggregates over small groups re-identify people. | Suppress rows below a minimum group size in person-level reports. | a report over a group of one shows no row |
| C-15 Public HTTP API | spoofing | Requests without a verified caller identity reach domain operations. | Authenticate every route in one middleware; deny by default. | every route returns 401 without credentials |
| C-15 Public HTTP API | tampering | Malformed or oversized bodies reach the core. | Schema-validate and size-limit at the surface; reject before parsing fully. | fuzz the body; oversize returns 413 |
| C-15 Public HTTP API | denial_of_service | A single caller saturates the service. | Per-caller rate limit and request timeouts. | burst from one key returns 429; others unaffected |
| C-15 Public HTTP API | information_disclosure | Stack traces or internal ids leak in error responses. | Map exceptions to fixed error shapes; log details server-side only. | no traceback text in any 4xx/5xx body |

## 5. What the engine could not decide

### Requirements the catalogue did not recognise

These are kept as requirements and assigned to the generic core/surface; refine their components and interfaces.

- **R-1**: Employees must find internal documents quickly and get a short summary without opening them.
- **R-10**: Documents are visible only to members of the tagged team.

### Decisions taken (scored trade-offs)

- D-1 API style: **REST/JSON over HTTP**
- D-2 Primary store: **PostgreSQL**
- D-3 Caller authentication: **OAuth2 / OIDC with the platform's identity provider**
- D-4 Caching: **Read-through cache with TTL and explicit invalidation on write**
- D-5 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-6 Vector index for semantic search: **pgvector in PostgreSQL**
- D-7 Where reports are computed: **Materialised aggregates built by a scheduled job into report tables in the primary database**
- D-8 Redundancy for the availability target: **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
- D-9 Assumed answer: stack (Q-deploy): **containers behind an ingress**
- D-10 Assumed answer: quality (Q-availability): **99.9 %**
- D-11 Assumed answer: data (Q-retention): **indefinite / 1 year**
- D-12 Assumed answer: data (Q-backup): **daily / 24 h / 4 h**
- D-13 Assumed answer: security (Q-authz): **owner-scoped + admin role**
- D-14 Assumed answer: resilience (Q-external): **10 s / 5 retries / queue**
- D-15 Assumed answer: cost (Q-budget): **existing only**
- D-16 Assumed answer: data (Q-migration): **greenfield**
- D-17 Assumed answer: operations (Q-alerting): **error rate + queue growth**

### Notes

- 15 components for a team of 3; consider merging adjacent layers.

## 6. How the text was read

- Patterns recognised: crud_api, notification, auth, rate_limiting, cache, search, file_storage, batch_pipeline, ml_inference, semantic_search, reporting
- Quality attributes (weight): durability 1.0, performance 0.8, isolation 0.7, availability 0.9, operability 0.8, scalability 0.7, simplicity 0.8
- Constraint tokens: containers, idp, multi_instance, nightly_batch, object_storage, postgres, vector_db; languages: python; team: 3

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | **none** | performance | — |
| R-2 | functional | must | file_storage | — | — |
| R-3 | functional | must | search, ml_inference, semantic_search | — | — |
| R-4 | functional | must | search | — | — |
| R-5 | functional | must | cache, ml_inference | — | — |
| R-6 | functional | must | search | — | — |
| R-7 | functional | must | notification, search, batch_pipeline, reporting | — | — |
| R-8 | nonfunctional | must | search | performance | p95 latency at 50,000 <= 800 ms |
| R-9 | nonfunctional | must | file_storage, ml_inference, semantic_search | durability, performance, isolation | latency <= 1 s |
| R-10 | functional | must | **none** | — | — |
| R-11 | constraint | must | file_storage | simplicity | — |
| R-12 | constraint | must | rate_limiting, ml_inference, semantic_search | — | — |
| R-13 | constraint | must | auth | security | — |
| R-14 | functional | must | batch_pipeline | operability, compliance | — |
| R-15 | functional | could | auth | operability | — |
| R-16 | nonfunctional | must | — | durability, availability | ratio 99.9 % |
| R-17 | nonfunctional | should | — | — | time at 4 h 24 h |
| R-18 | nonfunctional | should | — | durability | time at 5 10 s |
| R-19 | nonfunctional | must | — | operability | ratio at 5 minutes, 10 minutes 1 % |
| R-20 | constraint | must | — | scalability | — |
| R-21 | constraint | must | — | — | — |
| R-22 | constraint | must | — | — | — |
