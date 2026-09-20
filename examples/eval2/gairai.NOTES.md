# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions the engine answered for you (confirm or override)

Each answer is a proposed decision in the design and a bullet in the augmented requirements. To override, state the real answer in your requirements and run again.

| # | topic | question answered | engine's answer | basis | if the real answer differs |
|---|---|---|---|---|---|
| 1 | load | Q-payload | 2 KB typical, 256 KB maximum per record. | default — Typical JSON record sizes; the maximum bounds request bodies. | State the sizes; storage growth and body limits change. |
| 2 | data | Q-retention | Domain records kept indefinitely; logs and audit history 1 year, then deleted by a nightly job. | default — Deleting domain data is never a safe default; bounded retention for logs and history limits growth and satisfies most data-minimisation rules. | State the retention per record class; the deletion job and capacity change. |
| 3 | data | Q-backup | Daily backups; RPO 24 h, RTO 4 h. | default — The store's own daily backup is the cheapest credible baseline. | State RPO/RTO; the store decision and a restore drill change. |
| 4 | data | Q-migration | An existing system stays the system of record; records are exchanged, nothing is migrated in one shot. | evidence: legacy_integration pattern — The text names an existing system and describes an exchange with it. | State whether data moves; a migration package and risk are added. |
| 5 | security | Q-authz | Callers see only resources they own; an admin role may see everything. | default — Ownership scoping is the minimum that prevents cross-tenant access. | State the roles; core operations and acceptance checks change. |
| 6 | resilience | Q-external | 10 s timeout, 5 retries with exponential backoff, work queued while the external system is down. | default — Bounded retries with a durable queue keep the system responsive during a one-hour outage. | State the policy; the outbound client and scheduler contracts change. |
| 7 | operations | Q-alerting | Alert the team channel when the error rate exceeds 1 % for 5 minutes or a queue grows for 10 minutes. | default — Two alerts catch most incidents without paging on noise. | State the rules and the on-call; observability conventions change. |
| 8 | cost | Q-budget | Existing infrastructure only; no new managed services. | default — The cheapest assumption; every decision already prefers the option needing no new infrastructure. | State the budget; options adding infrastructure become available. |

## 1b. Requirements placed without a catalogue pattern

| requirement | owner(s) | how | detail |
|---|---|---|---|
| R-1 | C-15 Public HTTP API, C-6 Domain core | surface+core | human actor 'doctor': a use case |
| R-2 | C-15 Public HTTP API, C-6 Domain core | surface+core | human actor 'patient': a use case |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| concurrent handlers at the stated peak (requests) | 0.01 | Little's law: peak rate × mean service time | 3000 (R-12); mean service time assumed 200 ms |

- Missing: no rate stated (events/s, requests/s); throughput, storage growth and backlog cannot be estimated.
- Assumption: Record size: 2 KB stated in R-17.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **26 person-days**; critical path **12 days**; with a team of 3: **about 14 working days** (3 weeks).
- Wave 1: WP-1, WP-2
- Wave 2: WP-3, WP-4, WP-5, WP-6
- Wave 3: WP-7
- Wave 4: WP-10, WP-8, WP-9
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 3; packages in one wave run in parallel up to the team size; a wave lasts max(longest package, person-days ÷ team) and waves run one after another.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-7 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-9 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-9 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-13 Legacy system adapter | spoofing | The adapter trusts anything that looks like the legacy system. | Authenticate the legacy endpoint (mTLS or credentials); pin its address. | connection to an impostor host fails |
| C-13 Legacy system adapter | tampering | Malformed legacy records corrupt the domain. | Validate and translate every record; quarantine rejects with a report. | a malformed record is quarantined, not applied |
| C-14 Data protection | repudiation | A deletion cannot be proven later. | Record what was deleted where, with timestamps, in the audit log. | each completed request has a proof entry |
| C-14 Data protection | information_disclosure | An export goes to the wrong person. | Exports are delivered only to the verified subject or an authorised operator; time-limited links. | export link expires and is bound to the requester |
| C-15 Public HTTP API | spoofing | Requests without a verified caller identity reach domain operations. | Authenticate every route in one middleware; deny by default. | every route returns 401 without credentials |
| C-15 Public HTTP API | tampering | Malformed or oversized bodies reach the core. | Schema-validate and size-limit at the surface; reject before parsing fully. | fuzz the body; oversize returns 413 |
| C-15 Public HTTP API | denial_of_service | A single caller saturates the service. | Per-caller rate limit and request timeouts. | burst from one key returns 429; others unaffected |
| C-15 Public HTTP API | information_disclosure | Stack traces or internal ids leak in error responses. | Map exceptions to fixed error shapes; log details server-side only. | no traceback text in any 4xx/5xx body |

