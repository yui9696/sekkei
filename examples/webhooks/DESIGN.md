# webhook-delivery-service — design

We run a SaaS.

_version 0.1.0 · schema sekkei/1_

## Goals

- Clients read and write domain resources over HTTP.
- Customers or operators manage resources through an authenticated API.
- Producers hand events to the system, which persists them before acknowledging.
- Work is queued durably and performed by workers with a retry schedule.
- Outbound requests carry an HMAC signature; secrets rotate with a grace window.
- The system notifies people through an external channel.
- Targets that keep failing are disabled by policy and the owner is told.
- Metrics, structured logs and health endpoints for operations.

## Requirements

| id | kind | priority | statement | metric |
|---|---|---|---|---|
| R-1 | functional | must | Customers register webhook endpoints; when things happen in our platform (order.created, order.paid, refund.issued, ...) we must deliver a signed JSON event to every endpoint subscribed to that event type. | — |
| R-2 | functional | must | Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose event types, rotate the signing secret. | — |
| R-3 | functional | must | Internal services publish events through an internal API (HTTP or in-process call). | — |
| R-4 | functional | must | Each event is delivered at least once to every matching endpoint. Deliveries are retried with exponential backoff (1 min, 5 min, 30 min, 2 h, 12 h; 5 attempts) on 5xx/timeout. 4xx (except 429) is final failure. 429 honours Retry-After. | — |
| R-5 | functional | must | Every delivery carries an HMAC-SHA256 signature over the body with the endpoint's current secret, plus a timestamp header; after rotation, both old and new secrets are valid for 24 h. | — |
| R-6 | functional | must | Customers can see delivery attempts per event (status, response code, timestamps) and manually redeliver. | — |
| R-7 | functional | must | Endpoints that fail continuously for 3 days are disabled automatically and the customer is notified by email. | — |
| R-8 | nonfunctional | should | 1,000 events/s sustained publish rate, 5,000 endpoints; delivery latency p95 under 5 s for a healthy endpoint. | p95 latency at 1,000, 5,000 < 5 s s |
| R-9 | nonfunctional | should | No event lost on process crash (persist before ack). | records lost across a process crash = 0 records |
| R-10 | nonfunctional | must | Per-endpoint isolation: one slow endpoint must not delay others. | p95 latency of healthy targets while one target stalls within the stated latency target |
| R-11 | nonfunctional | should | Ops: metrics (queue depth, delivery success rate, attempt latency) exposed for Prometheus; structured logs. | required metrics exposed = all listed |
| R-12 | constraint | must | Python 3.12, PostgreSQL available, Redis available. Single region. Team of 3. | — |
| R-13 | constraint | must | Must run as a set of stateless containers behind our existing ingress. | — |

## Components

```mermaid
graph LR
  C_1[("C-1 Store")]
  C_2[("C-2 Work queue")]
  C_3[("C-3 Secret store")]
  C_4[["C-4 Email provider"]]
  C_5[["C-5 Customer endpoint"]]
  C_6["C-6 Domain core"]
  C_7["C-7 Outbound HTTP client"]
  C_8["C-8 Signer"]
  C_9["C-9 Notifier"]
  C_10["C-10 Observability"]
  C_11["C-11 Authentication"]
  C_12["C-12 Worker"]
  C_13["C-13 Scheduler"]
  C_14["C-14 Health policy"]
  C_15["C-15 Admin HTTP API"]
  C_16["C-16 Ingest API"]
  C_6 -->|I-1| C_1
  C_6 -->|I-10| C_10
  C_6 -->|I-3| C_3
  C_6 -->|I-9| C_9
  C_7 -->|I-10| C_10
  C_8 -->|I-3| C_3
  C_9 -->|I-4| C_4
  C_9 -->|I-10| C_10
  C_11 -->|I-1| C_1
  C_12 -->|I-2| C_2
  C_12 -->|I-6| C_6
  C_12 -->|I-13| C_13
  C_12 -->|I-10| C_10
  C_12 -->|I-7| C_7
  C_12 -->|I-8| C_8
  C_13 -->|I-10| C_10
  C_13 -->|I-2| C_2
  C_14 -->|I-6| C_6
  C_14 -->|I-9| C_9
  C_14 -->|I-10| C_10
  C_15 -->|I-6| C_6
  C_15 -->|I-11| C_11
  C_15 -->|I-10| C_10
  C_15 -->|I-3| C_3
  C_16 -->|I-6| C_6
  C_16 -->|I-2| C_2
  C_16 -->|I-10| C_10
  C_16 -->|I-11| C_11
```

### C-1 — Store

- **kind**: datastore · **path**: `app/store.py`
- **responsibility**: Owns persistence of the domain entities: durable writes, reads, listing, and the schema/migrations.
- **provides**: I-1
- **requires**: —
- **satisfies**: R-9, R-12

### C-2 — Work queue

- **kind**: datastore · **path**: `app/queue.py`
- **responsibility**: Durable, ordered hand-off of work items between the ingest path and the workers, with visibility timeout and dead-letter.
- **provides**: I-2
- **requires**: —
- **satisfies**: R-1, R-3, R-4, R-5, R-6, R-8, R-9, R-10

### C-3 — Secret store

- **kind**: datastore · **path**: `app/secrets.py`
- **responsibility**: Holds per-endpoint signing secrets and their rotation history; encrypts at rest.
- **provides**: I-3
- **requires**: —
- **satisfies**: R-1, R-2, R-5

### C-4 — Email provider

- **kind**: external
- **responsibility**: External email delivery service.
- **provides**: I-4
- **requires**: —
- **satisfies**: R-7

