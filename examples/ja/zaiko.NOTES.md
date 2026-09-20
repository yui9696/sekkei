# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions the engine answered for you (confirm or override)

Each answer is a proposed decision in the design and a bullet in the augmented requirements. To override, state the real answer in your requirements and run again.

| # | topic | question answered | engine's answer | basis | if the real answer differs |
|---|---|---|---|---|---|
| 1 | load | Q-rate | 100 requests/s sustained, 10x at peak (engine default, not derived). | default — No rate stated and none derivable (a count is a size, not a rate); 100 requests/s is a modest default for a first release — every capacity figure below inherits this assumption. | State the measured or expected rate; capacity estimates and the queue decision change. |
| 2 | load | Q-payload | 2 KB typical, 256 KB maximum per record. | default — Typical JSON record sizes; the maximum bounds request bodies. | State the sizes; storage growth and body limits change. |
| 3 | data | Q-retention | Domain records kept indefinitely; logs and audit history 1 year, then deleted by a nightly job. | default — Deleting domain data is never a safe default; bounded retention for logs and history limits growth and satisfies most data-minimisation rules. | State the retention per record class; the deletion job and capacity change. |
| 4 | data | Q-backup | Daily backups; RPO 24 h, RTO 4 h. | default — The store's own daily backup is the cheapest credible baseline. | State RPO/RTO; the store decision and a restore drill change. |
| 5 | data | Q-migration | Greenfield; no existing data to migrate. | default — Nothing in the text names an existing system. | Name the existing system; a migration package and risk are added. |
| 6 | security | Q-auth | Single sign-on with the company's identity provider (OIDC). | evidence: staff/employees mentioned — Internal staff systems normally sit behind the company's SSO. | State the scheme; the authentication decision is rescored. |
| 7 | compliance | Q-compliance | Personal data handled under GDPR-style rules: deletion on request within 30 days; access logged. | default — Email addresses or names are personal data almost everywhere; deletion on request is the common denominator. | State the regime; audit and deletion paths change. |
| 8 | operations | Q-alerting | Alert the team channel when the error rate exceeds 1 % for 5 minutes or a queue grows for 10 minutes. | default — Two alerts catch most incidents without paging on noise. | State the rules and the on-call; observability conventions change. |
| 9 | cost | Q-budget | Existing infrastructure only; no new managed services. | default — The cheapest assumption; every decision already prefers the option needing no new infrastructure. | State the budget; options adding infrastructure become available. |
| 10 | security | Q-authz | Callers see only resources they own; an admin role may see everything. | default — Ownership scoping is the minimum that prevents cross-tenant access. | State the roles; core operations and acceptance checks change. |
| 11 | resilience | Q-external | 10 s timeout, 5 retries with exponential backoff, work queued while the external system is down. | default — Bounded retries with a durable queue keep the system responsive during a one-hour outage. | State the policy; the outbound client and scheduler contracts change. |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| concurrent handlers at the stated peak (requests) | 20 | Little's law: peak rate × mean service time | 100 (R-14); mean service time assumed 200 ms |
| number of items | 200 k | stated | 200000 items (R-5) |

- Missing: no rate stated (events/s, requests/s); throughput, storage growth and backlog cannot be estimated.
- Assumption: Record size: 2 KB stated in R-15.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **34 person-days**; critical path **21 days**; with a team of 2: **about 25 working days** (5 weeks).
- Wave 1: WP-1, WP-2
- Wave 2: WP-3, WP-4, WP-5, WP-6
- Wave 3: WP-7
- Wave 4: WP-8
- Wave 5: WP-10, WP-9
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 2; packages in one wave run in parallel up to the team size; a wave lasts max(longest package, person-days ÷ team) and waves run one after another.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-5 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-7 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-7 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-12 Public HTTP API | spoofing | Requests without a verified caller identity reach domain operations. | Authenticate every route in one middleware; deny by default. | every route returns 401 without credentials |
| C-12 Public HTTP API | tampering | Malformed or oversized bodies reach the core. | Schema-validate and size-limit at the surface; reject before parsing fully. | fuzz the body; oversize returns 413 |
| C-12 Public HTTP API | denial_of_service | A single caller saturates the service. | Per-caller rate limit and request timeouts. | burst from one key returns 429; others unaffected |
| C-12 Public HTTP API | information_disclosure | Stack traces or internal ids leak in error responses. | Map exceptions to fixed error shapes; log details server-side only. | no traceback text in any 4xx/5xx body |

## 5. What the engine could not decide

### Assumptions made

- 2 sentence(s) were read but not taken as requirements (listed in the notes §6b); if one of them is a requirement, make it a bullet.

### Decisions taken (scored trade-offs)

- D-1 API style: **REST/JSON over HTTP**
- D-2 Primary store: **PostgreSQL**
- D-3 Caller authentication: **OAuth2 / OIDC with the platform's identity provider**
- D-4 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-5 Concurrency control for conflicting writes: **Row locks inside a short transaction (SELECT ... FOR UPDATE)**
- D-6 Redundancy for the availability target: **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
- D-7 Assumed answer: load (Q-rate): **100 requests/s**
- D-8 Assumed answer: load (Q-payload): **2 KB / 256 KB**
- D-9 Assumed answer: data (Q-retention): **indefinite / 1 year**
- D-10 Assumed answer: data (Q-backup): **daily / 24 h / 4 h**
- D-11 Assumed answer: data (Q-migration): **greenfield**
- D-12 Assumed answer: security (Q-auth): **OIDC**
- D-13 Assumed answer: compliance (Q-compliance): **GDPR-style deletion + audit**
- D-14 Assumed answer: operations (Q-alerting): **error rate + queue growth**
- D-15 Assumed answer: cost (Q-budget): **existing only**
- D-16 Assumed answer: security (Q-authz): **owner-scoped + admin role**
- D-17 Assumed answer: resilience (Q-external): **10 s / 5 retries / queue**

