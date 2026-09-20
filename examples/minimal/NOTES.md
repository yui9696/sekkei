# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions the engine answered for you (confirm or override)

Each answer is a proposed decision in the design and a bullet in the augmented requirements. To override, state the real answer in your requirements and run again.

| # | topic | question answered | engine's answer | basis | if the real answer differs |
|---|---|---|---|---|---|
| 1 | stack | Q-lang | Python 3.12. | default — No language stated; Python has the shortest path for a small team and the engine's richest layout. | Change the language line; every work package's files and test commands follow. |
| 2 | stack | Q-store | PostgreSQL. | default — A networked service with several actors favour a transactional server database; PostgreSQL is the engine's default when none is stated. | State the available database; the Primary store and Work queue decisions are rescored. |
| 3 | stack | Q-deploy | Stateless containers behind an existing ingress, several instances. | default — The default for a networked service; keeps instances interchangeable. | State the deployment; topology, statelessness conventions and store options change. |
| 4 | people | Q-team | A team of 2 for the first release. | default — No team stated; two people is the smallest team that can review each other's work. Simplicity is weighted accordingly. | State the team size; decision weights and the schedule change. |
| 5 | load | Q-rate | 100 requests/s sustained, 10x at peak (engine default, not derived). | default — No rate stated and none derivable (a count is a size, not a rate); 100 requests/s is a modest default for a first release — every capacity figure below inherits this assumption. | State the measured or expected rate; capacity estimates and the queue decision change. |
| 6 | load | Q-volume | 10,000 primary records and 1,000 users in the first year. | default — No counts stated; the default keeps single-instance options viable and is easy to revise. | State the counts; isolation and capacity estimates change. |
| 7 | load | Q-payload | 2 KB typical, 256 KB maximum per record. | default — Typical JSON record sizes; the maximum bounds request bodies. | State the sizes; storage growth and body limits change. |
| 8 | quality | Q-latency | p95 under 300 ms for reads and under 1 s for writes. | default — Common interactive-API targets; measurable from day one. | State the target; the metric acceptance checks change. |
| 9 | quality | Q-availability | 99.9 % monthly; during an outage work is delayed, nothing accepted is lost. | default — Three nines is achievable with two instances and health-based restarts; anything higher needs multi-region. | State the target and what may be lost; topology and queue durability change. |
| 10 | data | Q-backup | Daily backups; RPO 24 h, RTO 4 h. | default — The store's own daily backup is the cheapest credible baseline. | State RPO/RTO; the store decision and a restore drill change. |
| 11 | security | Q-auth | API keys per customer, hashed at rest, sent as a bearer token. | evidence: customers/visitors mentioned — External callers without a stated identity provider are simplest to serve with per-customer keys. | State the scheme; the authentication decision is rescored. |
| 12 | resilience | Q-external | 10 s timeout, 5 retries with exponential backoff, work queued while the external system is down. | default — Bounded retries with a durable queue keep the system responsive during a one-hour outage. | State the policy; the outbound client and scheduler contracts change. |
| 13 | compliance | Q-compliance | Personal data handled under GDPR-style rules: deletion on request within 30 days; access logged. | evidence: personal data mentioned — Email addresses or names are personal data almost everywhere; deletion on request is the common denominator. | State the regime; audit and deletion paths change. |
| 14 | cost | Q-budget | Existing infrastructure only; no new managed services. | default — The cheapest assumption; every decision already prefers the option needing no new infrastructure. | State the budget; options adding infrastructure become available. |
| 15 | data | Q-retention | Domain records kept indefinitely; logs and audit history 1 year, then deleted by a nightly job. | default — Deleting domain data is never a safe default; bounded retention for logs and history limits growth and satisfies most data-minimisation rules. | State the retention per record class; the deletion job and capacity change. |
| 16 | data | Q-migration | Greenfield; no existing data to migrate. | default — Nothing in the text names an existing system. | Name the existing system; a migration package and risk are added. |
| 17 | operations | Q-alerting | Alert the team channel when the error rate exceeds 1 % for 5 minutes or a queue grows for 10 minutes. | default — Two alerts catch most incidents without paging on noise. | State the rules and the on-call; observability conventions change. |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| concurrent handlers at the stated peak (requests) | 20 | Little's law: peak rate × mean service time | 100 (R-5); mean service time assumed 200 ms |
| number of records | 10 k | stated | 10,000 records (R-6) |
| number of users | 1 k | stated | 1,000 users (R-6) |