### C-5 — Customer endpoint

- **kind**: external
- **responsibility**: The customer's HTTPS receiver; outside our control.
- **provides**: I-5
- **requires**: —
- **satisfies**: R-1, R-4, R-5, R-6

### C-6 — Domain core

- **kind**: module · **path**: `app/core.py`
- **responsibility**: Business rules and validation for the domain entities; the only module that changes state through the store.
- **provides**: I-6
- **requires**: I-1, I-10, I-3, I-9
- **satisfies**: R-1, R-2, R-3, R-4, R-5, R-6, R-7, R-12

### C-7 — Outbound HTTP client

- **kind**: module · **path**: `app/dispatcher.py`
- **responsibility**: Performs the outbound HTTP call with timeouts, size limits, redirect and private-address protection, and returns a classified outcome.
- **provides**: I-7
- **requires**: I-10
- **satisfies**: R-1, R-4, R-5, R-6

### C-8 — Signer

- **kind**: module · **path**: `app/signer.py`
- **responsibility**: Produces and verifies HMAC signatures over request bodies with the current and previous secrets.
- **provides**: I-8
- **requires**: I-3
- **satisfies**: R-1, R-2, R-5

### C-9 — Notifier

- **kind**: module · **path**: `app/notifier.py`
- **responsibility**: Sends operator/customer notifications through the configured channel with templating and rate limiting.
- **provides**: I-9
- **requires**: I-4, I-10
- **satisfies**: R-7

### C-10 — Observability

- **kind**: module · **path**: `app/observability.py`
- **responsibility**: Metrics registry and exposition, structured logging, health/readiness endpoints.
- **provides**: I-10
- **requires**: —
- **satisfies**: R-8, R-11

### C-11 — Authentication

- **kind**: module · **path**: `app/auth.py`
- **responsibility**: Authenticates callers and resolves them to a principal and scope; enforces authorization for management operations.
- **provides**: I-11
- **requires**: I-1
- **satisfies**: R-1, R-2, R-6

### C-12 — Worker

- **kind**: job · **path**: `app/worker.py`
- **responsibility**: Leases work items, performs the outbound action, records the outcome, and decides retry vs. final failure.
- **provides**: I-12
- **requires**: I-2, I-6, I-13, I-10, I-7, I-8
- **satisfies**: R-1, R-4, R-5, R-6, R-8, R-10, R-11, R-13

### C-13 — Scheduler

- **kind**: job · **path**: `app/scheduler.py`
- **responsibility**: Computes when deferred work runs next (backoff schedules, periodic jobs) and promotes due work.
- **provides**: I-13
- **requires**: I-10, I-2
- **satisfies**: R-1, R-4, R-5, R-6

### C-14 — Health policy

- **kind**: job · **path**: `app/policy.py`
- **responsibility**: Evaluates per-target failure history against the disable policy and applies the consequence.
- **provides**: I-14
- **requires**: I-6, I-9, I-10
- **satisfies**: R-7

### C-15 — Admin HTTP API

- **kind**: service · **path**: `app/admin_api.py`
- **responsibility**: Management surface for operators/customers: resource lifecycle and configuration; authenticated.
- **provides**: I-15
- **requires**: I-6, I-11, I-10, I-3
- **satisfies**: R-1, R-2, R-6, R-8, R-11, R-13

### C-16 — Ingest API

- **kind**: service · **path**: `app/ingest_api.py`
- **responsibility**: Accepts events/records from producers, validates them, persists them, and enqueues work; acknowledges only after persistence.
- **provides**: I-16
- **requires**: I-6, I-2, I-10, I-11
- **satisfies**: R-3, R-8, R-9, R-11, R-13

**Layers** (each layer depends only on earlier ones):

0. C-1, C-10, C-2, C-3, C-4, C-5
1. C-11, C-13, C-7, C-8, C-9
2. C-6
3. C-12, C-14, C-15, C-16

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

### I-3 — Secret store interface

- **kind**: class · **owner**: C-3 · **stability**: stable
- Provided by Secret store. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `current` | `endpoint_id`: str | list[Secret] valid now | — | — |
| `rotate` | `endpoint_id`: str, `grace`: timedelta | Secret new | — | stated values: 24 h (R-5) / old secret stays valid until now + grace |

### I-4 — Email provider interface

- **kind**: http · **owner**: C-4 · **stability**: stable
- Provided by Email provider. External; contract is theirs.

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `send` | `to`: str, `subject`: str, `body`: str | provider message id | — | — |

### I-5 — Customer endpoint interface

- **kind**: http · **owner**: C-5 · **stability**: stable
- Provided by Customer endpoint. External; contract is theirs.

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `POST <url>` | `body`: json, `signature headers`: str | 2xx on acceptance | 4xx final, 5xx retry, 429 with Retry-After | — |

### I-6 — Domain core interface

