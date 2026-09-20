# newsletter-signup — design

Visitors can subscribe with an email address and confirm through a link sent by email.

_version 0.1.0 · schema sekkei/1_

## Goals

- Work is queued durably and performed by workers with a retry schedule.
- The system notifies people through an external channel.
- Callers are authenticated and authorized.
- Scheduled jobs process stored records in windows.
- Changes are recorded append-only with the actor.
- Records move in and out as files.

## Requirements

| id | kind | priority | statement | metric |
|---|---|---|---|---|
| R-1 | functional | must | Visitors can subscribe with an email address and confirm through a link sent by email. | — |
| R-2 | functional | must | Admins can export the subscriber list as CSV. | — |
| R-3 | functional | must | Personal data is deleted on request within 30 days and access to it is logged (assumed by the engine). | — |
| R-4 | functional | must | Domain records are kept indefinitely; logs and audit history are retained for 1 year, after which a nightly job deletes them (assumed by the engine). | — |
| R-5 | nonfunctional | must | The system sustains 100 requests/s with peaks of 1,000 requests/s (assumed by the engine; default, not derived from the text). | sustained rate at 1,000 100 requests /s |
| R-6 | nonfunctional | should | The system holds 10,000 records and serves 1,000 users in the first year (assumed by the engine). | number of records at 1,000 10000 records |
| R-7 | nonfunctional | must | Records are 2 KB on average and at most 256 KB (assumed by the engine). | size at 2 KB <= 256 kb |
| R-8 | nonfunctional | must | Read operations complete within 300 ms p95 and writes within 1 s p95 (assumed by the engine). | p95 latency at 1 s <= 300 ms |
| R-9 | nonfunctional | must | Availability of 99.9 % monthly; accepted work is delayed but never lost during an outage (assumed by the engine). | ratio 99.9 % |
| R-10 | nonfunctional | should | Backups run daily with a recovery point of 24 h and a recovery time of 4 h (assumed by the engine). | time at 4 h 24 h |
| R-11 | nonfunctional | should | External calls time out after 10 s; failures are retried 5 times with exponential backoff and work waits durably meanwhile (assumed by the engine). | time at 5 10 s |
| R-12 | nonfunctional | must | An alert is raised when the error rate exceeds 1 % for 5 minutes or the queue depth grows for 10 minutes (assumed by the engine). | ratio at 5 minutes, 10 minutes 1 % |
| R-13 | constraint | must | Python 3.12 (assumed by the engine). | — |
| R-14 | constraint | must | PostgreSQL available (assumed by the engine). | — |
| R-15 | constraint | must | Deployed as stateless containers behind an ingress (assumed by the engine). | — |
| R-16 | constraint | must | Team of 2 (assumed by the engine). | — |
| R-17 | constraint | must | Authentication by API keys per customer (assumed by the engine). | — |
| R-18 | constraint | must | Use existing infrastructure only; no new managed services (assumed by the engine). | — |
| R-19 | constraint | must | No existing data or system to migrate from (assumed by the engine). | — |

## Components

```mermaid
graph LR
  C_1[("C-1 Store")]
  C_2[("C-2 Work queue")]
  C_3[["C-3 Email provider"]]
  C_4[("C-4 Audit log")]
  C_5["C-5 Domain core"]
  C_6["C-6 Outbound HTTP client"]
  C_7["C-7 Notifier"]
  C_8["C-8 Observability"]
  C_9["C-9 Authentication"]
  C_10["C-10 Import/export"]
  C_11["C-11 Worker"]
  C_12["C-12 Scheduler"]
  C_13["C-13 Batch job"]
  C_14["C-14 Public HTTP API"]
  C_5 -->|I-1| C_1
  C_5 -->|I-8| C_8
  C_5 -->|I-4| C_4
  C_5 -->|I-7| C_7
  C_6 -->|I-8| C_8
  C_7 -->|I-3| C_3
  C_7 -->|I-8| C_8
  C_9 -->|I-1| C_1
  C_10 -->|I-5| C_5
  C_11 -->|I-2| C_2
  C_11 -->|I-5| C_5
  C_11 -->|I-12| C_12
  C_11 -->|I-8| C_8
  C_11 -->|I-6| C_6
  C_12 -->|I-8| C_8
  C_12 -->|I-2| C_2
  C_13 -->|I-1| C_1
  C_13 -->|I-12| C_12
  C_13 -->|I-8| C_8
  C_13 -->|I-10| C_10
  C_13 -->|I-5| C_5
  C_14 -->|I-5| C_5
  C_14 -->|I-8| C_8
  C_14 -->|I-9| C_9
  C_14 -->|I-10| C_10
```

### C-1 — Store

- **kind**: datastore · **path**: `app/store.py`
- **responsibility**: Owns persistence of the domain entities: durable writes, reads, listing, and the schema/migrations.
- **provides**: I-1
- **requires**: —
- **satisfies**: R-11, R-14

### C-2 — Work queue

- **kind**: datastore · **path**: `app/queue.py`
- **responsibility**: Durable, ordered hand-off of work items between the ingest path and the workers, with visibility timeout and dead-letter.
- **provides**: I-2
- **requires**: —
- **satisfies**: R-2, R-6, R-9, R-11, R-12

### C-3 — Email provider

- **kind**: external
- **responsibility**: External email delivery service.
- **provides**: I-3
- **requires**: —
- **satisfies**: R-1

### C-4 — Audit log

- **kind**: datastore · **path**: `app/audit.py`
- **responsibility**: Append-only record of who did what to which resource, queryable by resource and actor.
- **provides**: I-4
- **requires**: —
- **satisfies**: R-3

### C-5 — Domain core

- **kind**: module · **path**: `app/core.py`
- **responsibility**: Business rules and validation for the domain entities; the only module that changes state through the store.
- **provides**: I-5
- **requires**: I-1, I-8, I-4, I-7
- **satisfies**: R-2, R-13, R-16, R-18, R-19