## 5. What the engine could not decide

### Requirements the catalogue did not recognise

These are kept as requirements and assigned to the generic core/surface; refine their components and interfaces.

- **R-1**: Patients departments choose doctors. The system can register, change and cancel available slots from appointments.
- **R-2**: Staff can accept and register bookings patients. Staff can view bookings list the same day departments each.

### Assumptions made

- 1 sentence(s) were read but not taken as requirements (listed in the notes §6b); if one of them is a requirement, make it a bullet.

### Decisions taken (scored trade-offs)

- D-1 API style: **REST/JSON over HTTP**
- D-2 Primary store: **PostgreSQL**
- D-3 Caller authentication: **OAuth2 / OIDC with the platform's identity provider**
- D-4 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-5 Protection of personal data: **Encryption at rest by the platform plus strict access control and audit**
- D-6 Integration with the existing system: **Scheduled batch file exchange (CSV/fixed format) through a shared drop**
- D-7 Concurrency control for conflicting writes: **Optimistic concurrency: version column checked on every update; conflict returns 409 and the caller retries**
- D-8 Redundancy for the availability target: **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
- D-9 Assumed answer: load (Q-payload): **2 KB / 256 KB**
- D-10 Assumed answer: data (Q-retention): **indefinite / 1 year**
- D-11 Assumed answer: data (Q-backup): **daily / 24 h / 4 h**
- D-12 Assumed answer: data (Q-migration): **integrate, no migration**
- D-13 Assumed answer: security (Q-authz): **owner-scoped + admin role**
- D-14 Assumed answer: resilience (Q-external): **10 s / 5 retries / queue**
- D-15 Assumed answer: operations (Q-alerting): **error rate + queue growth**
- D-16 Assumed answer: cost (Q-budget): **existing only**

## 6. How the text was read

- Patterns recognised: crud_api, notification, observability, auth, search, batch_pipeline, scheduler_jobs, sms_notification, audit_log, compliance_data, legacy_integration
- Quality attributes (weight): consistency 0.76, durability 0.64, performance 1.0, availability 1.0, security 0.76, operability 1.0, simplicity 0.88, compliance 0.88
- Constraint tokens: containers, durable_required, idp, nightly_batch, postgres, single_region; languages: python; team: 3

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | **none** | — | — |
| R-2 | functional | must | **none** | — | — |
| R-3 | functional | must | notification, scheduler_jobs, sms_notification | — | — |
| R-4 | functional | must | scheduler_jobs | — | — |
| R-5 | functional | must | batch_pipeline | — | — |
| R-6 | functional | must | audit_log | operability, compliance | — |
| R-7 | functional | must | batch_pipeline, legacy_integration | operability | — |
| R-8 | nonfunctional | must | search | performance | p95 latency <= 500 ms |
| R-9 | nonfunctional | must | — | consistency | lost or duplicate updates under concurrent writes to one record = 0 updates |
| R-10 | nonfunctional | must | compliance_data | security, compliance | retention/deletion rules exercised = all |
| R-11 | nonfunctional | must | — | availability | ratio >= 99.5 % |
| R-12 | nonfunctional | must | — | performance | sustained rate at 20 3000 requests /day |
| R-13 | constraint | must | — | scalability, simplicity | — |
| R-14 | constraint | must | auth | security | — |
| R-15 | functional | must | batch_pipeline | operability, compliance | — |
| R-16 | functional | must | auth | operability | — |
| R-17 | nonfunctional | must | — | — | size at 2 KB <= 256 kb |
| R-18 | nonfunctional | should | — | — | time at 4 h 24 h |
| R-19 | nonfunctional | should | — | durability | time at 5 10 s |
| R-20 | nonfunctional | must | — | operability | ratio at 5 minutes, 10 minutes 1 % |
| R-21 | constraint | must | — | — | — |
| R-22 | constraint | must | — | — | — |