- **kind**: module · **owner**: C-6 · **stability**: draft
- Provided by Domain core. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `register_endpoints` | `endpoints`: Endpoints \| id | Endpoints \| None | ValidationError, NotFound | — |
| | from R-1: Customers register webhook endpoints; when things happen in our platform (order.created, o | | | |
| `deliver_event` | `event`: Event \| id | Event \| None | ValidationError, NotFound | — |
| | from R-1: Customers register webhook endpoints; when things happen in our platform (order.created, o | | | |
| `sign_event` | `event`: Event \| id | Event \| None | ValidationError, NotFound | — |
| | from R-1: Customers register webhook endpoints; when things happen in our platform (order.created, o | | | |
| `manage_endpoints` | `endpoints`: Endpoints \| id | Endpoints \| None | ValidationError, NotFound | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `create_endpoints` | `endpoints`: Endpoints \| id | Endpoints \| None | ValidationError, NotFound | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `list_endpoints` | `endpoints`: Endpoints \| id | Endpoints \| None | ValidationError, NotFound | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `delete_endpoints` | `endpoints`: Endpoints \| id | Endpoints \| None | ValidationError, NotFound | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `set_types` | `types`: Types \| id | Types \| None | ValidationError, NotFound | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `rotate_secret` | `secret`: Secret \| id | Secret \| None | ValidationError, NotFound | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `sign_secret` | `secret`: Secret \| id | Secret \| None | ValidationError, NotFound | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `publish_events` | `events`: Events \| id | Events \| None | ValidationError, NotFound | — |
| | from R-3: Internal services publish events through an internal API (HTTP or in-process call). | | | |
| `get_attempts` | `attempts`: Attempts \| id | Attempts \| None | ValidationError, NotFound | — |
| | from R-6: Customers can see delivery attempts per event (status, response code, timestamps) and manu | | | |
| `redeliver_timestamps` | `timestamps`: Timestamps \| id | Timestamps \| None | ValidationError, NotFound | — |
| | from R-6: Customers can see delivery attempts per event (status, response code, timestamps) and manu | | | |
| `disable_fail` | `fail`: Fail \| id | Fail \| None | ValidationError, NotFound | — |
| | from R-7: Endpoints that fail continuously for 3 days are disabled automatically and the customer is | | | |
| `notify_customer` | `customer`: Customer \| id | Customer \| None | ValidationError, NotFound | — |
| | from R-7: Endpoints that fail continuously for 3 days are disabled automatically and the customer is | | | |

### I-7 — Outbound HTTP client interface

- **kind**: module · **owner**: C-7 · **stability**: draft
- Provided by Outbound HTTP client. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `post` | `url`: str, `body`: bytes, `headers`: dict, `timeout`: float | Outcome(status, latency, retry_after) | TimeoutError, ConnectionError, BlockedAddressError | url resolves to a public address |

### I-8 — Signer interface

- **kind**: module · **owner**: C-8 · **stability**: draft
- Provided by Signer. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `sign` | `body`: bytes, `timestamp`: int, `secret`: bytes | signature hex | — | HMAC-SHA256(timestamp + '.' + body) |
| `headers` | `body`: bytes, `secrets`: list[bytes] | dict of signature headers | — | — |
| | one header per valid secret during a rotation window | | | |

### I-9 — Notifier interface

- **kind**: module · **owner**: C-9 · **stability**: draft
- Provided by Notifier. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `notify` | `recipient`: str, `template`: str, `context`: dict | message id | NotifyError | — |

### I-10 — Observability interface

- **kind**: module · **owner**: C-10 · **stability**: draft
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

### I-11 — Authentication interface

- **kind**: module · **owner**: C-11 · **stability**: draft
- Provided by Authentication. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `authenticate` | `credentials`: str | Principal | AuthError | — |
| `authorize` | `principal`: Principal, `action`: str, `resource`: str | None | Forbidden | — |

### I-12 — Worker interface

- **kind**: module · **owner**: C-12 · **stability**: draft
- Provided by Worker. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `run_once` | `partition`: str | int processed | — | — |
| | one lease/process/ack cycle; the loop and concurrency live in the process entry point | | | |
| `process` | `item`: WorkItem | Outcome | DeliveryError | outcome recorded through core before ack |

### I-13 — Scheduler interface

- **kind**: module · **owner**: C-13 · **stability**: draft
- Provided by Scheduler. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `next_attempt` | `attempt`: int, `retry_after`: timedelta \| None | datetime \| None | — | stated values: 1 min (R-4); 5 min (R-4); 30 min (R-4); 2 h (R-4); 12 h (R-4); 5 attempts (R-4); 24 h (R-5) |
| | None when attempts are exhausted | | | |
| `promote_due` | `now`: datetime | int moved | — | — |

### I-14 — Health policy interface

- **kind**: module · **owner**: C-14 · **stability**: draft
- Provided by Health policy. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `evaluate` | `now`: datetime | list[action taken] | — | stated values: 3 days (R-7) |
| | disables targets failing continuously beyond the window and notifies | | | |

### I-15 — Admin HTTP API interface

- **kind**: http · **owner**: C-15 · **stability**: draft
- Provided by Admin HTTP API. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `POST /endpoints` | `body`: endpoints fields | 201 {endpoints id} | 400 invalid body, 401 unauthenticated, 409 conflict | — |
| | from R-1: Customers register webhook endpoints; when things happen in our platform (order.created, o | | | |
| `GET /endpoints` | `filter`: query, `page`: cursor | 200 [endpoints], next cursor | 401 unauthenticated | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `DELETE /endpoints/{id}` | `id`: str | 204 | 401 unauthenticated, 404 unknown id | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `POST /secrets/{id}/rotate` | `id`: str | 202 rotate accepted | 401 unauthenticated, 404 unknown id, 409 not applicable in current state | — |
| | from R-2: Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose eve | | | |
| `GET /attempts/{id}` | `id`: str | 200 attempts | 401 unauthenticated, 404 unknown id | — |
| | from R-6: Customers can see delivery attempts per event (status, response code, timestamps) and manu | | | |
| `POST /timestamps/{id}/redeliver` | `id`: str | 202 redeliver accepted | 401 unauthenticated, 404 unknown id, 409 not applicable in current state | — |
| | from R-6: Customers can see delivery attempts per event (status, response code, timestamps) and manu | | | |

### I-16 — Ingest API interface

- **kind**: http · **owner**: C-16 · **stability**: draft
- Provided by Ingest API. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `POST /events` | `type`: str, `payload`: json, `idempotency_key`: str | 202 {event_id} | 400 invalid payload, 409 duplicate idempotency key | event persisted and enqueued before 202 |

## Entities

### E-1 — Record (owner C-1)

Generic domain record; refine per entity found in the requirements.

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `created_at` | timestamp |  |
| `updated_at` | timestamp |  |

### E-2 — Principal (owner C-1)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `kind` | enum(customer, operator, service) |  |
| `scopes` | list[str] |  |

### E-3 — Event (owner C-1)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `type` | str | indexed |
| `payload` | json |  |
| `created_at` | timestamp |  |
| `idempotency_key` | str | unique per producer |

### E-4 — WorkItem (owner C-2)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `partition` | str | indexed; the isolation key |
| `payload_ref` | uuid | references the event |
| `attempt` | int | >= 0 |
| `not_before` | timestamp | indexed |
| `leased_until` | timestamp \| null |  |

### E-5 — DeliveryAttempt (owner C-1)

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

### E-6 — Endpoint (owner C-1)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `owner_id` | uuid | indexed |
| `url` | https url | validated; no private addresses |
| `event_types` | list[str] |  |
| `enabled` | bool |  |
| `disabled_reason` | str \| null |  |
| `failing_since` | timestamp \| null |  |

### E-7 — Secret (owner C-3)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `endpoint_id` | uuid | indexed |
| `value` | bytes | encrypted at rest |
| `created_at` | timestamp |  |
| `valid_until` | timestamp \| null | set on rotation |

## Flows

### F-1 — Manage a resource

_Trigger:_ authenticated management request

1. C-15 → C-11 via I-11: authenticate and authorize
2. C-15 → C-6 via I-6: apply the change
3. C-6 → C-1 via I-1: persist

```mermaid
sequenceDiagram
  participant C_15 as C-15 Admin HTTP API
  participant C_11 as C-11 Authentication
  participant C_6 as C-6 Domain core
  participant C_1 as C-1 Store
  Note over C_15: authenticated management request
  C_15->>C_11: I-11 authenticate and authorize
  C_15->>C_6: I-6 apply the change
  C_6->>C_1: I-1 persist
```

### F-2 — Publish an event

_Trigger:_ producer calls the ingest API

1. C-16 → C-6 via I-6: validate the event against known types
2. C-6 → C-1 via I-1: persist the event
3. C-16 → C-2 via I-2: enqueue one work item per matching target; ack only after both are durable

```mermaid
sequenceDiagram
  participant C_16 as C-16 Ingest API
  participant C_6 as C-6 Domain core
  participant C_1 as C-1 Store
  participant C_2 as C-2 Work queue
  Note over C_16: producer calls the ingest API
  C_16->>C_6: I-6 validate the event against known types
  C_6->>C_1: I-1 persist the event
  C_16->>C_2: I-2 enqueue one work item per matching target; ack only after both are durable
```

### F-3 — Deliver a work item

_Trigger:_ worker leases due items

1. C-12 → C-2 via I-2: lease items of one partition
2. C-12 → C-6 via I-6: load target, secrets and payload
3. C-12 → C-2 via I-2: ack on success, nack with retry_at on retryable failure, dead-letter when exhausted

```mermaid
sequenceDiagram
  participant C_12 as C-12 Worker
  participant C_2 as C-2 Work queue
  participant C_6 as C-6 Domain core
  Note over C_12: worker leases due items
  C_12->>C_2: I-2 lease items of one partition
  C_12->>C_6: I-6 load target, secrets and payload
  C_12->>C_2: I-2 ack on success, nack with retry_at on retryable failure, dead-letter when exhausted
```

### F-4 — Retry after failure

_Trigger:_ scheduler tick

1. C-13 → C-2 via I-2: promote items whose not_before has passed

```mermaid
sequenceDiagram
  participant C_13 as C-13 Scheduler
  participant C_2 as C-2 Work queue
  Note over C_13: scheduler tick
  C_13->>C_2: I-2 promote items whose not_before has passed
```

### F-5 — Disable a continuously failing target

_Trigger:_ policy tick

1. C-14 → C-6 via I-6: read failure history and disable the target
2. C-14 → C-9 via I-9: notify the owner

```mermaid
sequenceDiagram
  participant C_14 as C-14 Health policy
  participant C_6 as C-6 Domain core
  participant C_9 as C-9 Notifier
  Note over C_14: policy tick
  C_14->>C_6: I-6 read failure history and disable the target
  C_14->>C_9: I-9 notify the owner
```

## Decisions

### D-1 — API style (accepted)

**Context.** Clients need a programmable surface.

- ✔ **REST/JSON over HTTP**
  - + universal tooling
  - + cacheable reads
  - − over-fetching on nested data
- ✘ **gRPC**
  - + typed contracts
  - + streaming
  - − browser and debugging friction
- ✘ **GraphQL**
  - + flexible queries
  - − complexity budget for a small team

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). REST/JSON over HTTP: 1.44; gRPC: 1.31; GraphQL: 1.16

**Consequences.** Not choosing 'gRPC' gives up: typed contracts, streaming. Not choosing 'GraphQL' gives up: flexible queries.

_Affects:_ C-15

### D-2 — Primary store (accepted)

**Context.** Domain records need durable, queryable storage.

- ✔ **PostgreSQL**
  - + transactions
  - + indexes and JSON
  - + already available
  - − operational dependency
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

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). PostgreSQL: 3.34; In-memory: 1.44; SQLite: unavailable (ruled out by containers, multi_instance); Files: unavailable (ruled out by containers, multi_instance). stated in the constraints

**Consequences.** Not choosing 'In-memory' gives up: fastest, trivial.

_Affects:_ C-1

### D-3 — Caller authentication (accepted)

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

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). API keys per customer, hashed at rest, sent as a: 1.38; Mutual TLS: 1.04; OAuth2 / OIDC with the platform's identity provi: unavailable (needs idp, not in the constraints)

**Consequences.** Not choosing 'Mutual TLS' gives up: strong, no secrets in headers.

_Affects:_ C-11, C-15

### D-4 — How producers publish (accepted)

**Context.** Internal services must hand events to the system.

- ✔ **HTTP publish endpoint with idempotency keys**
  - + language-agnostic
  - + one contract
  - − one network hop
  - − callers need retries
- ✘ **In-process client library that writes the outbox in the caller's transaction**
  - + no lost events at the source
  - − couples callers to our schema and language
- ✘ **Message bus topic**
  - + decoupled
  - − new infrastructure

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). HTTP publish endpoint with idempotency keys: 1.94; In-process client library that writes the outbox: 1.66; Message bus topic: unavailable (needs broker, not in the constraints)