### C-6 — Outbound HTTP client

- **kind**: module · **path**: `app/dispatcher.py`
- **responsibility**: Performs the outbound HTTP call with timeouts, size limits, redirect and private-address protection, and returns a classified outcome.
- **provides**: I-6
- **requires**: I-8
- **satisfies**: R-2

### C-7 — Notifier

- **kind**: module · **path**: `app/notifier.py`
- **responsibility**: Sends operator/customer notifications through the configured channel with templating and rate limiting.
- **provides**: I-7
- **requires**: I-3, I-8
- **satisfies**: R-1

### C-8 — Observability

- **kind**: module · **path**: `app/observability.py`
- **responsibility**: Metrics registry and exposition, structured logging, health/readiness endpoints.
- **provides**: I-8
- **requires**: —
- **satisfies**: R-9, R-12

### C-9 — Authentication

- **kind**: module · **path**: `app/auth.py`
- **responsibility**: Authenticates callers and resolves them to a principal and scope; enforces authorization for management operations.
- **provides**: I-9
- **requires**: I-1
- **satisfies**: R-17

### C-10 — Import/export

- **kind**: module · **path**: `app/exporter.py`
- **responsibility**: Streams records to and from CSV/JSON with validation and partial-failure reporting.
- **provides**: I-10
- **requires**: I-5
- **satisfies**: R-2

### C-11 — Worker

- **kind**: job · **path**: `app/worker.py`
- **responsibility**: Leases work items, performs the outbound action, records the outcome, and decides retry vs. final failure.
- **provides**: I-11
- **requires**: I-2, I-5, I-12, I-8, I-6
- **satisfies**: R-2, R-5, R-6, R-8, R-15

### C-12 — Scheduler

- **kind**: job · **path**: `app/scheduler.py`
- **responsibility**: Computes when deferred work runs next (backoff schedules, periodic jobs) and promotes due work.
- **provides**: I-12
- **requires**: I-8, I-2
- **satisfies**: R-2, R-4

### C-13 — Batch job

- **kind**: job · **path**: `app/batch.py`
- **responsibility**: Scheduled processing over stored records: extract, transform, aggregate, write results.
- **provides**: I-13
- **requires**: I-1, I-12, I-8, I-10, I-5
- **satisfies**: R-4

### C-14 — Public HTTP API

- **kind**: service · **path**: `app/surface_api.py`
- **responsibility**: Translates HTTP requests into core calls: routing, request validation, error mapping, JSON.
- **provides**: I-14
- **requires**: I-5, I-8, I-9, I-10
- **satisfies**: R-5, R-6, R-7, R-8, R-10, R-15

**Layers** (each layer depends only on earlier ones):

0. C-1, C-2, C-3, C-4, C-8
1. C-12, C-6, C-7, C-9
2. C-5
3. C-10, C-11
4. C-13, C-14

## Interfaces

### I-1 — Store interface

- **kind**: class · **owner**: C-1 · **stability**: stable
- Provided by Store. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `save` | `entity`: Entity, `record`: dict | id | ConflictError on duplicate key | record is durable before return |
| `get` | `entity`: Entity, `id`: str | record \| None | — | — |
| `list` | `entity`: Entity, `filter`: dict, `page`: Page | list[record], next page token | — | — |
| `delete` | `entity`: Entity, `id`: str | bool | — | — |

### I-2 — Work queue interface

- **kind**: class · **owner**: C-2 · **stability**: stable
- Provided by Work queue. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `enqueue` | `item`: WorkItem, `not_before`: datetime \| None | None | — | item is durable before return |
| `lease` | `partition`: str, `limit`: int, `visibility`: timedelta | list[WorkItem] | — | items whose not_before has passed |
| `ack` | `item_id`: str | None | — | — |
| `nack` | `item_id`: str, `retry_at`: datetime \| None | None | — | — |
| | re-queue with a delay, or dead-letter when retries are exhausted | | | |
| `depth` | `partition`: str \| None | int | — | — |

### I-3 — Email provider interface

- **kind**: http · **owner**: C-3 · **stability**: stable
- Provided by Email provider. External; contract is theirs.

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `send` | `to`: str, `subject`: str, `body`: str | provider message id | — | — |

### I-4 — Audit log interface

- **kind**: class · **owner**: C-4 · **stability**: stable
- Provided by Audit log. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `append` | `actor`: str, `action`: str, `resource`: str, `details`: dict | None | — | — |
| `query` | `resource`: str \| None, `actor`: str \| None, `page`: Page | entries | — | — |

### I-5 — Domain core interface

- **kind**: module · **owner**: C-5 · **stability**: draft
- Provided by Domain core. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `export_subscriber` | `subscriber`: Subscriber \| id | Subscriber \| None | ValidationError, NotFound | — |
| | from R-2: Admins can export the subscriber list as CSV. | | | |

### I-6 — Outbound HTTP client interface

- **kind**: module · **owner**: C-6 · **stability**: draft
- Provided by Outbound HTTP client. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `post` | `url`: str, `body`: bytes, `headers`: dict, `timeout`: float | Outcome(status, latency, retry_after) | TimeoutError, ConnectionError, BlockedAddressError | url resolves to a public address |

### I-7 — Notifier interface

- **kind**: module · **owner**: C-7 · **stability**: draft
- Provided by Notifier. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `notify` | `recipient`: str, `template`: str, `context`: dict | message id | NotifyError | — |

### I-8 — Observability interface

- **kind**: module · **owner**: C-8 · **stability**: draft
- Provided by Observability. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `counter` | `name`: str, `labels`: dict | Counter | — | — |
| `histogram` | `name`: str, `labels`: dict | Histogram | — | — |
| `gauge` | `name`: str, `labels`: dict | Gauge | — | — |
| `GET /metrics` | — | Prometheus text exposition | — | — |
| `GET /healthz` | — | 200 when dependencies reachable | — | — |
| `log` | `event`: str, `fields`: dict | None | — | — |
| | one JSON line per event | | | |