## 6b. What the structure pass found

- **Sentences read but not taken as requirements** (make one a bullet if it is a requirement):
    - “Patients during outside mobile app from so that bookings. Accept.” — introduction before the first heading

## 7. Input normalisation (Japanese → canonical English)

The engine reads English. Each Japanese sentence was rewritten with a glossary and a particle-driven reorder; check the right-hand column — it is what was designed, not the left.

| source | rewritten as |
|---|---|
| 中規模病院の外来診療の予約を、患者がスマートフォンから取れるようにし、受付の電話対応を減らす。 | Patients during outside mobile app from so that bookings. Accept. |
| 患者は診療科と医師を選び、空き枠から診察予約を登録・変更・キャンセルできる。 | Patients departments choose doctors. The system can register, change and cancel available slots from appointments. |
| 受付スタッフは患者の代わりに予約を登録でき、当日の予約一覧を診療科ごとに閲覧できる。 | Staff can accept and register bookings patients. Staff can view bookings list the same day departments each. |
| 患者は予約の前日にメールまたは SMS でリマインドを受け取る。 | Patients bookings the day before email or SMS receive reminders. |
| 医師は自分の診察予定と患者の基本情報(氏名、生年月日、保険証番号)を閲覧できる。 | Doctors can view basic information (name, date of birth, insurance number) their own appointments schedule patients. |
| 予約枠は診療科ごとの診療時間と医師のシフトから毎週自動生成する。 | The system must generate slots departments each opening hours doctors shifts from weekly. |
| 予約・変更・キャンセルの操作履歴を、誰がいつ行ったかとともに記録する。 | The system must change and record audit log bookings cancel who when rows. |
| 既存の電子カルテシステム(基幹システム)へ、確定した予約を夜間に連携する。 | The system must integrate confirmed bookings existing electronic health record system (external services) nightly. |
| 空き枠の検索は 500ms 以内(p95)に応答すること。 | The system must respond available slots search within 500 ms (p95). |
| 同じ枠に二重に予約が入ってはならない。 | Same must never be slots double-applied bookings. |
| 患者情報は暗号化して保存し、個人情報保護法に従って本人の求めに応じて削除できること。 | The system must save patient records encrypted. The system can delete appi in accordance with on request. |
| 月間稼働率 99.5% 以上。 | Monthly availability at least 99.5 %. |
| 1 日あたり 3,000 件の予約操作、月末には毎秒 20 件のピーク。 | 3000 requests/day bookings month end 20 requests/s peak. |
| Python 3.12、PostgreSQL を利用可能。 | The system can use Python 3.12 PostgreSQL. |
| チームは 3 名。 | Team of 3. |
| コンテナで単一リージョンに配置する。 | Containers single region. |
| 患者の認証は既存の患者ポータル(OIDC)を使う。 | Patients authenticate existing patient portal (OIDC). |
| 会計・保険請求。 | Accounting invoices. |
| 入院予約。 | Inpatient bookings. |

Words the glossary does not know (dropped from the English; add them to the text in English or extend the glossary): 「ったか」, 「代わり」, 「使う」, 「保険」, 「入っ」, 「取」, 「操作」, 「来診療」, 「減らす」, 「規模病院」, 「配置」, 「電話対応」
