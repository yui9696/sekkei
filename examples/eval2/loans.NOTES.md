# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions the engine answered for you (confirm or override)

Each answer is a proposed decision in the design and a bullet in the augmented requirements. To override, state the real answer in your requirements and run again.

| # | topic | question answered | engine's answer | basis | if the real answer differs |
|---|---|---|---|---|---|
| 1 | load | Q-payload | 2 KB typical, 256 KB maximum per record. | default — Typical JSON record sizes; the maximum bounds request bodies. | State the sizes; storage growth and body limits change. |
| 2 | data | Q-backup | Daily backups; RPO 24 h, RTO 4 h. | default — The store's own daily backup is the cheapest credible baseline. | State RPO/RTO; the store decision and a restore drill change. |
| 3 | data | Q-migration | An existing system stays the system of record; records are exchanged, nothing is migrated in one shot. | evidence: legacy_integration pattern — The text names an existing system and describes an exchange with it. | State whether data moves; a migration package and risk are added. |
| 4 | security | Q-authz | Callers see only resources they own; an admin role may see everything. | default — Ownership scoping is the minimum that prevents cross-tenant access. | State the roles; core operations and acceptance checks change. |
| 5 | operations | Q-alerting | Alert the team channel when the error rate exceeds 1 % for 5 minutes or a queue grows for 10 minutes. | default — Two alerts catch most incidents without paging on noise. | State the rules and the on-call; observability conventions change. |
| 6 | cost | Q-budget | Existing infrastructure only; no new managed services. | default — The cheapest assumption; every decision already prefers the option needing no new infrastructure. | State the budget; options adding infrastructure become available. |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| applications per day | 2 k | rate × 86,400 s | 2,000 (R-8) |
| storage growth per day (applications) | 4.1 MB | rate × 86,400 × record size | 2,000 (R-8); 2 KB stated in R-15 |
| storage after 30 days (applications) | 122.88 MB | daily growth × 30 | same inputs |
| backlog after a 1 h downstream outage | 83.33 applications | rate × outage seconds | 2,000 (R-8); outage length assumed |
| concurrent handlers to sustain the rate (applications) | 0 | Little's law: rate × mean service time | 2,000 (R-8); mean service time assumed 200 ms |
| in-flight items at the latency target | 0.05 | rate × latency target (Little's law upper bound) | 2,000 (R-8) × 2 s (R-8) |

- Assumption: Record size: 2 KB stated in R-15.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **34 person-days**; critical path **13 days**; with a team of 5: **about 16 working days** (4 weeks).
- Wave 1: WP-1, WP-2, WP-3, WP-4
- Wave 2: WP-5, WP-6, WP-7, WP-8
- Wave 3: WP-10, WP-9
- Wave 4: WP-11, WP-12
- Wave 5: WP-13, WP-14
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 5; packages in one wave run in parallel up to the team size; a wave lasts max(longest package, person-days ÷ team) and waves run one after another.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-3 File storage | tampering | Uploaded content is not what its type claims. | Sniff content type; reject executables; size limits. | renamed executable is rejected |
| C-3 File storage | elevation | Path traversal through user-supplied names. | Generate storage keys; never use client names as paths. | name '../x' cannot escape the store |
| C-8 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-10 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-10 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-11 Model server | denial_of_service | Adversarial or oversized inputs exhaust inference capacity. | Input size limits; batching with timeouts. | oversize input rejected before inference |
| C-14 Workflow engine | elevation | A requester approves their own item or skips a step. | Transition rules name the roles allowed per action and exclude the requester; no direct state writes. | self-approval and out-of-order transitions return NotPermitted/InvalidTransition |
| C-14 Workflow engine | repudiation | Approvals cannot be attributed later. | Every transition records the principal, time and comment in an append-only history. | history has one row per transition with the actor |
| C-17 Legacy system adapter | spoofing | The adapter trusts anything that looks like the legacy system. | Authenticate the legacy endpoint (mTLS or credentials); pin its address. | connection to an impostor host fails |
| C-17 Legacy system adapter | tampering | Malformed legacy records corrupt the domain. | Validate and translate every record; quarantine rejects with a report. | a malformed record is quarantined, not applied |
| C-18 Data protection | repudiation | A deletion cannot be proven later. | Record what was deleted where, with timestamps, in the audit log. | each completed request has a proof entry |
| C-18 Data protection | information_disclosure | An export goes to the wrong person. | Exports are delivered only to the verified subject or an authorised operator; time-limited links. | export link expires and is bound to the requester |
| C-19 Public HTTP API | spoofing | Requests without a verified caller identity reach domain operations. | Authenticate every route in one middleware; deny by default. | every route returns 401 without credentials |
| C-19 Public HTTP API | tampering | Malformed or oversized bodies reach the core. | Schema-validate and size-limit at the surface; reject before parsing fully. | fuzz the body; oversize returns 413 |
| C-19 Public HTTP API | denial_of_service | A single caller saturates the service. | Per-caller rate limit and request timeouts. | burst from one key returns 429; others unaffected |
| C-19 Public HTTP API | information_disclosure | Stack traces or internal ids leak in error responses. | Map exceptions to fixed error shapes; log details server-side only. | no traceback text in any 4xx/5xx body |

## 5. What the engine could not decide

### Assumptions made

- 1 sentence(s) were read but not taken as requirements (listed in the notes §6b); if one of them is a requirement, make it a bullet.

### Decisions taken (scored trade-offs)

- D-1 Caller authentication: **OAuth2 / OIDC with the platform's identity provider**
- D-2 Primary store: **PostgreSQL**
- D-3 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-4 How the approval workflow is implemented: **Explicit state machine in code: a transitions table (state, action, role) -> state, history rows in the store**
- D-5 Protection of personal data: **Encryption at rest by the platform plus strict access control and audit**
- D-6 Integration with the existing system: **Scheduled batch file exchange (CSV/fixed format) through a shared drop**
- D-7 Concurrency control for conflicting writes: **Row locks inside a short transaction (SELECT ... FOR UPDATE)**
- D-8 Redundancy for the availability target: **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
- D-9 Assumed answer: load (Q-payload): **2 KB / 256 KB**
- D-10 Assumed answer: data (Q-backup): **daily / 24 h / 4 h**
- D-11 Assumed answer: data (Q-migration): **integrate, no migration**
- D-12 Assumed answer: security (Q-authz): **owner-scoped + admin role**
- D-13 Assumed answer: operations (Q-alerting): **error rate + queue growth**
- D-14 Assumed answer: cost (Q-budget): **existing only**

Every requirement was recognised and every active quality has a tactic. Review the decisions above; they are the judgement calls.

## 6. How the text was read

- Patterns recognised: observability, auth, file_storage, batch_pipeline, ml_inference, audit_log, import_export, kyc, workflow, compliance_data, legacy_integration
- Quality attributes (weight): consistency 0.55, durability 0.55, performance 0.62, availability 0.78, security 0.62, operability 1.0, simplicity 0.7, compliance 0.55
- Constraint tokens: containers, durable_required, idp, nightly_batch, object_storage, postgres, single_region; languages: python; team: 5

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | file_storage | — | — |
| R-2 | functional | must | kyc | — | — |
| R-3 | functional | must | ml_inference, kyc, workflow | — | — |
| R-4 | functional | must | workflow | — | — |
| R-5 | functional | must | batch_pipeline, import_export, workflow, legacy_integration | — | — |
| R-6 | functional | must | audit_log | — | — |
| R-7 | functional | must | compliance_data | compliance | — |
| R-8 | nonfunctional | must | — | performance | p95 latency at 2,000, 1,000 <= 2 s |
| R-9 | nonfunctional | must | — | consistency, durability | occurrences of the forbidden action (record) = 0 occurrences |
| R-10 | nonfunctional | should | — | security | time 7 years |
| R-11 | nonfunctional | must | observability | availability, operability | ratio 99.9 % |
| R-12 | constraint | must | file_storage | scalability, simplicity | — |
| R-13 | constraint | must | auth | security | — |
| R-14 | functional | must | auth | operability | — |
| R-15 | nonfunctional | must | — | — | size at 2 KB <= 256 kb |
| R-16 | nonfunctional | should | — | — | time at 4 h 24 h |
| R-17 | nonfunctional | must | — | operability | ratio at 5 minutes, 10 minutes 1 % |
| R-18 | constraint | must | — | — | — |
| R-19 | constraint | must | — | — | — |

## 6b. What the structure pass found

- **Sentences read but not taken as requirements** (make one a bullet if it is a requirement):
    - “A digital lender takes personal-loan applications online, checks identity and credit, and hands approved loans to the core banking system.” — introduction before the first heading