### I-9 — Authentication interface

- **kind**: module · **owner**: C-9 · **stability**: draft
- Provided by Authentication. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `authenticate` | `credentials`: str | Principal | AuthError | — |
| `authorize` | `principal`: Principal, `action`: str, `resource`: str | None | Forbidden | — |

### I-10 — Import/export interface

- **kind**: module · **owner**: C-10 · **stability**: draft
- Provided by Import/export. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `export` | `entity`: Entity, `filter`: dict, `format`: csv\|json | byte stream | — | — |
| `import_` | `entity`: Entity, `stream`: bytes, `format`: csv\|json | ImportReport with per-row errors | — | — |

### I-11 — Worker interface

- **kind**: module · **owner**: C-11 · **stability**: draft
- Provided by Worker. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `run_once` | `partition`: str | int processed | — | — |
| | one lease/process/ack cycle; the loop and concurrency live in the process entry point | | | |
| `process` | `item`: WorkItem | Outcome | DeliveryError | outcome recorded through core before ack |

### I-12 — Scheduler interface

- **kind**: module · **owner**: C-12 · **stability**: draft
- Provided by Scheduler. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `next_attempt` | `attempt`: int, `retry_after`: timedelta \| None | datetime \| None | — | — |
| | None when attempts are exhausted | | | |
| `promote_due` | `now`: datetime | int moved | — | — |

### I-13 — Batch job interface

- **kind**: module · **owner**: C-13 · **stability**: draft
- Provided by Batch job. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `run` | `window`: DateRange | JobReport | JobError | stated values: 1 year (R-4) |

### I-14 — Public HTTP API interface

- **kind**: http · **owner**: C-14 · **stability**: draft
- Provided by Public HTTP API. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `GET /subscribers` | `filter`: query, `page`: cursor | 200 [subscriber], next cursor | 401 unauthenticated | — |
| | from R-2: Admins can export the subscriber list as CSV. | | | |

## Entities

### E-1 — WorkItem (owner C-2)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `partition` | str | indexed; the isolation key |
| `payload_ref` | uuid | references the event |
| `attempt` | int | >= 0 |
| `not_before` | timestamp | indexed |
| `leased_until` | timestamp \| null |  |

### E-2 — DeliveryAttempt (owner C-1)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `work_item_id` | uuid | indexed |
| `attempt` | int |  |
| `status` | enum(success, retry, failed) |  |
| `response_code` | int \| null |  |
| `started_at` | timestamp |  |
| `finished_at` | timestamp |  |
| `error` | str \| null |  |

### E-3 — Principal (owner C-1)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `kind` | enum(customer, operator, service) |  |
| `scopes` | list[str] |  |

### E-4 — JobRun (owner C-1)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `job` | str |  |
| `window_start` | timestamp |  |
| `window_end` | timestamp |  |
| `status` | enum |  |
| `report` | json |  |

### E-5 — AuditEntry (owner C-4)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `actor` | str |  |
| `action` | str |  |
| `resource` | str | indexed |
| `at` | timestamp |  |

## Flows

### F-1 — Deliver a work item

_Trigger:_ worker leases due items

1. C-11 → C-2 via I-2: lease items of one partition
2. C-11 → C-5 via I-5: load target, secrets and payload
3. C-11 → C-2 via I-2: ack on success, nack with retry_at on retryable failure, dead-letter when exhausted

```mermaid
sequenceDiagram
  participant C_11 as C-11 Worker
  participant C_2 as C-2 Work queue
  participant C_5 as C-5 Domain core
  Note over C_11: worker leases due items
  C_11->>C_2: I-2 lease items of one partition
  C_11->>C_5: I-5 load target, secrets and payload
  C_11->>C_2: I-2 ack on success, nack with retry_at on retryable failure, dead-letter when exhausted
```

### F-2 — Retry after failure

_Trigger:_ scheduler tick

1. C-12 → C-2 via I-2: promote items whose not_before has passed

```mermaid
sequenceDiagram
  participant C_12 as C-12 Scheduler
  participant C_2 as C-2 Work queue
  Note over C_12: scheduler tick
  C_12->>C_2: I-2 promote items whose not_before has passed
```

### F-3 — Run the batch job

_Trigger:_ schedule fires

1. C-13 → C-1 via I-1: read the window of records
2. C-13 → C-1 via I-1: write results and the job report

```mermaid
sequenceDiagram
  participant C_13 as C-13 Batch job
  participant C_1 as C-1 Store
  Note over C_13: schedule fires
  C_13->>C_1: I-1 read the window of records
  C_13->>C_1: I-1 write results and the job report
```

## Decisions

### D-1 — Work queue technology (accepted)

**Context.** Work items must survive a crash and be leased by several workers.

- ✔ **PostgreSQL table with SELECT ... FOR UPDATE SKIP LOCKED**
  - + transactional with the domain data (persist + enqueue atomically)
  - + no new infrastructure
  - + easy to inspect
  - − throughput bounded by the database (fine to ~10k items/s)
  - − needs a vacuum-friendly schema
- ✘ **Redis Streams with consumer groups**
  - + high throughput
  - + built-in consumer groups and pending lists
  - − durability depends on AOF/fsync configuration
  - − separate from the transactional store: needs an outbox
- ✘ **Managed broker (SQS/RabbitMQ/Kafka)**
  - + scales independently
  - + delayed delivery built in (SQS)
  - − new infrastructure and cost
  - − at-least-once semantics still need an outbox
