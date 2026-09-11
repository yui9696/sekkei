# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions the engine answered for you (confirm or override)

Each answer is a proposed decision in the design and a bullet in the augmented requirements. To override, state the real answer in your requirements and run again.

| # | topic | question answered | engine's answer | basis | if the real answer differs |
|---|---|---|---|---|---|
| 1 | load | Q-payload | 2 KB typical, 256 KB maximum per record. | default — Typical JSON record sizes; the maximum bounds request bodies. | State the sizes; storage growth and body limits change. |
| 2 | quality | Q-availability | 99.9 % monthly; during an outage work is delayed, nothing accepted is lost. | default — Three nines is achievable with two instances and health-based restarts; anything higher needs multi-region. | State the target and what may be lost; topology and queue durability change. |
| 3 | data | Q-retention | Records kept 90 days, audit history 1 year, then deleted by a nightly job. | default — Bounded retention limits storage growth and satisfies most data-minimisation rules. | State the retention; the deletion job and capacity change. |
| 4 | data | Q-backup | Daily backups; RPO 24 h, RTO 4 h. | default — The store's own daily backup is the cheapest credible baseline. | State RPO/RTO; the store decision and a restore drill change. |
| 5 | data | Q-migration | Greenfield; no existing data to migrate. | default — Nothing in the text names an existing system. | Name the existing system; a migration package and risk are added. |
| 6 | security | Q-auth | API keys per customer, hashed at rest, sent as a bearer token. | evidence: customers/visitors mentioned — External callers without a stated identity provider are simplest to serve with per-customer keys. | State the scheme; the authentication decision is rescored. |
| 7 | compliance | Q-compliance | Personal data handled under GDPR-style rules: deletion on request within 30 days; access logged. | evidence: personal data mentioned — Email addresses or names are personal data almost everywhere; deletion on request is the common denominator. | State the regime; audit and deletion paths change. |
| 8 | operations | Q-alerting | Alert the team channel when the error rate exceeds 1 % for 5 minutes or a queue grows for 10 minutes. | default — Two alerts catch most incidents without paging on noise. | State the rules and the on-call; observability conventions change. |
| 9 | cost | Q-budget | Existing infrastructure only; no new managed services. | default — The cheapest assumption; every decision already prefers the option needing no new infrastructure. | State the budget; options adding infrastructure become available. |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| events per day | 86.4 M | rate × 86,400 s | 1,000 (R-8) |
| storage growth per day (events) | 176.95 GB | rate × 86,400 × record size | 1,000 (R-8); 2 KB stated in R-16 |
| storage after 30 days (events) | 5.31 TB | daily growth × 30 | same inputs |
| backlog after a 1 h downstream outage | 3.6 M events | rate × outage seconds | 1,000 (R-8); outage length assumed |
| concurrent handlers to sustain the rate (events) | 200 | Little's law: rate × mean service time | 1,000 (R-8); mean service time assumed 200 ms |
| outbound deliveries per second if each event matches 1 target(s) | 1 k | event rate × fan-out | 1,000 (R-8); fan-out 1 assumed |
| outbound deliveries per second if each event matches 10 target(s) | 10 k | event rate × fan-out | 1,000 (R-8); fan-out 10 assumed |
| in-flight items at the latency target | 5 k | rate × latency target (Little's law upper bound) | 1,000 (R-8) × 5 s (R-8) |
| number of endpoints | 5 k | stated | 5,000 endpoints (R-8) |
| average rate per endpoint (if evenly spread) | 0.2/s | rate ÷ count | 1,000 ÷ 5,000 |

- Assumption: Record size: 2 KB stated in R-16.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **32 person-days**; critical path **12 days**; with a team of 3: **about 12 working days** (3 weeks).
- Wave 1: WP-1, WP-2, WP-3
- Wave 2: WP-4, WP-5, WP-6, WP-7
- Wave 3: WP-8
- Wave 4: WP-10, WP-11, WP-12, WP-13, WP-9
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 3; packages in one wave run in parallel up to the team size.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-2 Work queue | denial_of_service | A poison item is retried forever and blocks its partition. | Attempt cap and dead-letter; per-partition concurrency cap. | an always-failing item ends in the dead-letter after the cap |
| C-2 Work queue | tampering | Items are processed twice after a crash between call and ack. | Idempotent processing with the item id; ack only after the outcome is recorded. | kill the worker mid-call; the item is redelivered exactly once more |
| C-3 Secret store | information_disclosure | Secrets readable from a database dump or a read-only breach. | Encrypt at rest with a key held outside the database; never log values. | database dump contains no plaintext secret; grep logs for secret prefixes finds nothing |
| C-3 Secret store | elevation | A rotated secret stays valid forever. | Bound the grace window; expire old secrets by time. | old secret rejected after the window |
| C-8 Outbound HTTP client | ssrf | A customer-supplied URL points at internal or metadata addresses. | Resolve and block private/link-local ranges; pin the resolved IP; forbid redirects to non-public hosts. | URL to 169.254.169.254 / 10.0.0.1 / localhost is refused before connecting |
| C-8 Outbound HTTP client | denial_of_service | A slow or infinite response body ties up a worker. | Per-request timeout; cap response size; stream and discard bodies. | target that stalls is cut at the timeout; 100 MB body is cut at the cap |
| C-8 Outbound HTTP client | information_disclosure | Secrets or internal headers leak to targets. | Send only the documented headers; never forward inbound headers. | captured request has exactly the documented headers |
| C-9 Signer | tampering | Signatures without a timestamp can be replayed. | Sign timestamp + body; document a tolerance window for verifiers. | replay outside the window fails verification |
| C-10 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-12 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-12 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-17 Admin HTTP API | spoofing | Management operations reachable without authentication. | Authenticate in one middleware for every management route; deny by default. | every management route returns 401 unauthenticated |
| C-17 Admin HTTP API | repudiation | No record of who changed what. | Audit log entries for every management write with the principal. | each write produces an audit entry |
| C-17 Admin HTTP API | elevation | A customer manages another customer's resources. | Ownership check on every resource operation. | cross-customer access returns 404 |
| C-18 Ingest API | spoofing | Any network peer can publish events. | Authenticate producers (service credentials); allowlist event types. | unauthenticated publish returns 401 |
| C-18 Ingest API | tampering | Duplicate or replayed publishes create duplicate work. | Idempotency key per event; reject or de-duplicate replays. | replaying the same key does not enqueue twice |
| C-18 Ingest API | denial_of_service | A producer floods the ingest path. | Per-producer rate limit; back-pressure with 429 and Retry-After. | flood from one producer is throttled |

## 5. What the engine could not decide

### Decisions taken (scored trade-offs)

- D-1 API style: **REST/JSON over HTTP**
- D-2 Primary store: **PostgreSQL**
- D-3 Caller authentication: **API keys per customer, hashed at rest, sent as a bearer token**
- D-4 How producers publish: **HTTP publish endpoint with idempotency keys**
- D-5 Work queue technology: **PostgreSQL table with SELECT ... FOR UPDATE SKIP LOCKED**
- D-6 Where delayed retries wait: **not_before column on the work item; the scheduler promotes due rows**
- D-7 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-8 Outbound request safety: **Resolve and block private/link-local ranges; pin the resolved IP; cap body size and redirects; per-request timeout**
- D-9 Storage of signing secrets: **Encrypted column (AES-GCM) with a key from the environment/KMS**
- D-10 Per-target isolation of outbound work: **Partition the queue by target; each lease takes one partition with a per-partition concurrency cap**
- D-11 Redundancy for the availability target: **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
- D-12 Assumed answer: load (Q-payload): **2 KB / 256 KB**
- D-13 Assumed answer: quality (Q-availability): **99.9 %**
- D-14 Assumed answer: data (Q-retention): **90 days / 1 year**
- D-15 Assumed answer: data (Q-backup): **daily / 24 h / 4 h**
- D-16 Assumed answer: data (Q-migration): **greenfield**
- D-17 Assumed answer: security (Q-auth): **API keys**
- D-18 Assumed answer: compliance (Q-compliance): **GDPR-style deletion + audit**
- D-19 Assumed answer: operations (Q-alerting): **error rate + queue growth**
- D-20 Assumed answer: cost (Q-budget): **existing only**

### Notes

- 18 components for a team of 3; consider merging adjacent layers.

Every requirement was recognised and every active quality has a tactic. Review the decisions above; they are the judgement calls.

## 6. How the text was read

- Patterns recognised: crud_api, admin_api, event_ingest, async_delivery, signing, notification, health_policy, observability, batch_pipeline, auth, audit_log
- Quality attributes (weight): durability 1.0, performance 0.82, isolation 0.82, availability 0.63, security 0.54, operability 0.82, scalability 0.63, simplicity 0.8, compliance 0.54
- Constraint tokens: containers, multi_instance, postgres, redis, single_region; languages: python; team: 3

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | crud_api, admin_api, async_delivery, signing | security | — |
| R-2 | functional | must | crud_api, admin_api, signing | security | — |
| R-3 | functional | must | crud_api, event_ingest | — | — |
| R-4 | functional | must | async_delivery | durability | — |
| R-5 | functional | must | async_delivery, signing | security | — |
| R-6 | functional | must | admin_api, async_delivery | — | — |
| R-7 | functional | must | notification, health_policy | — | — |
| R-8 | nonfunctional | should | event_ingest, async_delivery | performance, operability, scalability | p95 latency at 1,000, 5,000 < 5 s s |
| R-9 | nonfunctional | should | — | durability | records lost across a process crash = 0 records |
| R-10 | nonfunctional | must | — | isolation | p95 latency of healthy targets while one target stalls within the stated latency target |
| R-11 | nonfunctional | should | async_delivery, observability | performance, operability | required metrics exposed = all listed |
| R-12 | constraint | must | — | simplicity | — |
| R-13 | constraint | must | — | scalability | — |
| R-14 | functional | must | batch_pipeline | compliance | — |
| R-15 | functional | must | audit_log | performance, compliance | — |
| R-16 | nonfunctional | should | — | — | size at 2 KB <= 256 kb kb |
| R-17 | nonfunctional | must | — | durability, availability | ratio 99.9 % % |
| R-18 | nonfunctional | should | — | — | time at 4 h 24 h h |
| R-19 | nonfunctional | should | — | operability | ratio at 5 minutes, 10 minutes 1 % % |
| R-20 | constraint | must | — | — | — |
| R-21 | constraint | must | auth | isolation, security | — |
| R-22 | constraint | must | — | — | — |