**Consequences.** Not choosing 'In-process client library that writes the outbox' gives up: no lost events at the source.

_Affects:_ C-16

### D-5 — Work queue technology (accepted)

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

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). PostgreSQL table with SELECT ... FOR UPDATE SKIP: 2.37; Redis Streams with consumer groups: 2.01; In-memory queue: 1.44; Managed broker: unavailable (needs broker, not in the constraints)

**Consequences.** Not choosing 'Redis Streams with consumer groups' gives up: high throughput, built-in consumer groups and pending lists. Not choosing 'In-memory queue' gives up: simplest possible.

_Affects:_ C-2, C-16, C-12

### D-6 — Where delayed retries wait (accepted)

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

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). not_before column on the work item: 2.08; Redis sorted set keyed by due time: 1.60; In-process timers: 1.42

**Consequences.** Not choosing 'Redis sorted set keyed by due time' gives up: cheap due-time queries. Not choosing 'In-process timers' gives up: no store.

_Affects:_ C-13, C-2

### D-7 — Process topology (accepted)

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

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). One image, role by flag: `api` and `worker` proc: 1.84; Separate services per concern: 1.58; Single process with background threads: 1.43

**Consequences.** Not choosing 'Separate services per concern' gives up: clear ownership. Not choosing 'Single process with background threads' gives up: one deployable.