- ✘ **In-memory queue**
  - + simplest possible
  - − work is lost on crash
  - − single process only

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), performance (weight 1.0). PostgreSQL table with SELECT ... FOR UPDATE SKIP: 2.15; Redis Streams with consumer groups: unavailable (needs redis, not in the constraints); Managed broker: unavailable (needs broker, not in the constraints); In-memory queue: unavailable (ruled out by durable_required)

_Affects:_ C-2, C-11

### D-2 — Where delayed retries wait (accepted)

**Context.** Failed deliveries must run again at a computed future time.

- ✔ **not_before column on the work item; the scheduler promotes due rows**
  - + one durable store for queued and delayed items
  - + trivial to inspect and to redeliver manually
  - − a periodic scan (index on not_before)
- ✘ **Redis sorted set keyed by due time**
  - + cheap due-time queries
  - − a second store to keep consistent
- ✘ **In-process timers**
  - + no store
  - − lost on restart

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), performance (weight 1.0). not_before column on the work item: 2.01; Redis sorted set keyed by due time: unavailable (needs redis, not in the constraints); In-process timers: unavailable (ruled out by durable_required)

_Affects:_ C-12, C-2

### D-3 — Process topology (accepted)

**Context.** The same code base serves requests and performs background work.

- ✔ **One image, role by flag: `api` and `worker` processes scale independently**
  - + stateless containers
  - + independent scaling of ingress and outbound work
  - + one build
  - − two deployables to operate
- ✘ **Single process with background threads**
  - + one deployable
  - − request latency competes with outbound work
  - − cannot scale roles separately
- ✘ **Separate services per concern (ingest, admin, delivery)**
  - + clear ownership
  - − three deployables for a team of three
  - − shared schema anyway

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), performance (weight 1.0). One image, role by flag: `api` and `worker` proc: 2.00; Separate services per concern: 1.59; Single process with background threads: 1.39

**Consequences.** Not choosing 'Separate services per concern' gives up: clear ownership. Not choosing 'Single process with background threads' gives up: one deployable.

_Affects:_ C-14, C-11, C-12

### D-4 — Outbound request safety (accepted)

**Context.** The system makes HTTP requests to customer-supplied URLs.

- ✘ **Resolve and block private/link-local ranges; pin the resolved IP; cap body size and redirects; per-request timeout**
  - + closes SSRF and slow-loris classes
  - − a resolver step per request
- ✔ **Plain HTTP client with a timeout**
  - + simplest
  - − SSRF into internal networks
  - − unbounded response bodies

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), performance (weight 1.0). Plain HTTP client with a timeout: 1.25; Resolve and block private/link-local ranges: 1.13

**Consequences.** Not choosing 'Resolve and block private/link-local ranges; pin' gives up: closes SSRF and slow-loris classes.

_Affects:_ C-6

### D-5 — Primary store (accepted)

**Context.** Domain records need durable, queryable storage.

- ✔ **PostgreSQL**
  - + transactions
  - + indexes and JSON
  - + widely available
  - − operational dependency
- ✘ **MySQL / MariaDB (the stated database)**
  - + transactions
  - + already operated by the team
  - − weaker JSON and DDL ergonomics than PostgreSQL
- ✘ **Redis for the hot state (as stated) with a relational store for durable records**
  - + the stated home of the hot data
  - + sub-millisecond reads
  - − two stores to keep consistent
  - − Redis durability depends on AOF/fsync
- ✘ **Managed document store (DynamoDB/MongoDB, as stated)**
  - + scales without operations
  - + flexible records
  - − no cross-record transactions by default
  - − query patterns must be designed up front
- ✘ **SQLite**
  - + zero operations
  - + single file
  - − one writer at a time
  - − no network access
- ✘ **Files (JSON/CSV on disk)**
  - + no dependencies
  - + human readable
  - − no transactions or concurrency
- ✘ **In-memory**
  - + fastest
  - + trivial
  - − lost on restart

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), performance (weight 1.0). PostgreSQL: 2.56; SQLite: 1.69; Files: 1.11; MySQL / MariaDB: unavailable (needs mysql, not in the constraints); Redis for the hot state: unavailable (needs redis_primary, not in the constraints); Managed document store: unavailable (needs document_db, not in the constraints); In-memory: unavailable (ruled out by durable_required)

**Consequences.** Not choosing 'SQLite' gives up: zero operations, single file. Not choosing 'Files' gives up: no dependencies, human readable.

_Affects:_ C-1

### D-6 — Caller authentication (accepted)

**Context.** Management operations must be attributable to a customer or operator.

- ✔ **API keys per customer, hashed at rest, sent as a bearer token**
  - + simple
  - + scriptable
  - − no delegation or expiry unless added
- ✘ **OAuth2 / OIDC with the platform's identity provider**
  - + single sign-on
  - + expiry and scopes
  - − integration effort
- ✘ **Mutual TLS**
  - + strong
  - + no secrets in headers
  - − certificate lifecycle for every customer
- ✘ **Session tokens issued by the platform's own account service to game/mobile clients (device-bound, short-lived, refreshable)**
  - + fits clients without a browser
  - + revocable per device
  - − a token service to run
- ✘ **Email one-time code / magic link (no account needed)**
  - + no password, no sign-up
  - + works for occasional customers
  - − depends on email delivery
  - − weak against mailbox compromise

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), performance (weight 1.0). API keys per customer, hashed at rest, sent as a: 1.25; Mutual TLS: 0.87; OAuth2 / OIDC with the platform's identity provi: unavailable (needs idp, not in the constraints); Session tokens issued by the platform's own acco: unavailable (needs game_client, not in the constraints); Email one-time code / magic link: unavailable (needs email_auth, not in the constraints)

**Consequences.** Not choosing 'Mutual TLS' gives up: strong, no secrets in headers.

_Affects:_ C-9

### D-7 — Redundancy for the availability target (accepted)

**Context.** The availability target must be met through instance failures and deploys.

- ✔ **Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys**
  - + survives one instance failure
  - + zero-downtime deploys
  - − needs stateless instances and a shared store
