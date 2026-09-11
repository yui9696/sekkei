# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions to answer before committing

Answer by adding bullets to the requirements and running `sekkei design` again; each answer changes only what its last column names.

| # | topic | question | why it matters | assumed meanwhile | changes |
|---|---|---|---|---|---|
| 1 | stack | Which language and runtime version will this be built in? | It fixes the file layout, test commands and every brief's conventions. | Python 3.11+ (engine default). | conventions, work-package files |
| 2 | stack | Is a database available (PostgreSQL/MySQL), or must the system manage its own storage (SQLite/files)? | The primary-store decision and the queue decision are scored on this. | No database stated; options needing one were scored as unavailable. | D: Primary store, Work queue technology |
| 3 | stack | How is it deployed: containers behind an ingress, a single binary/CLI, serverless, on-prem? | Stateless-ness, process topology and configuration loading follow from it. | Single deployable, may run as several instances (stateless conventions applied). | D: Process topology; conventions |
| 4 | people | How many people will build and run it, and for how long? | It weights simplicity in every decision and turns work packages into a calendar. | Small team (simplicity weighted 0.8 when a team size <= 4 is stated; otherwise unweighted). | decisions, schedule estimate |
| 5 | load | What is the sustained and peak request/event rate (per second), and the growth over 12 months? | Without a rate the queue, store and worker decisions cannot be sized and the capacity estimate is empty. | No rate; performance tactics applied without numbers. | capacity estimates, D: Work queue technology |
| 6 | load | How many of the main things exist (users, tenants, endpoints, items) now and in a year? | Partitioning and isolation strategies depend on the count. | Counts unknown; per-item isolation assumed cheap. | D: isolation, capacity |
| 7 | load | How large is a typical and a maximum payload/record (KB)? | Storage growth and body-size limits are computed from it. | 2 KB per record (engine assumption in the capacity estimate). | capacity, input limits |
| 8 | quality | What latency is acceptable for the main operations (a percentile and a number, e.g. p95 under 300 ms)? | It becomes a measurable metric and a load-test acceptance check. | No latency target; no performance acceptance check emitted. | R: non-functional, acceptance checks |
| 9 | quality | What availability is required (e.g. 99.9 % monthly), and what may be lost or delayed during an outage? | Redundancy, health-based restart and queue durability follow from it. | Best effort; single-instance failure delays work but loses nothing that was persisted. | D: Process topology; risks |
| 10 | data | What is the backup/restore expectation (RPO/RTO)? | It decides whether a managed store or an explicit backup job is needed. | Store's own backups; no application-level backup. | D: Primary store; risks |
| 11 | security | How are callers authenticated (API keys, OIDC/OAuth, mTLS), and who issues credentials? | Every management route is gated on it; the auth decision is scored on it. | API keys per caller, hashed at rest. | D: Caller authentication; C: Authentication |
| 12 | resilience | For calls to external systems: timeouts, retry policy, and what happens when they are down for an hour? | The outbound client and the queue are designed to these numbers. | Timeout 10 s, retries per the delivery pattern, work queued during outages. | C: Outbound HTTP client, D: retries |
| 13 | compliance | Is personal data involved, and which regime applies (GDPR/HIPAA/PCI)? Are deletion requests required? | Adds audit, retention and deletion paths. | Personal data present but no regime stated; no deletion path designed. | C: Audit log; batch deletion job |
| 14 | cost | Is there a cost ceiling (infrastructure per month) or a preference for existing infrastructure only? | Options that add infrastructure are scored on cost. | Existing infrastructure preferred (cost weight only if stated). | decisions |

## 2. Capacity estimates

- Missing: no rate stated (events/s, requests/s); throughput, storage growth and backlog cannot be estimated.
- Assumption: Record size: assumed 2048 bytes per record.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **10 person-days**; critical path **8 days**; with a team of 2: **about 8 working days** (2 weeks).
- Wave 1: WP-1, WP-2
- Wave 2: WP-3
- Wave 3: WP-4
- Wave 4: WP-5
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 2 (assumed; no team size stated); packages in one wave run in parallel up to the team size.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-4 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-6 Public HTTP API | spoofing | Requests without a verified caller identity reach domain operations. | Authenticate every route in one middleware; deny by default. | every route returns 401 without credentials |
| C-6 Public HTTP API | tampering | Malformed or oversized bodies reach the core. | Schema-validate and size-limit at the surface; reject before parsing fully. | fuzz the body; oversize returns 413 |
| C-6 Public HTTP API | denial_of_service | A single caller saturates the service. | Per-caller rate limit and request timeouts. | burst from one key returns 429; others unaffected |
| C-6 Public HTTP API | information_disclosure | Stack traces or internal ids leak in error responses. | Map exceptions to fixed error shapes; log details server-side only. | no traceback text in any 4xx/5xx body |

## 5. What the engine could not decide

### Assumptions made

- No implementation language stated; assumed python.
- No database stated; the store decision is scored without a database constraint.
- No non-functional requirements found; performance and availability targets are unset.

### Decisions taken (scored trade-offs)

- D-1 Primary store: **SQLite**

Every requirement was recognised and every active quality has a tactic. Review the decisions above; they are the judgement calls.

## 6. How the text was read

- Patterns recognised: notification, import_export
- Quality attributes (weight): (none)
- Constraint tokens: (none); languages: (none); team: unknown

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | notification | — | — |
| R-2 | functional | must | import_export | — | — |