_Affects:_ C-15, C-16, C-12, C-13, C-14

### D-8 — Outbound request safety (accepted)

**Context.** The system makes HTTP requests to customer-supplied URLs.

- ✔ **Resolve and block private/link-local ranges; pin the resolved IP; cap body size and redirects; per-request timeout**
  - + closes SSRF and slow-loris classes
  - − a resolver step per request
- ✘ **Plain HTTP client with a timeout**
  - + simplest
  - − SSRF into internal networks
  - − unbounded response bodies

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). Resolve and block private/link-local ranges: 1.49; Plain HTTP client with a timeout: 1.19

**Consequences.** Not choosing 'Plain HTTP client with a timeout' gives up: simplest.

_Affects:_ C-7

### D-9 — Storage of signing secrets (accepted)

**Context.** Per-endpoint secrets are sensitive and must be readable by workers.

- ✔ **Encrypted column (AES-GCM) with a key from the environment/KMS**
  - + one store
  - + workers read directly
  - − key rotation procedure needed
- ✘ **External secrets manager (Vault/KMS-backed)**
  - + audited access
  - + rotation built in
  - − latency and a new dependency on the hot path
- ✘ **Plaintext column**
  - + simplest
  - − database dump exposes every customer secret

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). Encrypted column: 1.52; Plaintext column: 1.48; External secrets manager: unavailable (needs vault, not in the constraints)

**Consequences.** Not choosing 'Plaintext column' gives up: simplest.

_Affects:_ C-3, C-8

### D-10 — Per-target isolation of outbound work (accepted)

**Context.** One slow or failing target must not delay work for the others.

- ✔ **Partition the queue by target; each lease takes one partition with a per-partition concurrency cap**
  - + a slow target only occupies its own slot
  - + fair scheduling across targets
  - − more bookkeeping in the queue
  - − partition count = target count
- ✘ **Single FIFO queue with a global worker pool**
  - + simplest
  - − one slow target blocks pool slots for everyone (head-of-line blocking)
- ✘ **Hash targets to N shards, one worker pool per shard**
  - + bounded blast radius without per-target state
  - − a slow target still delays its shard

**Rationale.** Scored against the active qualities; decided by durability (weight 1.0), isolation (weight 0.94). Partition the queue by target: 1.74; Hash targets to N shards, one worker pool per sh: 1.59; Single FIFO queue with a global worker pool: 1.40

**Consequences.** Not choosing 'Hash targets to N shards, one worker pool per sh' gives up: bounded blast radius without per-target state. Not choosing 'Single FIFO queue with a global worker pool' gives up: simplest.

_Affects:_ C-2, C-12

## Risks