- Missing: no rate stated (events/s, requests/s); throughput, storage growth and backlog cannot be estimated.
- Assumption: Record size: 2 KB stated in R-7.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **40 person-days**; critical path **24 days**; with a team of 2: **about 30 working days** (6 weeks).
- Wave 1: WP-1, WP-2
- Wave 2: WP-3, WP-4, WP-5
- Wave 3: WP-6
- Wave 4: WP-7, WP-8
- Wave 5: WP-10, WP-9
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 2; packages in one wave run in parallel up to the team size; a wave lasts max(longest package, person-days ÷ team) and waves run one after another.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-2 Work queue | denial_of_service | A poison item is retried forever and blocks its partition. | Attempt cap and dead-letter; per-partition concurrency cap. | an always-failing item ends in the dead-letter after the cap |
| C-2 Work queue | tampering | Items are processed twice after a crash between call and ack. | Idempotent processing with the item id; ack only after the outcome is recorded. | kill the worker mid-call; the item is redelivered exactly once more |
| C-6 Outbound HTTP client | ssrf | A customer-supplied URL points at internal or metadata addresses. | Resolve and block private/link-local ranges; pin the resolved IP; forbid redirects to non-public hosts. | URL to 169.254.169.254 / 10.0.0.1 / localhost is refused before connecting |
| C-6 Outbound HTTP client | denial_of_service | A slow or infinite response body ties up a worker. | Per-request timeout; cap response size; stream and discard bodies. | target that stalls is cut at the timeout; 100 MB body is cut at the cap |
| C-6 Outbound HTTP client | information_disclosure | Secrets or internal headers leak to targets. | Send only the documented headers; never forward inbound headers. | captured request has exactly the documented headers |
| C-7 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-9 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-9 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-14 Public HTTP API | spoofing | Requests without a verified caller identity reach domain operations. | Authenticate every route in one middleware; deny by default. | every route returns 401 without credentials |
| C-14 Public HTTP API | tampering | Malformed or oversized bodies reach the core. | Schema-validate and size-limit at the surface; reject before parsing fully. | fuzz the body; oversize returns 413 |
| C-14 Public HTTP API | denial_of_service | A single caller saturates the service. | Per-caller rate limit and request timeouts. | burst from one key returns 429; others unaffected |
| C-14 Public HTTP API | information_disclosure | Stack traces or internal ids leak in error responses. | Map exceptions to fixed error shapes; log details server-side only. | no traceback text in any 4xx/5xx body |

## 5. What the engine could not decide

### Decisions taken (scored trade-offs)

- D-1 Work queue technology: **PostgreSQL table with SELECT ... FOR UPDATE SKIP LOCKED**
- D-2 Where delayed retries wait: **not_before column on the work item; the scheduler promotes due rows**
- D-3 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-4 Outbound request safety: **Plain HTTP client with a timeout**
- D-5 Primary store: **PostgreSQL**
- D-6 Caller authentication: **API keys per customer, hashed at rest, sent as a bearer token**
- D-7 Redundancy for the availability target: **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
- D-8 Assumed answer: stack (Q-lang): **Python 3.12**
- D-9 Assumed answer: stack (Q-store): **PostgreSQL**
- D-10 Assumed answer: stack (Q-deploy): **containers behind an ingress**
- D-11 Assumed answer: people (Q-team): **team of 2**
- D-12 Assumed answer: load (Q-rate): **100 requests/s**
- D-13 Assumed answer: load (Q-volume): **10,000 records / 1,000 users**
- D-14 Assumed answer: load (Q-payload): **2 KB / 256 KB**
- D-15 Assumed answer: quality (Q-latency): **300 ms / 1 s**
- D-16 Assumed answer: quality (Q-availability): **99.9 %**
- D-17 Assumed answer: data (Q-backup): **daily / 24 h / 4 h**
- D-18 Assumed answer: security (Q-auth): **API keys**
- D-19 Assumed answer: resilience (Q-external): **10 s / 5 retries / queue**
- D-20 Assumed answer: compliance (Q-compliance): **GDPR-style deletion + audit**
- D-21 Assumed answer: cost (Q-budget): **existing only**
- D-22 Assumed answer: data (Q-retention): **indefinite / 1 year**
- D-23 Assumed answer: data (Q-migration): **greenfield**
- D-24 Assumed answer: operations (Q-alerting): **error rate + queue growth**

### Notes

- 14 components for a team of 2; consider merging adjacent layers.

Every requirement was recognised and every active quality has a tactic. Review the decisions above; they are the judgement calls.

## 5b. Domain model read from the text

Entities with the fields, relations, state machines and invariants the sentences state (nothing inferred beyond the text); each aggregate is a component. Dispute any row by its requirement ids.

No domain entity could be read from the text (no object of a create/submit/book-type verb, no attribute list).

## 6. How the text was read

- Patterns recognised: async_delivery, notification, import_export, auth, audit_log, batch_pipeline
- Quality attributes (weight): durability 1.0, performance 1.0, availability 1.0, operability 0.88, scalability 0.88, simplicity 0.8, compliance 0.76
- Constraint tokens: containers, durable_required, multi_instance, nightly_batch, postgres; languages: python; team: 2

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | notification | — | — |
| R-2 | functional | must | async_delivery, import_export | — | — |
| R-3 | functional | must | audit_log | performance, compliance | — |
| R-4 | functional | must | batch_pipeline | operability, compliance | — |
| R-5 | nonfunctional | must | — | performance | sustained rate at 1,000 100 requests /s |
| R-6 | nonfunctional | should | — | scalability | number of records at 1,000 10000 records |
| R-7 | nonfunctional | must | — | — | size at 2 KB <= 256 kb |
| R-8 | nonfunctional | must | — | performance, operability | p95 latency at 1 s <= 300 ms |
| R-9 | nonfunctional | must | — | durability, availability | ratio 99.9 % |
| R-10 | nonfunctional | should | — | — | time at 4 h 24 h |
| R-11 | nonfunctional | should | — | durability | time at 5 10 s |
| R-12 | nonfunctional | must | — | operability | ratio at 5 minutes, 10 minutes 1 % |
| R-13 | constraint | must | — | — | — |
| R-14 | constraint | must | — | — | — |
| R-15 | constraint | must | — | scalability | — |
| R-16 | constraint | must | — | simplicity | — |
| R-17 | constraint | must | auth | isolation, security | — |
| R-18 | constraint | must | — | — | — |
| R-19 | constraint | must | — | — | — |
