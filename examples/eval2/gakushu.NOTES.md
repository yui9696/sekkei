# Architect's notes (engine)

Everything a solution architect hands over besides the design: the questions still open, the
assumptions taken meanwhile, sizing, threats, effort — and what the engine could not do.

## 1. Questions the engine answered for you (confirm or override)

Each answer is a proposed decision in the design and a bullet in the augmented requirements. To override, state the real answer in your requirements and run again.

| # | topic | question answered | engine's answer | basis | if the real answer differs |
|---|---|---|---|---|---|
| 1 | load | Q-rate | 100 requests/s sustained, 10x at peak (engine default, not derived). | default — No rate stated and none derivable (a count is a size, not a rate); 100 requests/s is a modest default for a first release — every capacity figure below inherits this assumption. | State the measured or expected rate; capacity estimates and the queue decision change. |
| 2 | data | Q-backup | Daily backups; RPO 24 h, RTO 4 h. | default — The store's own daily backup is the cheapest credible baseline. | State RPO/RTO; the store decision and a restore drill change. |
| 3 | data | Q-migration | Greenfield; no existing data to migrate. | default — Nothing in the text names an existing system. | Name the existing system; a migration package and risk are added. |
| 4 | security | Q-authz | Callers see only resources they own; an admin role may see everything. | default — Ownership scoping is the minimum that prevents cross-tenant access. | State the roles; core operations and acceptance checks change. |
| 5 | resilience | Q-external | 10 s timeout, 5 retries with exponential backoff, work queued while the external system is down. | default — Bounded retries with a durable queue keep the system responsive during a one-hour outage. | State the policy; the outbound client and scheduler contracts change. |
| 6 | operations | Q-alerting | Alert the team channel when the error rate exceeds 1 % for 5 minutes or a queue grows for 10 minutes. | default — Two alerts catch most incidents without paging on noise. | State the rules and the on-call; observability conventions change. |
| 7 | cost | Q-budget | Existing infrastructure only; no new managed services. | default — The cheapest assumption; every decision already prefers the option needing no new infrastructure. | State the budget; options adding infrastructure become available. |

## 1b. Requirements placed without a catalogue pattern

| requirement | owner(s) | how | detail |
|---|---|---|---|
| R-3 | C-14 Public HTTP API, C-6 Domain core | surface+core | human actor 'employee': a use case |

## 2. Capacity estimates