| id | risk | likelihood | impact | mitigation |
|---|---|---|---|---|
| K-1 | Payloads or uploads without size limits exhaust memory or disk. | medium | medium | Enforce size limits at the surface; reject early with a clear error. |
| K-2 | Entities evolve; migrations run against live data. | medium | medium | Versioned migrations applied before deploy; additive changes first, removals one release later. |
| K-3 | A management operation reachable without authentication. | low | high | Authenticate in one middleware for every management route; test every route unauthenticated. |
| K-4 | At-least-once delivery means a target can receive the same event twice (crash between call and ack). | high | medium | Send a stable event id and attempt number in headers; document idempotent consumption; never retry on 2xx. |
| K-5 | Many targets fail at once (regional outage) and their retries align, creating a burst. | medium | medium | Add jitter to the backoff schedule and cap concurrent deliveries per partition and globally. |
| K-6 | Customer-supplied URLs can point at internal addresses or metadata services. | high | high | Resolve before connecting, block private ranges, pin the IP, forbid redirects to non-public hosts. |
| K-7 | Retried and dead-lettered items accumulate and slow the lease query. | medium | medium | Partial index on (partition, not_before) for live items; archive terminal items on a schedule. |
| K-8 | Timestamp-based signatures and not_before scheduling depend on wall clocks. | low | medium | Use the database clock for scheduling; tolerate a bounded skew window when verifying timestamps. |
| K-9 | Signing secrets in the database are exposed by a dump or a read-only breach. | medium | high | Encrypt at rest with a key outside the database; log secret reads; rotate on suspicion. |
| K-10 | A widespread failure disables many targets and emails every owner at once. | low | medium | Rate-limit notifications per owner and batch them. |
| K-11 | Per-target labels on metrics explode cardinality. | medium | low | Label by outcome and partition class, not by target id; expose per-target detail through the API instead. |
| K-12 | [tampering] Store: Injection through query construction. | medium | medium | Parameterised queries only; no string-built SQL. Check: static check for string-formatted SQL finds nothing |
| K-13 | [information_disclosure] Store: Backups and dumps contain everything. | medium | high | Encrypt backups; restrict who can take them. Check: backup file is not readable without the key |
| K-14 | [denial_of_service] Work queue: A poison item is retried forever and blocks its partition. | medium | medium | Attempt cap and dead-letter; per-partition concurrency cap. Check: an always-failing item ends in the dead-letter after the cap |
| K-15 | [tampering] Work queue: Items are processed twice after a crash between call and ack. | medium | medium | Idempotent processing with the item id; ack only after the outcome is recorded. Check: kill the worker mid-call; the item is redelivered exactly once more |
| K-16 | [information_disclosure] Secret store: Secrets readable from a database dump or a read-only breach. | medium | high | Encrypt at rest with a key held outside the database; never log values. Check: database dump contains no plaintext secret; grep logs for secret prefixes finds nothing |
| K-17 | [elevation] Secret store: A rotated secret stays valid forever. | medium | high | Bound the grace window; expire old secrets by time. Check: old secret rejected after the window |
| K-18 | [ssrf] Outbound HTTP client: A customer-supplied URL points at internal or metadata addresses. | medium | high | Resolve and block private/link-local ranges; pin the resolved IP; forbid redirects to non-public hosts. Check: URL to 169.254.169.254 / 10.0.0.1 / localhost is refused before connecting |
| K-19 | [denial_of_service] Outbound HTTP client: A slow or infinite response body ties up a worker. | medium | medium | Per-request timeout; cap response size; stream and discard bodies. Check: target that stalls is cut at the timeout; 100 MB body is cut at the cap |
| K-20 | [information_disclosure] Outbound HTTP client: Secrets or internal headers leak to targets. | medium | high | Send only the documented headers; never forward inbound headers. Check: captured request has exactly the documented headers |
| K-21 | [tampering] Signer: Signatures without a timestamp can be replayed. | medium | medium | Sign timestamp + body; document a tolerance window for verifiers. Check: replay outside the window fails verification |
| K-22 | [denial_of_service] Notifier: Notification storms and template injection. | medium | medium | Rate-limit per recipient; escape template context. Check: 1,000 failures produce one digest per owner |
| K-23 | [spoofing] Authentication: Credential stuffing or leaked keys. | medium | medium | Hash keys at rest; allow revocation; rate-limit failures. Check: revoked key is rejected within seconds; brute force is throttled |
| K-24 | [elevation] Authentication: A caller acts on another tenant's resources. | medium | high | Every core operation takes the principal and checks ownership. Check: cross-tenant request returns 404/403 for every operation |
| K-25 | [spoofing] Admin HTTP API: Management operations reachable without authentication. | medium | medium | Authenticate in one middleware for every management route; deny by default. Check: every management route returns 401 unauthenticated |
| K-26 | [repudiation] Admin HTTP API: No record of who changed what. | medium | medium | Audit log entries for every management write with the principal. Check: each write produces an audit entry |
| K-27 | [elevation] Admin HTTP API: A customer manages another customer's resources. | medium | high | Ownership check on every resource operation. Check: cross-customer access returns 404 |
| K-28 | [spoofing] Ingest API: Any network peer can publish events. | medium | medium | Authenticate producers (service credentials); allowlist event types. Check: unauthenticated publish returns 401 |
| K-29 | [tampering] Ingest API: Duplicate or replayed publishes create duplicate work. | medium | medium | Idempotency key per event; reject or de-duplicate replays. Check: replaying the same key does not enqueue twice |
| K-30 | [denial_of_service] Ingest API: A producer floods the ingest path. | medium | medium | Per-producer rate limit; back-pressure with 429 and Retry-After. Check: flood from one producer is throttled |

## Work packages

