# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions to answer before committing

Answer by adding bullets to the requirements and running `sekkei design` again; each answer changes only what its last column names.

| # | topic | question | why it matters | assumed meanwhile | changes |
|---|---|---|---|---|---|
| 1 | load | How large is a typical and a maximum payload/record (KB)? | Storage growth and body-size limits are computed from it. | 2 KB per record (engine assumption in the capacity estimate). | capacity, input limits |
| 2 | quality | What availability is required (e.g. 99.9 % monthly), and what may be lost or delayed during an outage? | Redundancy, health-based restart and queue durability follow from it. | Best effort; single-instance failure delays work but loses nothing that was persisted. | D: Process topology; risks |
| 3 | data | How long must records, logs and history be kept, and when/how are they deleted? | Retention drives storage growth, archival jobs and compliance. | Kept indefinitely; no archival job designed. | capacity, batch jobs, compliance |
| 4 | data | What is the backup/restore expectation (RPO/RTO)? | It decides whether a managed store or an explicit backup job is needed. | Store's own backups; no application-level backup. | D: Primary store; risks |
| 5 | data | Is there existing data or a system being replaced, and must the cut-over be gradual? | A migration path adds a package and a risk. | Greenfield; no migration package. | work packages, risks |
| 6 | security | How are callers authenticated (API keys, OIDC/OAuth, mTLS), and who issues credentials? | Every management route is gated on it; the auth decision is scored on it. | API keys per caller, hashed at rest. | D: Caller authentication; C: Authentication |
| 7 | compliance | Is personal data involved, and which regime applies (GDPR/HIPAA/PCI)? Are deletion requests required? | Adds audit, retention and deletion paths. | Personal data present but no regime stated; no deletion path designed. | C: Audit log; batch deletion job |
| 8 | operations | Who is alerted on what (thresholds, on-call), and where do alerts go? | Metrics exist; alert rules and their owners are a human decision. | Metrics exposed; no alert rules designed. | observability conventions |
| 9 | cost | Is there a cost ceiling (infrastructure per month) or a preference for existing infrastructure only? | Options that add infrastructure are scored on cost. | Existing infrastructure preferred (cost weight only if stated). | decisions |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| events per day | 86.4 M | rate × 86,400 s | 1,000 (R-8) |
| storage growth per day (events) | 176.95 GB | rate × 86,400 × record size | 1,000 (R-8); assumed 2048 bytes per record |
| storage after 30 days (events) | 5.31 TB | daily growth × 30 | same inputs |
| backlog after a 1 h downstream outage | 3.6 M events | rate × outage seconds | 1,000 (R-8); outage length assumed |
| concurrent handlers to sustain the rate (events) | 200 | Little's law: rate × mean service time | 1,000 (R-8); mean service time assumed 200 ms |
| outbound deliveries per second if each event matches 1 target(s) | 1 k | event rate × fan-out | 1,000 (R-8); fan-out 1 assumed |
| outbound deliveries per second if each event matches 10 target(s) | 10 k | event rate × fan-out | 1,000 (R-8); fan-out 10 assumed |
| in-flight items at the latency target | 5 k | rate × latency target (Little's law upper bound) | 1,000 (R-8) × 5 s (R-8) |
| number of endpoints | 5 k | stated | 5,000 endpoints (R-8) |
| average rate per endpoint (if evenly spread) | 0.2/s | rate ÷ count | 1,000 ÷ 5,000 |

- Assumption: Record size: assumed 2048 bytes per record.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **26 person-days**; critical path **17 days**; with a team of 3: **about 17 working days** (4 weeks).
- Wave 1: WP-1, WP-2
- Wave 2: WP-3, WP-4
- Wave 3: WP-5
- Wave 4: WP-6, WP-7
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
| C-7 Outbound HTTP client | ssrf | A customer-supplied URL points at internal or metadata addresses. | Resolve and block private/link-local ranges; pin the resolved IP; forbid redirects to non-public hosts. | URL to 169.254.169.254 / 10.0.0.1 / localhost is refused before connecting |
| C-7 Outbound HTTP client | denial_of_service | A slow or infinite response body ties up a worker. | Per-request timeout; cap response size; stream and discard bodies. | target that stalls is cut at the timeout; 100 MB body is cut at the cap |
| C-7 Outbound HTTP client | information_disclosure | Secrets or internal headers leak to targets. | Send only the documented headers; never forward inbound headers. | captured request has exactly the documented headers |
| C-8 Signer | tampering | Signatures without a timestamp can be replayed. | Sign timestamp + body; document a tolerance window for verifiers. | replay outside the window fails verification |
| C-9 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-11 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-11 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-15 Admin HTTP API | spoofing | Management operations reachable without authentication. | Authenticate in one middleware for every management route; deny by default. | every management route returns 401 unauthenticated |
| C-15 Admin HTTP API | repudiation | No record of who changed what. | Audit log entries for every management write with the principal. | each write produces an audit entry |
| C-15 Admin HTTP API | elevation | A customer manages another customer's resources. | Ownership check on every resource operation. | cross-customer access returns 404 |
| C-16 Ingest API | spoofing | Any network peer can publish events. | Authenticate producers (service credentials); allowlist event types. | unauthenticated publish returns 401 |
| C-16 Ingest API | tampering | Duplicate or replayed publishes create duplicate work. | Idempotency key per event; reject or de-duplicate replays. | replaying the same key does not enqueue twice |
| C-16 Ingest API | denial_of_service | A producer floods the ingest path. | Per-producer rate limit; back-pressure with 429 and Retry-After. | flood from one producer is throttled |

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

### Notes

- 16 components for a team of 3; consider merging adjacent layers.

Every requirement was recognised and every active quality has a tactic. Review the decisions above; they are the judgement calls.

## 6. How the text was read

- Patterns recognised: crud_api, admin_api, event_ingest, async_delivery, signing, notification, health_policy, observability
- Quality attributes (weight): durability 1.0, performance 0.88, isolation 0.94, security 0.52, operability 0.82, scalability 0.7, simplicity 0.8
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
| R-9 | nonfunctional | should | event_ingest | durability | records lost across a process crash = 0 records |
| R-10 | nonfunctional | must | crud_api | isolation | p95 latency of healthy targets while one target stalls within the stated latency target |
| R-11 | nonfunctional | should | async_delivery, observability | performance, operability | required metrics exposed = all listed |
| R-12 | constraint | must | — | simplicity | — |
| R-13 | constraint | must | — | scalability | — |