| estimate | value | formula | inputs |
|---|---|---|---|
| requests per day | 8.64 M | rate × 86,400 s | 100 (R-16) |
| storage growth per day (requests) | 17.69 GB | rate × 86,400 × record size | 100 (R-16); assumed 2048 bytes per record |
| storage after 30 days (requests) | 530.84 GB | daily growth × 30 | same inputs |
| backlog after a 1 h downstream outage | 360 k requests | rate × outage seconds | 100 (R-16); outage length assumed |
| concurrent handlers to sustain the rate (requests) | 20 | Little's law: rate × mean service time | 100 (R-16); mean service time assumed 200 ms |
| in-flight items at the latency target | 1 k | rate × latency target (Little's law upper bound) | 100 (R-16) × 10 min (R-8) |
| concurrent handlers at the stated peak (requests) | 200 | Little's law: peak rate × mean service time | 1,000 (R-16); mean service time assumed 200 ms |
| number of users | 2 k | stated | 2000 users (R-9) |
| average rate per user (if evenly spread) | 0.05/s | rate ÷ count | 100 ÷ 2000 |

- Assumption: Record size: assumed 2048 bytes per record.
- Assumption: Mean service time 200 ms and a 1 h outage are engine assumptions; replace with measurements.

## 3. Effort and schedule

- Total effort: **26 person-days**; critical path **13 days**; with a team of 4: **about 16 working days** (4 weeks).
- Wave 1: WP-1, WP-2, WP-3, WP-4
- Wave 2: WP-5, WP-6, WP-7
- Wave 3: WP-8
- Wave 4: WP-9
- Wave 5: WP-10
- Assumption: Package sizes S/M/L = 2/5/10 person-days (assumption).
- Assumption: Team of 4; packages in one wave run in parallel up to the team size; a wave lasts max(longest package, person-days ÷ team) and waves run one after another.

## 4. Threat model (STRIDE-lite)

Each row is also a risk in the design, so it reaches the brief of the component that must mitigate it.

| component | category | threat | mitigation | proof |
|---|---|---|---|---|
| C-1 Store | tampering | Injection through query construction. | Parameterised queries only; no string-built SQL. | static check for string-formatted SQL finds nothing |
| C-1 Store | information_disclosure | Backups and dumps contain everything. | Encrypt backups; restrict who can take them. | backup file is not readable without the key |
| C-3 File storage | tampering | Uploaded content is not what its type claims. | Sniff content type; reject executables; size limits. | renamed executable is rejected |
| C-3 File storage | elevation | Path traversal through user-supplied names. | Generate storage keys; never use client names as paths. | name '../x' cannot escape the store |
| C-7 Notifier | denial_of_service | Notification storms and template injection. | Rate-limit per recipient; escape template context. | 1,000 failures produce one digest per owner |
| C-9 Authentication | spoofing | Credential stuffing or leaked keys. | Hash keys at rest; allow revocation; rate-limit failures. | revoked key is rejected within seconds; brute force is throttled |
| C-9 Authentication | elevation | A caller acts on another tenant's resources. | Every core operation takes the principal and checks ownership. | cross-tenant request returns 404/403 for every operation |
| C-14 Public HTTP API | spoofing | Requests without a verified caller identity reach domain operations. | Authenticate every route in one middleware; deny by default. | every route returns 401 without credentials |
| C-14 Public HTTP API | tampering | Malformed or oversized bodies reach the core. | Schema-validate and size-limit at the surface; reject before parsing fully. | fuzz the body; oversize returns 413 |
| C-14 Public HTTP API | denial_of_service | A single caller saturates the service. | Per-caller rate limit and request timeouts. | burst from one key returns 429; others unaffected |
| C-14 Public HTTP API | information_disclosure | Stack traces or internal ids leak in error responses. | Map exceptions to fixed error shapes; log details server-side only. | no traceback text in any 4xx/5xx body |

## 5. What the engine could not decide

### Requirements the catalogue did not recognise

These are kept as requirements and assigned to the generic core/surface; refine their components and interfaces.

- **R-3**: Employees can take tests. Employees can view explanations grades immediately.

### Assumptions made

- 2 sentence(s) were read but not taken as requirements (listed in the notes §6b); if one of them is a requirement, make it a bullet.

### Decisions taken (scored trade-offs)

- D-1 API style: **REST/JSON over HTTP**
- D-2 Primary store: **PostgreSQL**
- D-3 Caller authentication: **OAuth2 / OIDC with the platform's identity provider**
- D-4 How media reaches viewers: **Object storage behind a CDN, signed expiring URLs, HTTP range requests; the application never streams bytes**
- D-5 Localisation approach: **Message catalogues in the code base (ICU message format), locale from the user's profile then the request**
- D-6 Concurrency control for conflicting writes: **Optimistic concurrency: version column checked on every update; conflict returns 409 and the caller retries**
- D-7 Redundancy for the availability target: **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
- D-8 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-9 Assumed answer: load (Q-rate): **100 requests/s**
- D-10 Assumed answer: data (Q-backup): **daily / 24 h / 4 h**
- D-11 Assumed answer: data (Q-migration): **greenfield**
- D-12 Assumed answer: security (Q-authz): **owner-scoped + admin role**
- D-13 Assumed answer: resilience (Q-external): **10 s / 5 retries / queue**
- D-14 Assumed answer: operations (Q-alerting): **error rate + queue growth**
- D-15 Assumed answer: cost (Q-budget): **existing only**

## 6. How the text was read

- Patterns recognised: crud_api, notification, observability, auth, search, file_storage, scheduler_jobs, audit_log, import_export, media, i18n
- Quality attributes (weight): consistency 0.83, durability 1.0, performance 0.83, availability 0.83, operability 1.0, scalability 0.57, simplicity 0.8, compliance 0.66
- Constraint tokens: containers, durable_required, idp, object_storage, postgres; languages: typescript; team: 4

| id | kind | priority | patterns | qualities | metric |
|---|---|---|---|---|---|
| R-1 | functional | must | media | — | — |
| R-2 | functional | must | search, media | durability | — |
| R-3 | functional | must | **none** | — | — |
| R-4 | functional | must | import_export | — | — |
| R-5 | functional | must | notification, scheduler_jobs | — | — |
| R-6 | functional | must | audit_log | compliance | — |
| R-7 | functional | must | notification, i18n | — | — |
| R-8 | nonfunctional | must | file_storage, media | performance | latency at 2 GB <= 10 min |
| R-9 | nonfunctional | must | media | consistency, scalability | number of users 2000 users |
| R-10 | nonfunctional | must | — | performance | p95 latency <= 300 ms |
| R-11 | nonfunctional | must | — | consistency, durability | lost or duplicate updates under concurrent writes to one record = 0 updates |
| R-12 | nonfunctional | must | observability, import_export | availability, operability | ratio >= 99.9 % |
| R-13 | constraint | must | file_storage | simplicity | — |
| R-14 | constraint | must | auth | security, scalability | — |
| R-15 | functional | could | auth | operability | — |
| R-16 | nonfunctional | must | — | performance | sustained rate at 1,000 100 requests /s |
| R-17 | nonfunctional | should | — | — | time at 4 h 24 h |
| R-18 | nonfunctional | should | — | durability | time at 5 10 s |
| R-19 | nonfunctional | must | — | operability | ratio at 5 minutes, 10 minutes 1 % |
| R-20 | constraint | must | — | — | — |
| R-21 | constraint | must | — | — | — |

## 6b. What the structure pass found

- **Sentences read but not taken as requirements** (make one a bullet if it is a requirement): “Employees can take video courses.” (introduction before the first heading); “Managers can track tests and progress system. Japanese English.” (introduction before the first heading)

## 7. Input normalisation (Japanese → canonical English)

The engine reads English. Each Japanese sentence was rewritten with a glossary and a particle-driven reorder; check the right-hand column — it is what was designed, not the left.

| source | rewritten as |
|---|---|
| 社員が動画教材で受講し、確認テストを受け、上長が受講状況を把握するためのシステム。 | Employees can take video courses. Managers can track tests and progress system. |
| 日本語と英語で使う。 | Japanese English. |
| 管理者は講座(タイトル、説明、動画ファイル、確認テスト)を作成・公開・非公開にできる。 | Admins can create, publish and unpublish courses (videos, files, tests). |
| 社員は講座を検索して受講し、動画の視聴位置を保存して後で再開できる。 | Employees can search and take courses. Employees can save and resume playback position videos later. |
| 社員は確認テストを受験し、採点結果と解説を即時に閲覧できる。 | Employees can take tests. Employees can view explanations grades immediately. |
| 上長は部下の受講状況と成績を一覧で閲覧し、CSV でエクスポートできる。 | Managers can list and view grades their reports progress. Managers can export CSV. |
| 受講期限の 3 日前に未受講の社員へメールで通知する。 | The system must notify deadline 3 days before not yet taken employees email. |
| 講座の受講完了と成績は監査のため 5 年間保持する。 | Courses completions grades audit for 5 years retention. |
| 画面とメールは社員のロケール(日本語・英語)で表示する。 | The system must view pages email employees locale (Japanese English). |
| 動画ファイルは最大 2GB。 | Videos files up to 2 GB. |
| アップロードは 10 分以内に完了すること。 | The system must complete upload within 10 min. |
| 同時に 2,000 人が動画を視聴しても再生が途切れないこと。 | The system must view videos concurrently 2000 users playback must not stall. |
| 講座一覧は 300ms 以内(p95)に応答すること。 | The system must respond courses list within 300 ms (p95). |
| 成績は失われてはならず、二重に記録されてはならない。 | Grades must never be lost. Grades must not record double-applied. |
| 月間稼働率 99.9% 以上。 | Monthly availability at least 99.9 %. |
| Prometheus 向けメトリクスを出力する。 | The system must export Prometheus for metrics. |
| TypeScript(Node 20)、PostgreSQL、S3 互換のオブジェクトストレージを利用可能。 | The system can use object storage TypeScript (Node 20) PostgreSQL S3. |
| チームは 4 名。 | Team of 4. |
| 社員の認証は社内 SSO(OIDC)。 | Employees authenticate internal SSO (OIDC). |
| コンテナで既存のイングレスの背後に配置する。 | Containers existing ingress behind. |
| 動画のトランスコード(既存サービスに委ねる)。 | Videos transcoding (existing service delegated to). |
| 外部受講者(社外)への提供。 | Outside learners (external). |

Words the glossary does not know (dropped from the English; add them to the text in English or extend the glossary): 「め」, 「互換」, 「使う」, 「受け」, 「提供」, 「部」, 「配置」