```mermaid
graph LR
  WP_1["WP-1 Store + Work queue + Observability (M)"]
  WP_2["WP-2 Secret store (S)"]
  WP_3["WP-3 Authentication + Outbound HTTP client + Scheduler (M)"]
  WP_4["WP-4 Notifier + Signer (M)"]
  WP_5["WP-5 Domain core (S)"]
  WP_6["WP-6 Admin HTTP API + Worker + Ingest API (M)"]
  WP_7["WP-7 Health policy (S)"]
  WP_1 --> WP_3
  WP_1 --> WP_4
  WP_2 --> WP_4
  WP_1 --> WP_5
  WP_2 --> WP_5
  WP_4 --> WP_5
  WP_1 --> WP_6
  WP_2 --> WP_6
  WP_3 --> WP_6
  WP_4 --> WP_6
  WP_5 --> WP_6
  WP_1 --> WP_7
  WP_4 --> WP_7
  WP_5 --> WP_7
```

**Waves** (packages in one wave may run in parallel):

1. WP-1, WP-2
2. WP-3, WP-4
3. WP-5
4. WP-6, WP-7

_Critical path (weight 7):_ WP-1 → WP-4 → WP-5 → WP-6

### WP-1 — Store + Work queue + Observability (M)

Implement Store: Owns persistence of the domain entities: durable writes, reads, listing, and the schema/migrations; Work queue: Durable, ordered hand-off of work items between the ingest path and the workers, with visibility timeout and dead-letter; Observability: Metrics registry and exposition, structured logging, health/readiness endpoints.

- **components**: C-1, C-2, C-10 · **implements**: I-1, I-2, I-10
- **depends on**: — · **satisfies**: R-1, R-3, R-4, R-5, R-6, R-8, R-9, R-10, R-11, R-12
- **write scope**: `app/store.py`, `tests/test_store.py`, `app/queue.py`, `tests/test_queue.py`, `app/observability.py`, `tests/test_observability.py`
- **acceptance**:
  - A-1 (test) unit tests of Store, Work queue, Observability pass — `python -m pytest -q tests/test_store.py tests/test_queue.py tests/test_observability.py`
  - A-2 (metric) R-8: p95 latency at 1,000, 5,000 < 5 s s — load test at the stated rate; the stated percentile must meet the target — metric R-8
  - A-3 (metric) R-9: records lost across a process crash = 0 records — crash/kill test: no accepted item is lost and none is delivered without a durable record — metric R-9
  - A-4 (metric) R-10: p95 latency of healthy targets while one target stalls within the stated latency target — one target stalled (timeouts) while others must keep meeting their latency target — metric R-10
  - A-5 (metric) R-11: required metrics exposed = all listed — load test at the stated rate; the stated percentile must meet the target — metric R-11
- **notes**: family: crud_api

### WP-2 — Secret store (S)

Implement Secret store: Holds per-endpoint signing secrets and their rotation history; encrypts at rest.

- **components**: C-3 · **implements**: I-3
- **depends on**: — · **satisfies**: R-1, R-2, R-5
- **write scope**: `app/secrets.py`, `tests/test_secrets.py`
- **acceptance**:
  - A-6 (test) unit tests of Secret store pass — `python -m pytest -q tests/test_secrets.py`
- **notes**: family: signing

### WP-3 — Authentication + Outbound HTTP client + Scheduler (M)

Implement Authentication: Authenticates callers and resolves them to a principal and scope; enforces authorization for management operations; Outbound HTTP client: Performs the outbound HTTP call with timeouts, size limits, redirect and private-address protection, and returns a classified outcome; Scheduler: Computes when deferred work runs next (backoff schedules, periodic jobs) and promotes due work.

- **components**: C-11, C-7, C-13 · **implements**: I-11, I-7, I-13
- **depends on**: WP-1 · **satisfies**: R-1, R-2, R-4, R-5, R-6
- **write scope**: `app/auth.py`, `tests/test_auth.py`, `app/dispatcher.py`, `tests/test_dispatcher.py`, `app/scheduler.py`, `tests/test_scheduler.py`
- **acceptance**:
  - A-7 (test) unit tests of Authentication, Outbound HTTP client, Scheduler pass — `python -m pytest -q tests/test_auth.py tests/test_dispatcher.py tests/test_scheduler.py`
- **notes**: family: admin_api

### WP-4 — Notifier + Signer (M)

Implement Notifier: Sends operator/customer notifications through the configured channel with templating and rate limiting; Signer: Produces and verifies HMAC signatures over request bodies with the current and previous secrets.

- **components**: C-9, C-8 · **implements**: I-9, I-8
- **depends on**: WP-1, WP-2 · **satisfies**: R-1, R-2, R-5, R-7
- **write scope**: `app/notifier.py`, `tests/test_notifier.py`, `app/signer.py`, `tests/test_signer.py`
- **acceptance**:
  - A-8 (test) unit tests of Notifier, Signer pass — `python -m pytest -q tests/test_notifier.py tests/test_signer.py`
- **notes**: family: notification

### WP-5 — Domain core (S)

Implement Domain core: Business rules and validation for the domain entities; the only module that changes state through the store.

- **components**: C-6 · **implements**: I-6
- **depends on**: WP-1, WP-2, WP-4 · **satisfies**: R-1, R-2, R-3, R-4, R-5, R-6, R-7, R-12
- **write scope**: `app/core.py`, `tests/test_core.py`
- **acceptance**:
  - A-9 (test) unit tests of Domain core pass — `python -m pytest -q tests/test_core.py`
- **notes**: family: crud_api

### WP-6 — Admin HTTP API + Worker + Ingest API (M)

Implement Admin HTTP API: Management surface for operators/customers: resource lifecycle and configuration; authenticated; Worker: Leases work items, performs the outbound action, records the outcome, and decides retry vs. final failure; Ingest API: Accepts events/records from producers, validates them, persists them, and enqueues work; acknowledges only after persistence.