- ✘ **Single instance with health-based restart**
  - + simplest
  - + cheapest
  - − restart time is downtime
  - − deploys are downtime
- ✘ **Active-active across two regions**
  - + survives a regional outage
  - − data replication and conflict handling
  - − cost

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), performance (weight 1.0). Two or more interchangeable instances per role b: 1.72; Active-active across two regions: 1.47; Single instance with health-based restart: 1.25

**Consequences.** Not choosing 'Active-active across two regions' gives up: survives a regional outage. Not choosing 'Single instance with health-based restart' gives up: simplest, cheapest.

_Affects:_ C-14, C-11

### D-8 — Assumed answer: stack (Q-lang) (proposed)

**Context.** The requirements do not say. Question: Q-lang. No evidence in the text; engine default.

- ✔ **Python 3.12**
- ✘ **TypeScript on Node 20**
- ✘ **Go 1.22**

**Rationale.** No language stated; Python has the shortest path for a small team and the engine's richest layout.

**Consequences.** If the real answer differs: Change the language line; every work package's files and test commands follow.

### D-9 — Assumed answer: stack (Q-store) (proposed)

**Context.** The requirements do not say. Question: Q-store. No evidence in the text; engine default.

- ✔ **PostgreSQL**
- ✘ **SQLite**
- ✘ **MySQL**

**Rationale.** A networked service with several actors favour a transactional server database; PostgreSQL is the engine's default when none is stated.

**Consequences.** If the real answer differs: State the available database; the Primary store and Work queue decisions are rescored.

_Affects:_ C-1, C-2

### D-10 — Assumed answer: stack (Q-deploy) (proposed)

**Context.** The requirements do not say. Question: Q-deploy. No evidence in the text; engine default.

- ✔ **containers behind an ingress**
- ✘ **single VM**
- ✘ **serverless functions**

**Rationale.** The default for a networked service; keeps instances interchangeable.

**Consequences.** If the real answer differs: State the deployment; topology, statelessness conventions and store options change.

_Affects:_ C-14, C-11

### D-11 — Assumed answer: people (Q-team) (proposed)

**Context.** The requirements do not say. Question: Q-team. No evidence in the text; engine default.

- ✔ **team of 2**
- ✘ **team of 1**
- ✘ **team of 5**

**Rationale.** No team stated; two people is the smallest team that can review each other's work. Simplicity is weighted accordingly.

**Consequences.** If the real answer differs: State the team size; decision weights and the schedule change.

### D-12 — Assumed answer: load (Q-rate) (proposed)

**Context.** The requirements do not say. Question: Q-rate. No evidence in the text; engine default.

- ✔ **100 requests/s**
- ✘ **10 requests/s**
- ✘ **1,000 requests/s**

**Rationale.** No rate stated and none derivable (a count is a size, not a rate); 100 requests/s is a modest default for a first release — every capacity figure below inherits this assumption.

**Consequences.** If the real answer differs: State the measured or expected rate; capacity estimates and the queue decision change.

_Affects:_ C-2, C-14

### D-13 — Assumed answer: load (Q-volume) (proposed)

**Context.** The requirements do not say. Question: Q-volume. No evidence in the text; engine default.

- ✔ **10,000 records / 1,000 users**
- ✘ **100,000 / 10,000**
- ✘ **1,000 / 100**

**Rationale.** No counts stated; the default keeps single-instance options viable and is easy to revise.

**Consequences.** If the real answer differs: State the counts; isolation and capacity estimates change.

_Affects:_ C-1

### D-14 — Assumed answer: load (Q-payload) (proposed)

**Context.** The requirements do not say. Question: Q-payload. No evidence in the text; engine default.

- ✔ **2 KB / 256 KB**
- ✘ **16 KB / 1 MB**
- ✘ **256 bytes / 4 KB**

**Rationale.** Typical JSON record sizes; the maximum bounds request bodies.

**Consequences.** If the real answer differs: State the sizes; storage growth and body limits change.

_Affects:_ C-14

### D-15 — Assumed answer: quality (Q-latency) (proposed)

**Context.** The requirements do not say. Question: Q-latency. No evidence in the text; engine default.

- ✔ **300 ms / 1 s**
- ✘ **100 ms / 500 ms**
- ✘ **1 s / 5 s**

**Rationale.** Common interactive-API targets; measurable from day one.

**Consequences.** If the real answer differs: State the target; the metric acceptance checks change.

_Affects:_ C-14

### D-16 — Assumed answer: quality (Q-availability) (proposed)

**Context.** The requirements do not say. Question: Q-availability. No evidence in the text; engine default.

- ✔ **99.9 %**
- ✘ **99.5 %**
- ✘ **99.99 %**

**Rationale.** Three nines is achievable with two instances and health-based restarts; anything higher needs multi-region.

**Consequences.** If the real answer differs: State the target and what may be lost; topology and queue durability change.

_Affects:_ C-2, C-8

### D-17 — Assumed answer: data (Q-backup) (proposed)

**Context.** The requirements do not say. Question: Q-backup. No evidence in the text; engine default.

- ✔ **daily / 24 h / 4 h**
- ✘ **hourly / 1 h / 1 h**
- ✘ **none**

**Rationale.** The store's own daily backup is the cheapest credible baseline.

**Consequences.** If the real answer differs: State RPO/RTO; the store decision and a restore drill change.

_Affects:_ C-1

### D-18 — Assumed answer: security (Q-auth) (proposed)

**Context.** The requirements do not say. Question: Q-auth. Evidence: customers/visitors mentioned.

- ✔ **API keys**
- ✘ **OIDC**
- ✘ **mTLS**

**Rationale.** External callers without a stated identity provider are simplest to serve with per-customer keys.

**Consequences.** If the real answer differs: State the scheme; the authentication decision is rescored.

_Affects:_ C-9