### Notes

- 13 components for a team of 2; consider merging adjacent layers.

Every requirement was recognised and every active quality has a tactic. Review the decisions above; they are the judgement calls.

## 5b. Domain model read from the text

Entities with the fields, relations, states and invariants the reader found in the sentences named in the last column. It reads a fixed set of phrasings (attribute lists, 'has/records/carries A, B and C', possessives, 'set its X', transactional and state verbs, 'then'/'until'/'otherwise' sequences, arrow lists, 'never/cannot' rules); a fact stated another way is not here, and a field or state that is here may still be misread — check each row against its requirement. Each aggregate is a component.

| entity | fields (type) | relations | states | invariants | from |
|---|---|---|---|---|---|
| Item | sku (ref), quantity (int), warehouses (str), bins (str) | — | — | — | R-1 |
| Warehouse | — | — | — | — | R-4 |

## 6. How the text was read

- Patterns recognised: crud_api, notification, observability, search, import_export, batch_pipeline, auth, audit_log
- Quality attributes (weight): consistency 0.78, durability 0.78, performance 0.78, availability 0.78, operability 1.0, simplicity 0.8, compliance 0.62
- Constraint tokens: containers, durable_required, idp, nightly_batch, postgres, rest_api; languages: typescript; team: 2

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | crud_api | — | — |
| R-2 | functional | must | notification | — | — |
| R-3 | functional | must | import_export | — | — |
| R-4 | functional | must | search | — | — |
| R-5 | nonfunctional | must | search | performance | p95 latency at 200000 <= 300 ms |
| R-6 | nonfunctional | must | — | consistency, durability | lost or duplicate updates under concurrent writes to one record = 0 updates |
| R-7 | nonfunctional | must | — | availability | ratio >= 99.9 % |
| R-8 | nonfunctional | must | observability, import_export | operability | required metrics exposed = all listed |
| R-9 | constraint | must | — | simplicity | — |
| R-10 | constraint | must | — | scalability | — |
| R-11 | functional | must | batch_pipeline | operability, compliance | — |
| R-12 | functional | must | audit_log | performance, compliance | — |
| R-13 | functional | must | auth | operability | — |
| R-14 | nonfunctional | must | — | performance | sustained rate at 1,000 100 requests /s |
| R-15 | nonfunctional | must | — | — | size at 2 KB <= 256 kb |
| R-16 | nonfunctional | should | — | — | time at 4 h 24 h |
| R-17 | nonfunctional | must | — | operability | ratio at 5 minutes, 10 minutes 1 % |
| R-18 | nonfunctional | should | — | durability | time at 5 10 s |
| R-19 | constraint | must | — | — | — |
| R-20 | constraint | must | auth | security | — |
| R-21 | constraint | must | — | — | — |

## 6b. What the structure pass found

- **Sentences read but not taken as requirements** (make one a bullet if it is a requirement):
    - “Staff can record stock movements warehouses stock.” — introduction before the first heading
    - “Managers can track out of stock service.” — introduction before the first heading

## 7. Input normalisation (Japanese → canonical English)

The engine reads English. Each Japanese sentence was rewritten with a glossary and a particle-driven reorder; check the right-hand column — it is what was designed, not the left.

| source | rewritten as |
|---|---|
| 倉庫スタッフが在庫の入出庫を記録し、マネージャーが欠品を把握するためのサービス。 | Staff can record stock movements warehouses stock. Managers can track out of stock service. |
| スタッフは在庫品目(SKU、数量、倉庫、棚)を REST API で追加・移動・削除できる。 | Staff can add, move and delete stock items (SKU, quantity, warehouses, bins) REST API. |
| マネージャーは在庫が発注点を下回るとメールで通知される。 | Managers are notified reorder level stock falls below email. |
| マネージャーは在庫一覧を CSV でエクスポートできる。 | Managers can export stock list CSV. |
| 利用者は SKU と倉庫で在庫を検索できる。 | Users can search stock SKU warehouses. |
| 検索は 20万件の品目に対して 300ms以内(p95)に応答すること。 | The system must respond search 200000 items for within 300 ms (p95). |
| 在庫数は同時更新でも失われず、二重に適用されない。 | The system must update stock counts concurrent not lost. The system must not apply double-applied. |
| 月間稼働率 99.9% 以上。 | Monthly availability at least 99.9 %. |
| Prometheus 向けメトリクスと構造化ログを出力する。 | The system must export structured logs Prometheus for metrics. |
| TypeScript(Node 20)。 | TypeScript(Node 20). |
| PostgreSQL を利用可能。 | The system can use PostgreSQL. |
| チームは 2 名。 | Team of 2. |
| コンテナで既存のイングレスの背後で動かす。 | Containers existing ingress behind run. |
| 購買・仕入先管理。 | Purchasing suppliers manage. |

Words the glossary does not know (dropped from the English; add them to the text in English or extend the glossary): 「め」