- **components**: C-15, C-12, C-16 · **implements**: I-15, I-12, I-16
- **depends on**: WP-1, WP-2, WP-3, WP-4, WP-5 · **satisfies**: R-1, R-2, R-3, R-4, R-5, R-6, R-8, R-9, R-10, R-11, R-13
- **write scope**: `app/admin_api.py`, `tests/test_admin_api.py`, `app/worker.py`, `tests/test_worker.py`, `app/ingest_api.py`, `tests/test_ingest_api.py`
- **acceptance**:
  - A-10 (test) unit tests of Admin HTTP API, Worker, Ingest API pass — `python -m pytest -q tests/test_admin_api.py tests/test_worker.py tests/test_ingest_api.py`
  - A-11 (metric) R-8: p95 latency at 1,000, 5,000 < 5 s s — load test at the stated rate; the stated percentile must meet the target — metric R-8
  - A-12 (metric) R-9: records lost across a process crash = 0 records — crash/kill test: no accepted item is lost and none is delivered without a durable record — metric R-9
  - A-13 (metric) R-10: p95 latency of healthy targets while one target stalls within the stated latency target — one target stalled (timeouts) while others must keep meeting their latency target — metric R-10
  - A-14 (metric) R-11: required metrics exposed = all listed — load test at the stated rate; the stated percentile must meet the target — metric R-11
- **notes**: family: admin_api

### WP-7 — Health policy (S)

Implement Health policy: Evaluates per-target failure history against the disable policy and applies the consequence.

- **components**: C-14 · **implements**: I-14
- **depends on**: WP-1, WP-4, WP-5 · **satisfies**: R-7
- **write scope**: `app/policy.py`, `tests/test_policy.py`
- **acceptance**:
  - A-15 (test) unit tests of Health policy pass — `python -m pytest -q tests/test_policy.py`
- **notes**: family: health_policy

## Traceability

| requirement | priority | components | work packages | acceptance |
|---|---|---|---|---|
| R-1 | must | C-2, C-3, C-5, C-6, C-7, C-8, C-11, C-12, C-13, C-15 | WP-1, WP-2, WP-3, WP-4, WP-5, WP-6 | A-1, A-2, A-3, A-4, A-5, A-6, A-7, A-8, A-9, A-10, A-11, A-12, A-13, A-14 |
| R-2 | must | C-3, C-6, C-8, C-11, C-15 | WP-2, WP-3, WP-4, WP-5, WP-6 | A-6, A-7, A-8, A-9, A-10, A-11, A-12, A-13, A-14 |
| R-3 | must | C-2, C-6, C-16 | WP-1, WP-5, WP-6 | A-1, A-2, A-3, A-4, A-5, A-9, A-10, A-11, A-12, A-13, A-14 |
| R-4 | must | C-2, C-5, C-6, C-7, C-12, C-13 | WP-1, WP-3, WP-5, WP-6 | A-1, A-2, A-3, A-4, A-5, A-7, A-9, A-10, A-11, A-12, A-13, A-14 |
| R-5 | must | C-2, C-3, C-5, C-6, C-7, C-8, C-12, C-13 | WP-1, WP-2, WP-3, WP-4, WP-5, WP-6 | A-1, A-2, A-3, A-4, A-5, A-6, A-7, A-8, A-9, A-10, A-11, A-12, A-13, A-14 |
| R-6 | must | C-2, C-5, C-6, C-7, C-11, C-12, C-13, C-15 | WP-1, WP-3, WP-5, WP-6 | A-1, A-2, A-3, A-4, A-5, A-7, A-9, A-10, A-11, A-12, A-13, A-14 |
| R-7 | must | C-4, C-6, C-9, C-14 | WP-4, WP-5, WP-7 | A-8, A-9, A-15 |
| R-8 | should | C-2, C-10, C-12, C-15, C-16 | WP-1, WP-6 | A-1, A-2, A-3, A-4, A-5, A-10, A-11, A-12, A-13, A-14 |
| R-9 | should | C-1, C-2, C-16 | WP-1, WP-6 | A-1, A-2, A-3, A-4, A-5, A-10, A-11, A-12, A-13, A-14 |
| R-10 | must | C-2, C-12 | WP-1, WP-6 | A-1, A-2, A-3, A-4, A-5, A-10, A-11, A-12, A-13, A-14 |
| R-11 | should | C-10, C-12, C-15, C-16 | WP-1, WP-6 | A-1, A-2, A-3, A-4, A-5, A-10, A-11, A-12, A-13, A-14 |
| R-12 | must | C-1, C-6 | WP-1, WP-5 | A-1, A-2, A-3, A-4, A-5, A-9 |
| R-13 | must | C-12, C-15, C-16 | WP-6 | A-10, A-11, A-12, A-13, A-14 |

## Conventions

- **language**: python
- **test**: `python -m pytest -q`
- **lint**: `ruff check .`
- Type hints on every public function; dataclasses or pydantic for records.
- No business logic in the HTTP layer.
- Every management route goes through the authentication middleware; no route is exempt without a decision.
- Every component logs one structured line per unit of work with the correlation id.
- No in-process state that a second instance would not see; instances are interchangeable.
- Prefer the boring option; a new piece of infrastructure needs a decision record.
- Python 3.12 as stated in the constraints.
- Stateless processes: configuration from the environment, no local files that a second instance would not see.

**Definition of done**

- Acceptance checks of the package pass.
- No file outside the write scope changed.
- Every public operation of the implemented interfaces exists with the declared inputs.