### D-19 — Assumed answer: resilience (Q-external) (proposed)

**Context.** The requirements do not say. Question: Q-external. No evidence in the text; engine default.

- ✔ **10 s / 5 retries / queue**
- ✘ **fail fast, no retry**
- ✘ **30 s / unlimited retries**

**Rationale.** Bounded retries with a durable queue keep the system responsive during a one-hour outage.

**Consequences.** If the real answer differs: State the policy; the outbound client and scheduler contracts change.

_Affects:_ C-6, C-12, C-2

### D-20 — Assumed answer: compliance (Q-compliance) (proposed)

**Context.** The requirements do not say. Question: Q-compliance. Evidence: personal data mentioned.

- ✔ **GDPR-style deletion + audit**
- ✘ **no regime**
- ✘ **HIPAA/PCI controls**

**Rationale.** Email addresses or names are personal data almost everywhere; deletion on request is the common denominator.

**Consequences.** If the real answer differs: State the regime; audit and deletion paths change.

_Affects:_ C-4, C-1

### D-21 — Assumed answer: cost (Q-budget) (proposed)

**Context.** The requirements do not say. Question: Q-budget. No evidence in the text; engine default.

- ✔ **existing only**
- ✘ **managed services allowed**
- ✘ **strict monthly cap**

**Rationale.** The cheapest assumption; every decision already prefers the option needing no new infrastructure.

**Consequences.** If the real answer differs: State the budget; options adding infrastructure become available.

### D-22 — Assumed answer: data (Q-retention) (proposed)

**Context.** The requirements do not say. Question: Q-retention. No evidence in the text; engine default.

- ✔ **indefinite / 1 year**
- ✘ **90 days / 1 year**
- ✘ **30 days / 90 days**

**Rationale.** Deleting domain data is never a safe default; bounded retention for logs and history limits growth and satisfies most data-minimisation rules.

**Consequences.** If the real answer differs: State the retention per record class; the deletion job and capacity change.

_Affects:_ C-13, C-1

### D-23 — Assumed answer: data (Q-migration) (proposed)

**Context.** The requirements do not say. Question: Q-migration. No evidence in the text; engine default.

- ✔ **greenfield**
- ✘ **one-shot import**
- ✘ **gradual cut-over**

**Rationale.** Nothing in the text names an existing system.

**Consequences.** If the real answer differs: Name the existing system; a migration package and risk are added.

### D-24 — Assumed answer: operations (Q-alerting) (proposed)

**Context.** The requirements do not say. Question: Q-alerting. No evidence in the text; engine default.

- ✔ **error rate + queue growth**
- ✘ **none**
- ✘ **per-endpoint SLO alerts**

**Rationale.** Two alerts catch most incidents without paging on noise.

**Consequences.** If the real answer differs: State the rules and the on-call; observability conventions change.

_Affects:_ C-8

## Risks

| id | risk | likelihood | impact | mitigation |
|---|---|---|---|---|
| K-1 | At-least-once delivery means a target can receive the same event twice (crash between call and ack). | high | medium | Send a stable event id and attempt number in headers; document idempotent consumption; never retry on 2xx. |
| K-2 | Many targets fail at once (regional outage) and their retries align, creating a burst. | medium | medium | Add jitter to the backoff schedule and cap concurrent deliveries per partition and globally. |
| K-3 | Customer-supplied URLs can point at internal addresses or metadata services. | high | high | Resolve before connecting, block private ranges, pin the IP, forbid redirects to non-public hosts. |
| K-4 | Retried and dead-lettered items accumulate and slow the lease query. | medium | medium | Partial index on (partition, not_before) for live items; archive terminal items on a schedule. |
| K-5 | Timestamp-based signatures and not_before scheduling depend on wall clocks. | low | medium | Use the database clock for scheduling; tolerate a bounded skew window when verifying timestamps. |
| K-6 | A widespread failure disables many targets and emails every owner at once. | low | medium | Rate-limit notifications per owner and batch them. |
| K-7 | A management operation reachable without authentication. | low | high | Authenticate in one middleware for every management route; test every route unauthenticated. |
| K-8 | Entities evolve; migrations run against live data. | medium | medium | Versioned migrations applied before deploy; additive changes first, removals one release later. |
| K-9 | Payloads or uploads without size limits exhaust memory or disk. | medium | medium | Enforce size limits at the surface; reject early with a clear error. |
| K-10 | [tampering] Store: Injection through query construction. | medium | medium | Parameterised queries only; no string-built SQL. Check: static check for string-formatted SQL finds nothing |
| K-11 | [information_disclosure] Store: Backups and dumps contain everything. | medium | high | Encrypt backups; restrict who can take them. Check: backup file is not readable without the key |
| K-12 | [denial_of_service] Work queue: A poison item is retried forever and blocks its partition. | medium | medium | Attempt cap and dead-letter; per-partition concurrency cap. Check: an always-failing item ends in the dead-letter after the cap |
| K-13 | [tampering] Work queue: Items are processed twice after a crash between call and ack. | medium | medium | Idempotent processing with the item id; ack only after the outcome is recorded. Check: kill the worker mid-call; the item is redelivered exactly once more |
| K-14 | [ssrf] Outbound HTTP client: A customer-supplied URL points at internal or metadata addresses. | medium | high | Resolve and block private/link-local ranges; pin the resolved IP; forbid redirects to non-public hosts. Check: URL to 169.254.169.254 / 10.0.0.1 / localhost is refused before connecting |
| K-15 | [denial_of_service] Outbound HTTP client: A slow or infinite response body ties up a worker. | medium | medium | Per-request timeout; cap response size; stream and discard bodies. Check: target that stalls is cut at the timeout; 100 MB body is cut at the cap |
| K-16 | [information_disclosure] Outbound HTTP client: Secrets or internal headers leak to targets. | medium | high | Send only the documented headers; never forward inbound headers. Check: captured request has exactly the documented headers |
| K-17 | [denial_of_service] Notifier: Notification storms and template injection. | medium | medium | Rate-limit per recipient; escape template context. Check: 1,000 failures produce one digest per owner |
| K-18 | [spoofing] Authentication: Credential stuffing or leaked keys. | medium | medium | Hash keys at rest; allow revocation; rate-limit failures. Check: revoked key is rejected within seconds; brute force is throttled |
| K-19 | [elevation] Authentication: A caller acts on another tenant's resources. | medium | high | Every core operation takes the principal and checks ownership. Check: cross-tenant request returns 404/403 for every operation |
| K-20 | [spoofing] Public HTTP API: Requests without a verified caller identity reach domain operations. | medium | medium | Authenticate every route in one middleware; deny by default. Check: every route returns 401 without credentials |
| K-21 | [tampering] Public HTTP API: Malformed or oversized bodies reach the core. | medium | medium | Schema-validate and size-limit at the surface; reject before parsing fully. Check: fuzz the body; oversize returns 413 |
| K-22 | [denial_of_service] Public HTTP API: A single caller saturates the service. | medium | medium | Per-caller rate limit and request timeouts. Check: burst from one key returns 429; others unaffected |
| K-23 | [information_disclosure] Public HTTP API: Stack traces or internal ids leak in error responses. | medium | high | Map exceptions to fixed error shapes; log details server-side only. Check: no traceback text in any 4xx/5xx body |

## Work packages

```mermaid
graph LR
  WP_1["WP-1 Audit log (S)"]
  WP_2["WP-2 Store + Work queue + Observability (M)"]
  WP_3["WP-3 Outbound HTTP client (S)"]
  WP_4["WP-4 Authentication + Scheduler (M)"]
  WP_5["WP-5 Notifier (S)"]
  WP_6["WP-6 Domain core (S)"]
  WP_7["WP-7 Worker (S)"]
  WP_8["WP-8 Import/export (S)"]
  WP_9["WP-9 Batch job (S)"]
  WP_10["WP-10 Public HTTP API (S)"]
  WP_2 --> WP_3
  WP_2 --> WP_4
  WP_2 --> WP_5
  WP_1 --> WP_6
  WP_2 --> WP_6
  WP_5 --> WP_6
  WP_2 --> WP_7
  WP_3 --> WP_7
  WP_4 --> WP_7
  WP_6 --> WP_7
  WP_6 --> WP_8
  WP_2 --> WP_9
  WP_4 --> WP_9
  WP_6 --> WP_9
  WP_8 --> WP_9
  WP_2 --> WP_10
  WP_4 --> WP_10
  WP_6 --> WP_10
  WP_8 --> WP_10
```

**Waves** (packages in one wave may run in parallel):

1. WP-1, WP-2
2. WP-3, WP-4, WP-5
3. WP-6
4. WP-7, WP-8
5. WP-10, WP-9

_Critical path (13 person-days):_ WP-2 → WP-5 → WP-6 → WP-8 → WP-9

### WP-1 — Audit log (S)

Implement Audit log: Append-only record of who did what to which resource, queryable by resource and actor.

- **components**: C-4 · **implements**: I-4
- **depends on**: — · **satisfies**: R-3
- **write scope**: `app/audit.py`, `tests/test_audit.py`
- **acceptance**:
  - A-1 (test) unit tests of Audit log pass — `python -m pytest -q tests/test_audit.py`
- **notes**: family: audit_log

### WP-2 — Store + Work queue + Observability (M)

Implement Store: Owns persistence of the domain entities: durable writes, reads, listing, and the schema/migrations; Work queue: Durable, ordered hand-off of work items between the ingest path and the workers, with visibility timeout and dead-letter; Observability: Metrics registry and exposition, structured logging, health/readiness endpoints.

- **components**: C-1, C-2, C-8 · **implements**: I-1, I-2, I-8
- **depends on**: — · **satisfies**: R-2, R-6, R-9, R-11, R-12, R-14
- **write scope**: `app/store.py`, `tests/test_store.py`, `app/queue.py`, `tests/test_queue.py`, `app/observability.py`, `tests/test_observability.py`
- **acceptance**:
  - A-2 (test) unit tests of Store, Work queue, Observability pass — `python -m pytest -q tests/test_store.py tests/test_queue.py tests/test_observability.py`
  - A-3 (metric) R-9: ratio 99.9 % — kill one instance under load; error rate stays within the target — metric R-9
- **notes**: family: infra

### WP-3 — Outbound HTTP client (S)

Implement Outbound HTTP client: Performs the outbound HTTP call with timeouts, size limits, redirect and private-address protection, and returns a classified outcome.

- **components**: C-6 · **implements**: I-6
- **depends on**: WP-2 · **satisfies**: R-2
- **write scope**: `app/dispatcher.py`, `tests/test_dispatcher.py`
- **acceptance**:
  - A-4 (test) unit tests of Outbound HTTP client pass — `python -m pytest -q tests/test_dispatcher.py`
- **notes**: family: async_delivery

### WP-4 — Authentication + Scheduler (M)

Implement Authentication: Authenticates callers and resolves them to a principal and scope; enforces authorization for management operations; Scheduler: Computes when deferred work runs next (backoff schedules, periodic jobs) and promotes due work.

- **components**: C-9, C-12 · **implements**: I-9, I-12
- **depends on**: WP-2 · **satisfies**: R-2, R-4, R-17
- **write scope**: `app/auth.py`, `tests/test_auth.py`, `app/scheduler.py`, `tests/test_scheduler.py`
- **acceptance**:
  - A-5 (test) unit tests of Authentication, Scheduler pass — `python -m pytest -q tests/test_auth.py tests/test_scheduler.py`
- **notes**: family: infra

### WP-5 — Notifier (S)

Implement Notifier: Sends operator/customer notifications through the configured channel with templating and rate limiting.

- **components**: C-7 · **implements**: I-7
- **depends on**: WP-2 · **satisfies**: R-1
- **write scope**: `app/notifier.py`, `tests/test_notifier.py`
- **acceptance**:
  - A-6 (test) unit tests of Notifier pass — `python -m pytest -q tests/test_notifier.py`
- **notes**: family: notification

### WP-6 — Domain core (S)

Implement Domain core: Business rules and validation for the domain entities; the only module that changes state through the store.

- **components**: C-5 · **implements**: I-5
- **depends on**: WP-1, WP-2, WP-5 · **satisfies**: R-2, R-13, R-16, R-18, R-19
- **write scope**: `app/core.py`, `tests/test_core.py`
- **acceptance**:
  - A-7 (test) unit tests of Domain core pass — `python -m pytest -q tests/test_core.py`
- **notes**: family: async_delivery

### WP-7 — Worker (S)

Implement Worker: Leases work items, performs the outbound action, records the outcome, and decides retry vs. final failure.

- **components**: C-11 · **implements**: I-11
- **depends on**: WP-2, WP-3, WP-4, WP-6 · **satisfies**: R-2, R-5, R-6, R-8, R-15
- **write scope**: `app/worker.py`, `tests/test_worker.py`
- **acceptance**:
  - A-8 (test) unit tests of Worker pass — `python -m pytest -q tests/test_worker.py`
  - A-9 (metric) R-8: p95 latency at 1 s <= 300 ms — load test at the stated rate; the stated percentile must meet the target — metric R-8
- **notes**: family: async_delivery

### WP-8 — Import/export (S)

Implement Import/export: Streams records to and from CSV/JSON with validation and partial-failure reporting.

- **components**: C-10 · **implements**: I-10
- **depends on**: WP-6 · **satisfies**: R-2
- **write scope**: `app/exporter.py`, `tests/test_exporter.py`
- **acceptance**:
  - A-10 (test) unit tests of Import/export pass — `python -m pytest -q tests/test_exporter.py`
- **notes**: family: import_export

### WP-9 — Batch job (S)

Implement Batch job: Scheduled processing over stored records: extract, transform, aggregate, write results.

- **components**: C-13 · **implements**: I-13
- **depends on**: WP-2, WP-4, WP-6, WP-8 · **satisfies**: R-4
- **write scope**: `app/batch.py`, `tests/test_batch.py`
- **acceptance**:
  - A-11 (test) unit tests of Batch job pass — `python -m pytest -q tests/test_batch.py`
- **notes**: family: batch_pipeline

### WP-10 — Public HTTP API (S)

Implement Public HTTP API: Translates HTTP requests into core calls: routing, request validation, error mapping, JSON.

- **components**: C-14 · **implements**: I-14
- **depends on**: WP-2, WP-4, WP-6, WP-8 · **satisfies**: R-5, R-6, R-7, R-8, R-10, R-15
- **write scope**: `app/surface_api.py`, `tests/test_surface_api.py`
- **acceptance**:
  - A-12 (test) unit tests of Public HTTP API pass — `python -m pytest -q tests/test_surface_api.py`
  - A-13 (metric) R-8: p95 latency at 1 s <= 300 ms — load test at the stated rate; the stated percentile must meet the target — metric R-8
- **notes**: family: infra

## Traceability

| requirement | priority | components | work packages | acceptance |
|---|---|---|---|---|
| R-1 | must | C-3, C-7 | WP-5 | A-6 |
| R-2 | must | C-2, C-5, C-6, C-10, C-11, C-12 | WP-2, WP-3, WP-4, WP-6, WP-7, WP-8 | A-2, A-3, A-4, A-5, A-7, A-8, A-9, A-10 |
| R-3 | must | C-4 | WP-1 | A-1 |
| R-4 | must | C-12, C-13 | WP-4, WP-9 | A-5, A-11 |
| R-5 | must | C-11, C-14 | WP-7, WP-10 | A-8, A-9, A-12, A-13 |
| R-6 | should | C-2, C-11, C-14 | WP-2, WP-7, WP-10 | A-2, A-3, A-8, A-9, A-12, A-13 |
| R-7 | must | C-14 | WP-10 | A-12, A-13 |
| R-8 | must | C-11, C-14 | WP-7, WP-10 | A-8, A-9, A-12, A-13 |
| R-9 | must | C-2, C-8 | WP-2 | A-2, A-3 |
| R-10 | should | C-14 | WP-10 | A-12, A-13 |
| R-11 | should | C-1, C-2 | WP-2 | A-2, A-3 |
| R-12 | must | C-2, C-8 | WP-2 | A-2, A-3 |
| R-13 | must | C-5 | WP-6 | A-7 |
| R-14 | must | C-1 | WP-2 | A-2, A-3 |
| R-15 | must | C-11, C-14 | WP-7, WP-10 | A-8, A-9, A-12, A-13 |
| R-16 | must | C-5 | WP-6 | A-7 |
| R-17 | must | C-9 | WP-4 | A-5 |
| R-18 | must | C-5 | WP-6 | A-7 |
| R-19 | must | C-5 | WP-6 | A-7 |

## Conventions

- **language**: python
- **test**: `python -m pytest -q`
- **lint**: `ruff check .`
- Type hints on every public function; dataclasses or pydantic for records.
- No business logic in the HTTP layer.
- Every component logs one structured line per unit of work with the correlation id.
- No in-process state that a second instance would not see; instances are interchangeable.
- Prefer the boring option; a new piece of infrastructure needs a decision record.
- Python 3.12 as stated in the constraints.
- Stateless processes: configuration from the environment, no local files that a second instance would not see.

**Definition of done**

- Acceptance checks of the package pass.
- No file outside the write scope changed.
- Every public operation of the implemented interfaces exists with the declared inputs.
