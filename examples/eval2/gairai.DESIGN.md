# outside-bookings-system — design

Patients during outside mobile app from so that bookings.

_version 0.1.0 · schema sekkei/1_

## Goals

- Clients read and write domain resources over HTTP.
- The system notifies people through an external channel.
- Metrics, structured logs and health endpoints for operations.
- Callers are authenticated and authorized.
- Users search and filter records.
- Scheduled jobs process stored records in windows.
- Work runs on a schedule.
- People are notified by SMS.
- Changes are recorded append-only with the actor.
- Personal data is held and must be protected, exportable and deletable.
- Records flow to and from a system that already exists.

**Non-goals**

- Accounting invoices.
- Inpatient bookings.

## Requirements

| id | kind | priority | statement | metric |
|---|---|---|---|---|
| R-1 | functional | must | Patients departments choose doctors. The system can register, change and cancel available slots from appointments. | — |
| R-2 | functional | must | Staff can accept and register bookings patients. Staff can view bookings list the same day departments each. | — |
| R-3 | functional | must | Patients bookings the day before email or SMS receive reminders. | — |
| R-4 | functional | must | Doctors can view basic information name date of birth insurance number their own appointments schedule patients. | — |
| R-5 | functional | must | The system must generate slots departments each opening hours doctors shifts from weekly. | — |
| R-6 | functional | must | The system must change and record audit log bookings cancel who when rows. | — |
| R-7 | functional | must | The system must integrate confirmed bookings existing electronic health record system external services nightly. | — |
| R-8 | nonfunctional | must | The system must respond available slots search within 500 ms p95. | p95 latency <= 500 ms |
| R-9 | nonfunctional | must | Same must never be slots double-applied bookings. | lost or duplicate updates under concurrent writes to one record = 0 updates |
| R-10 | nonfunctional | must | The system must save patient records encrypted. The system can delete appi in accordance with on request. | retention/deletion rules exercised = all |
| R-11 | nonfunctional | must | Monthly availability at least 99.5 %. | ratio >= 99.5 % |
| R-12 | nonfunctional | must | 3000 requests/day bookings 20 requests/s peak. | sustained rate at 20 3000 requests /day |
| R-13 | constraint | must | The system can use Python 3.12 PostgreSQL. Team of 3. Containers single region. | — |
| R-14 | constraint | must | Patients authenticate existing patient portal OIDC. | — |
| R-15 | functional | must | Domain records are kept indefinitely; logs and audit history are retained for 1 year, after which a nightly job deletes them (assumed by the engine). | — |
| R-16 | functional | could | Every operation is scoped to the caller's own resources; an admin role may act on any resource (assumed by the engine). | — |
| R-17 | functional | must | Personal data is deleted on request and access to it is logged, under the regime the requirements name (assumed by the engine: regime named). | — |
| R-18 | nonfunctional | must | Records are 2 KB on average and at most 256 KB (assumed by the engine). | size at 2 KB <= 256 kb |
| R-19 | nonfunctional | should | Backups run daily with a recovery point of 24 h and a recovery time of 4 h (assumed by the engine). | time at 4 h 24 h |
| R-20 | nonfunctional | should | External calls time out after 10 s; failures are retried 5 times with exponential backoff and work waits durably meanwhile (assumed by the engine). | time at 5 10 s |
| R-21 | nonfunctional | must | An alert is raised when the error rate exceeds 1 % for 5 minutes or the queue depth grows for 10 minutes (assumed by the engine). | ratio at 5 minutes, 10 minutes 1 % |
| R-22 | constraint | must | The existing system named in the requirements stays in place; integration, not migration (assumed by the engine). | — |
| R-23 | constraint | must | Use existing infrastructure only; no new managed services (assumed by the engine). | — |

## Components

```mermaid
graph LR
  C_1[("C-1 Store")]
  C_2[["C-2 Email provider"]]
  C_3[["C-3 SMS provider"]]
  C_4[("C-4 Audit log")]
  C_5[["C-5 Existing system"]]
  C_6["C-6 Domain core"]
  C_7["C-7 Notifier"]
  C_8["C-8 Observability"]
  C_9["C-9 Authentication"]
  C_10["C-10 Search index"]
  C_11["C-11 Scheduler"]
  C_12["C-12 Batch job"]
  C_13["C-13 Legacy system adapter"]
  C_14["C-14 Data protection"]
  C_15["C-15 Public HTTP API"]
  C_6 -->|I-1| C_1
  C_6 -->|I-8| C_8
  C_6 -->|I-4| C_4
  C_6 -->|I-7| C_7
  C_7 -->|I-2| C_2
  C_7 -->|I-8| C_8
  C_7 -->|I-3| C_3
  C_9 -->|I-1| C_1
  C_10 -->|I-1| C_1
  C_11 -->|I-8| C_8
  C_12 -->|I-1| C_1
  C_12 -->|I-11| C_11
  C_12 -->|I-8| C_8
  C_12 -->|I-6| C_6
  C_13 -->|I-5| C_5
  C_13 -->|I-6| C_6
  C_14 -->|I-1| C_1
  C_14 -->|I-4| C_4
  C_15 -->|I-6| C_6
  C_15 -->|I-8| C_8
  C_15 -->|I-9| C_9
  C_15 -->|I-10| C_10
```

### C-1 — Store

- **kind**: datastore · **path**: `app/store.py`
- **responsibility**: Owns persistence of the domain entities: durable writes, reads, listing, and the schema/migrations.
- **provides**: I-1
- **requires**: —
- **satisfies**: R-9, R-10, R-13, R-20

### C-2 — Email provider

- **kind**: external
- **responsibility**: External email delivery service.
- **provides**: I-2
- **requires**: —
- **satisfies**: R-3

### C-3 — SMS provider

- **kind**: external
- **responsibility**: External SMS gateway.
- **provides**: I-3
- **requires**: —
- **satisfies**: R-3

### C-4 — Audit log

- **kind**: datastore · **path**: `app/audit.py`
- **responsibility**: Append-only record of who did what to which resource, queryable by resource and actor.
- **provides**: I-4
- **requires**: —
- **satisfies**: R-6, R-10, R-17

### C-5 — Existing system

- **kind**: external
- **responsibility**: The system of record that already exists (ERP/CRM/database); outside our control.
- **provides**: I-5
- **requires**: —
- **satisfies**: R-7

### C-6 — Domain core

- **kind**: module · **path**: `app/core.py`
- **responsibility**: Business rules and validation for the domain entities; the only module that changes state through the store.
- **provides**: I-6
- **requires**: I-1, I-8, I-4, I-7
- **satisfies**: R-1, R-2, R-7, R-9, R-13, R-22, R-23

### C-7 — Notifier

- **kind**: module · **path**: `app/notifier.py`
- **responsibility**: Sends operator/customer notifications through the configured channel with templating and rate limiting.
- **provides**: I-7
- **requires**: I-2, I-8, I-3
- **satisfies**: R-3

### C-8 — Observability

- **kind**: module · **path**: `app/observability.py`
- **responsibility**: Metrics registry and exposition, structured logging, health/readiness endpoints.
- **provides**: I-8
- **requires**: —
- **satisfies**: R-11, R-21

### C-9 — Authentication

- **kind**: module · **path**: `app/auth.py`
- **responsibility**: Authenticates callers and resolves them to a principal and scope; enforces authorization for management operations.
- **provides**: I-9
- **requires**: I-1
- **satisfies**: R-14, R-16

### C-10 — Search index

- **kind**: module · **path**: `app/search.py`
- **responsibility**: Full-text and filtered queries over the indexed entities.
- **provides**: I-10
- **requires**: I-1
- **satisfies**: R-8, R-12

### C-11 — Scheduler

- **kind**: job · **path**: `app/scheduler.py`
- **responsibility**: Computes when deferred work runs next (backoff schedules, periodic jobs) and promotes due work.
- **provides**: I-11
- **requires**: I-8
- **satisfies**: R-3, R-4, R-5, R-7, R-15

### C-12 — Batch job

- **kind**: job · **path**: `app/batch.py`
- **responsibility**: Scheduled processing over stored records: extract, transform, aggregate, write results.
- **provides**: I-12
- **requires**: I-1, I-11, I-8, I-6
- **satisfies**: R-5, R-7, R-15

### C-13 — Legacy system adapter

- **kind**: module · **path**: `app/legacy_adapter.py`
- **responsibility**: Anti-corruption layer in front of the existing system: translates its records and calls into our model, isolates its quirks and outages.
- **provides**: I-13
- **requires**: I-5, I-6
- **satisfies**: R-7

### C-14 — Data protection

- **kind**: job · **path**: `app/data_protection.py`
- **responsibility**: Retention schedules, deletion and export requests for a person's data, consent records; runs the deletions and proves them.
- **provides**: I-14
- **requires**: I-1, I-4
- **satisfies**: R-10, R-17

### C-15 — Public HTTP API

- **kind**: service · **path**: `app/surface_api.py`
- **responsibility**: Translates HTTP requests into core calls: routing, request validation, error mapping, JSON.
- **provides**: I-15
- **requires**: I-6, I-8, I-9, I-10
- **satisfies**: R-1, R-2, R-8, R-12, R-13, R-18, R-19

**Layers** (each layer depends only on earlier ones):

0. C-1, C-2, C-3, C-4, C-5, C-8
1. C-10, C-11, C-14, C-7, C-9
2. C-6
3. C-12, C-13, C-15

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

### I-2 — Email provider interface

- **kind**: http · **owner**: C-2 · **stability**: stable
- Provided by Email provider. External; contract is theirs.

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `send` | `to`: str, `subject`: str, `body`: str | provider message id | — | — |

### I-3 — SMS provider interface

- **kind**: http · **owner**: C-3 · **stability**: stable
- Provided by SMS provider. External; contract is theirs.

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `send` | `to`: str, `text`: str | provider message id | — | — |

### I-4 — Audit log interface

- **kind**: class · **owner**: C-4 · **stability**: stable
- Provided by Audit log. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `append` | `actor`: str, `action`: str, `resource`: str, `details`: dict | None | — | — |
| `query` | `resource`: str \| None, `actor`: str \| None, `page`: Page | entries | — | — |

### I-5 — Existing system interface

- **kind**: http · **owner**: C-5 · **stability**: stable
- Provided by Existing system. External; contract is theirs.

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `read/write` | — | records | unavailable | — |

### I-6 — Domain core interface

- **kind**: module · **owner**: C-6 · **stability**: draft
- Provided by Domain core. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `set_doctors` | `doctors`: Doctors \| id | Doctors \| None | ValidationError, NotFound | — |
| | from R-1: Patients departments choose doctors. The system can register, change and cancel available | | | |
| `register_slots` | `slots`: Slots \| id | Slots \| None | ValidationError, NotFound | — |
| | from R-1: Patients departments choose doctors. The system can register, change and cancel available | | | |
| `update_slots` | `slots`: Slots \| id | Slots \| None | ValidationError, NotFound | — |
| | from R-1: Patients departments choose doctors. The system can register, change and cancel available | | | |
| `cancel_slots` | `slots`: Slots \| id | Slots \| None | ValidationError, NotFound | — |
| | from R-1: Patients departments choose doctors. The system can register, change and cancel available | | | |
| `accept_patients` | `patients`: Patients \| id | Patients \| None | ValidationError, NotFound | — |
| | from R-2: Staff can accept and register bookings patients. Staff can view bookings list the same day | | | |
| `register_patients` | `patients`: Patients \| id | Patients \| None | ValidationError, NotFound | — |
| | from R-2: Staff can accept and register bookings patients. Staff can view bookings list the same day | | | |
| `get_bookings` | `bookings`: Bookings \| id | Bookings \| None | ValidationError, NotFound | — |
| | from R-2: Staff can accept and register bookings patients. Staff can view bookings list the same day | | | |
| `list_departments` | `departments`: Departments \| id | Departments \| None | ValidationError, NotFound | — |
| | from R-2: Staff can accept and register bookings patients. Staff can view bookings list the same day | | | |
| `receive_reminders` | `reminders`: Reminders \| id | Reminders \| None | ValidationError, NotFound | — |
| | from R-3: Patients bookings the day before email or SMS receive reminders. | | | |
| `get_information` | `information`: Information \| id | Information \| None | ValidationError, NotFound | — |
| | from R-4: Doctors can view basic information name date of birth insurance number their own appointme | | | |
| `schedule_patients` | `patients`: Patients \| id | Patients \| None | ValidationError, NotFound | — |
| | from R-4: Doctors can view basic information name date of birth insurance number their own appointme | | | |
| `generate_departments` | `departments`: Departments \| id | Departments \| None | ValidationError, NotFound | — |
| | from R-5: The system must generate slots departments each opening hours doctors shifts from weekly. | | | |
| `open_shifts` | `shifts`: Shifts \| id | Shifts \| None | ValidationError, NotFound | — |
| | from R-5: The system must generate slots departments each opening hours doctors shifts from weekly. | | | |
| `update_audit` | `audit`: Audit \| id | Audit \| None | ValidationError, NotFound | — |
| | from R-6: The system must change and record audit log bookings cancel who when rows. | | | |
| `record_audit` | `audit`: Audit \| id | Audit \| None | ValidationError, NotFound | — |
| | from R-6: The system must change and record audit log bookings cancel who when rows. | | | |
| `log_bookings` | `bookings`: Bookings \| id | Bookings \| None | ValidationError, NotFound | — |
| | from R-6: The system must change and record audit log bookings cancel who when rows. | | | |
| `cancel_rows` | `rows`: Rows \| id | Rows \| None | ValidationError, NotFound | — |
| | from R-6: The system must change and record audit log bookings cancel who when rows. | | | |
| `record_external` | `external`: External \| id | External \| None | ValidationError, NotFound | — |
| | from R-7: The system must integrate confirmed bookings existing electronic health record system exte | | | |
| `record_kept` | `kept`: Kept \| id | Kept \| None | ValidationError, NotFound | stated values: 1 year (R-15) |
| | from R-15: Domain records are kept indefinitely; logs and audit history are retained for 1 year, afte | | | |
| `log_history` | `history`: History \| id | History \| None | ValidationError, NotFound | stated values: 1 year (R-15) |
| | from R-15: Domain records are kept indefinitely; logs and audit history are retained for 1 year, afte | | | |
| `delete_job` | `job`: Job \| id | Job \| None | ValidationError, NotFound | stated values: 1 year (R-15) |
| | from R-15: Domain records are kept indefinitely; logs and audit history are retained for 1 year, afte | | | |

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

### I-10 — Search index interface

- **kind**: module · **owner**: C-10 · **stability**: draft
- Provided by Search index. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `index` | `entity`: Entity, `record`: dict | None | — | — |
| `query` | `text`: str, `filters`: dict, `page`: Page | hits | — | — |

### I-11 — Scheduler interface

- **kind**: module · **owner**: C-11 · **stability**: draft
- Provided by Scheduler. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `next_attempt` | `attempt`: int, `retry_after`: timedelta \| None | datetime \| None | — | — |
| | None when attempts are exhausted | | | |
| `promote_due` | `now`: datetime | int moved | — | — |

### I-12 — Batch job interface

- **kind**: module · **owner**: C-12 · **stability**: draft
- Provided by Batch job. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `run` | `window`: DateRange | JobReport | JobError | stated values: 1 year (R-15) |

### I-13 — Legacy system adapter interface

- **kind**: module · **owner**: C-13 · **stability**: draft
- Provided by Legacy system adapter. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `pull` | `since`: datetime | list[record] | LegacyUnavailableError | — |
| | incremental read; idempotent on re-run | | | |
| `push` | `record`: record | legacy id | LegacyRejectedError | mapping stored so the record is not pushed twice |

### I-14 — Data protection interface

- **kind**: module · **owner**: C-14 · **stability**: draft
- Provided by Data protection. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `request_deletion` | `subject_id`: str, `requested_by`: Principal | DeletionRequest | — | request recorded with a deadline |
| `run_due` | `now`: datetime | int completed | — | — |
| | deletes or anonymises across every store; audit entry per subject | | | |
| `export` | `subject_id`: str | archive | — | — |
| | everything held about the subject, machine readable | | | |

### I-15 — Public HTTP API interface

- **kind**: http · **owner**: C-15 · **stability**: draft
- Provided by Public HTTP API. 

| operation | inputs | output | errors | pre / post |
|---|---|---|---|---|
| `POST /slots` | `body`: slots fields | 201 {slots id} | 400 invalid body, 401 unauthenticated, 409 conflict | — |
| | from R-1: Patients departments choose doctors. The system can register, change and cancel available | | | |
| `PUT /slots/{id}` | `id`: str, `body`: slots fields | 200 slots | 400 invalid body, 401 unauthenticated, 404 unknown id | — |
| | from R-1: Patients departments choose doctors. The system can register, change and cancel available | | | |
| `POST /slots/{id}/cancel` | `id`: str | 202 cancel accepted | 401 unauthenticated, 404 unknown id, 409 not applicable in current state | — |
| | from R-1: Patients departments choose doctors. The system can register, change and cancel available | | | |
| `POST /patients/{id}/accept` | `id`: str | 202 accept accepted | 401 unauthenticated, 404 unknown id, 409 not applicable in current state | — |
| | from R-2: Staff can accept and register bookings patients. Staff can view bookings list the same day | | | |
| `POST /patients` | `body`: patients fields | 201 {patients id} | 400 invalid body, 401 unauthenticated, 409 conflict | — |
| | from R-2: Staff can accept and register bookings patients. Staff can view bookings list the same day | | | |
| `GET /bookings/{id}` | `id`: str | 200 bookings | 401 unauthenticated, 404 unknown id | — |
| | from R-2: Staff can accept and register bookings patients. Staff can view bookings list the same day | | | |
| `GET /departments` | `filter`: query, `page`: cursor | 200 [departments], next cursor | 401 unauthenticated | — |
| | from R-2: Staff can accept and register bookings patients. Staff can view bookings list the same day | | | |
| `GET /informations/{id}` | `id`: str | 200 information | 401 unauthenticated, 404 unknown id | — |
| | from R-4: Doctors can view basic information name date of birth insurance number their own appointme | | | |

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

### E-3 — JobRun (owner C-1)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `job` | str |  |
| `window_start` | timestamp |  |
| `window_end` | timestamp |  |
| `status` | enum |  |
| `report` | json |  |

### E-4 — AuditEntry (owner C-4)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `actor` | str |  |
| `action` | str |  |
| `resource` | str | indexed |
| `at` | timestamp |  |

### E-5 — DeletionRequest (owner C-1)

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `subject_id` | uuid | indexed |
| `requested_at` | timestamp |  |
| `deadline` | timestamp | statutory window |
| `completed_at` | timestamp |  |
| `proof` | json | what was deleted where |

### E-6 — Booking (owner C-1)

Domain entity named in the requirements ('booking'); confirm the fields.

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `created_at` | timestamp |  |

### E-7 — Slot (owner C-1)

Domain entity named in the requirements ('slot'); confirm the fields.

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `created_at` | timestamp |  |

### E-8 — Department (owner C-1)

Domain entity named in the requirements ('department'); confirm the fields.

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `created_at` | timestamp |  |

### E-9 — Appointment (owner C-1)

Domain entity named in the requirements ('appointment'); confirm the fields.

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `created_at` | timestamp |  |

### E-10 — External (owner C-1)

Domain entity named in the requirements ('external'); confirm the fields.

| field | type | constraints |
|---|---|---|
| `id` | uuid | primary key |
| `created_at` | timestamp |  |

## Flows

### F-1 — Serve a request

_Trigger:_ client calls the API

1. C-15 → C-6 via I-6: validate and apply
2. C-6 → C-1 via I-1: read/write

```mermaid
sequenceDiagram
  participant C_15 as C-15 Public HTTP API
  participant C_6 as C-6 Domain core
  participant C_1 as C-1 Store
  Note over C_15: client calls the API
  C_15->>C_6: I-6 validate and apply
  C_6->>C_1: I-1 read/write
```

### F-2 — Run the batch job

_Trigger:_ schedule fires

1. C-12 → C-1 via I-1: read the window of records
2. C-12 → C-1 via I-1: write results and the job report

```mermaid
sequenceDiagram
  participant C_12 as C-12 Batch job
  participant C_1 as C-1 Store
  Note over C_12: schedule fires
  C_12->>C_1: I-1 read the window of records
  C_12->>C_1: I-1 write results and the job report
```

### F-3 — Exchange records with the existing system

_Trigger:_ schedule fires

1. C-13 → C-5 via I-5: pull(since)
2. C-13 → C-6 via I-6: translated records applied
3. C-13 → C-6 via I-6: records changed since the last run are read
4. C-13 → C-5 via I-5: push; mapping stored

```mermaid
sequenceDiagram
  participant C_13 as C-13 Legacy system adapter
  participant C_5 as C-5 Existing system
  participant C_6 as C-6 Domain core
  Note over C_13: schedule fires
  C_13->>C_5: I-5 pull(since)
  C_13->>C_6: I-6 translated records applied
  C_13->>C_6: I-6 records changed since the last run are read
  C_13->>C_5: I-5 push; mapping stored
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

**Rationale.** Scored against the active qualities; decided by performance (weight 1.0), availability (weight 1.0). REST/JSON over HTTP: 1.41; gRPC: 1.29; GraphQL: 1.15

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

**Rationale.** Scored against the active qualities; decided by performance (weight 1.0), availability (weight 1.0). PostgreSQL: 3.13; In-memory: 1.49; SQLite: unavailable (ruled out by containers); Files: unavailable (ruled out by containers). stated in the constraints

**Consequences.** Not choosing 'In-memory' gives up: fastest, trivial.

_Affects:_ C-1

### D-3 — Caller authentication (accepted)

**Context.** Management operations must be attributable to a customer or operator.

- ✘ **API keys per customer, hashed at rest, sent as a bearer token**
  - + simple
  - + scriptable
  - − no delegation or expiry unless added
- ✔ **OAuth2 / OIDC with the platform's identity provider**
  - + single sign-on
  - + expiry and scopes
  - − integration effort
- ✘ **Mutual TLS**
  - + strong
  - + no secrets in headers
  - − certificate lifecycle for every customer

**Rationale.** Scored against the active qualities; decided by performance (weight 1.0), availability (weight 1.0). OAuth2 / OIDC with the platform's identity provi: 2.22; API keys per customer, hashed at rest, sent as a: 1.37; Mutual TLS: 1.09. stated in the constraints

**Consequences.** Not choosing 'API keys per customer, hashed at rest, sent as a' gives up: simple, scriptable. Not choosing 'Mutual TLS' gives up: strong, no secrets in headers.

_Affects:_ C-9

### D-4 — Process topology (accepted)

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

**Rationale.** Scored against the active qualities; decided by performance (weight 1.0), availability (weight 1.0). One image, role by flag: `api` and `worker` proc: 1.72; Single process with background threads: 1.41; Separate services per concern: 1.29

**Consequences.** Not choosing 'Single process with background threads' gives up: one deployable. Not choosing 'Separate services per concern' gives up: clear ownership.

_Affects:_ C-15, C-11

### D-5 — Protection of personal data (accepted)

**Context.** Personal data is stored and must be protected and deletable.

- ✘ **Field-level encryption for identifiers and sensitive fields with a key outside the database; pseudonymous ids elsewhere**
  - + a dump does not expose people
  - + deletion = key destruction where fields are only encrypted
  - − cannot index encrypted fields
  - − key management
- ✔ **Encryption at rest by the platform plus strict access control and audit**
  - + no application changes
  - + indexes work
  - − anyone with database access sees everything
- ✘ **Separate personal-data store with tokenised references**
  - + blast radius contained
  - + deletion in one place
  - − joins across two stores
  - − a second store

**Rationale.** Scored against the active qualities; decided by performance (weight 1.0), availability (weight 1.0). Encryption at rest by the platform plus strict a: 1.78; Field-level encryption for identifiers and sensi: 1.59; Separate personal-data store with tokenised refe: 1.45

**Consequences.** Not choosing 'Field-level encryption for identifiers and sensi' gives up: a dump does not expose people, deletion = key destruction where fields are only encrypted. Not choosing 'Separate personal-data store with tokenised refe' gives up: blast radius contained, deletion in one place.

_Affects:_ C-14, C-1

### D-6 — Integration with the existing system (accepted)

**Context.** Records must flow between the new system and the one that already exists.

- ✘ **API façade (anti-corruption layer) calling the legacy system's interfaces, with a translation layer and retries**
  - + legacy schema never leaks in
  - + quirks isolated in one module
  - − depends on the legacy system's uptime
- ✔ **Scheduled batch file exchange (CSV/fixed format) through a shared drop**
  - + works with any system
  - + no live coupling
  - − latency of the schedule
  - − reconciliation of partial files
- ✘ **Change data capture from the legacy database**
  - + near real time
  - + no legacy code changes
  - − coupled to the legacy schema
  - − capture tooling to operate

**Rationale.** Scored against the active qualities; decided by performance (weight 1.0), availability (weight 1.0). Scheduled batch file exchange: 2.59; API façade: 1.63; Change data capture from the legacy database: 1.41. stated in the constraints

**Consequences.** Not choosing 'API façade' gives up: legacy schema never leaks in, quirks isolated in one module. Not choosing 'Change data capture from the legacy database' gives up: near real time, no legacy code changes.

_Affects:_ C-13

### D-7 — Concurrency control for conflicting writes (accepted)

**Context.** Two callers may change the same record at the same time and the result must be consistent.

- ✔ **Optimistic concurrency: version column checked on every update; conflict returns 409 and the caller retries**
  - + no locks held across requests
  - + works with stateless instances
  - − callers must handle 409
- ✘ **Row locks inside a short transaction (SELECT ... FOR UPDATE)**
  - + simple mental model
  - + no client retry
  - − lock waits under contention
  - − needs a transactional store
- ✘ **Last write wins**
  - + nothing to implement
  - − lost updates

**Rationale.** Scored against the active qualities; decided by performance (weight 1.0), availability (weight 1.0). Optimistic concurrency: version column checked o: 1.65; Row locks inside a short transaction: 1.63; Last write wins: 1.44

**Consequences.** Not choosing 'Row locks inside a short transaction' gives up: simple mental model, no client retry. Not choosing 'Last write wins' gives up: nothing to implement.

_Affects:_ C-1, C-6

### D-8 — Redundancy for the availability target (accepted)

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

**Rationale.** Scored against the active qualities; decided by performance (weight 1.0), availability (weight 1.0). Two or more interchangeable instances per role b: 1.42; Single instance with health-based restart: 1.26; Active-active across two regions: unavailable (ruled out by single_region)

**Consequences.** Not choosing 'Single instance with health-based restart' gives up: simplest, cheapest.

_Affects:_ C-15

### D-9 — Assumed answer: load (Q-payload) (proposed)

**Context.** The requirements do not say. Question: Q-payload. No evidence in the text; engine default.

- ✔ **2 KB / 256 KB**
- ✘ **16 KB / 1 MB**
- ✘ **256 bytes / 4 KB**

**Rationale.** Typical JSON record sizes; the maximum bounds request bodies.

**Consequences.** If the real answer differs: State the sizes; storage growth and body limits change.

_Affects:_ C-15

### D-10 — Assumed answer: data (Q-retention) (proposed)

**Context.** The requirements do not say. Question: Q-retention. No evidence in the text; engine default.

- ✔ **indefinite / 1 year**
- ✘ **90 days / 1 year**
- ✘ **30 days / 90 days**

**Rationale.** Deleting domain data is never a safe default; bounded retention for logs and history limits growth and satisfies most data-minimisation rules.

**Consequences.** If the real answer differs: State the retention per record class; the deletion job and capacity change.

_Affects:_ C-12, C-1

### D-11 — Assumed answer: data (Q-backup) (proposed)

**Context.** The requirements do not say. Question: Q-backup. No evidence in the text; engine default.

- ✔ **daily / 24 h / 4 h**
- ✘ **hourly / 1 h / 1 h**
- ✘ **none**

**Rationale.** The store's own daily backup is the cheapest credible baseline.

**Consequences.** If the real answer differs: State RPO/RTO; the store decision and a restore drill change.

_Affects:_ C-1

### D-12 — Assumed answer: data (Q-migration) (proposed)

**Context.** The requirements do not say. Question: Q-migration. Evidence: legacy_integration pattern.

- ✔ **integrate, no migration**
- ✘ **one-shot import**
- ✘ **gradual cut-over**

**Rationale.** The text names an existing system and describes an exchange with it.

**Consequences.** If the real answer differs: State whether data moves; a migration package and risk are added.

_Affects:_ C-13

### D-13 — Assumed answer: security (Q-authz) (proposed)

**Context.** The requirements do not say. Question: Q-authz. No evidence in the text; engine default.

- ✔ **owner-scoped + admin role**
- ✘ **flat (everyone sees everything)**
- ✘ **role matrix per resource**

**Rationale.** Ownership scoping is the minimum that prevents cross-tenant access.

**Consequences.** If the real answer differs: State the roles; core operations and acceptance checks change.

_Affects:_ C-6, C-9

### D-14 — Assumed answer: resilience (Q-external) (proposed)

**Context.** The requirements do not say. Question: Q-external. No evidence in the text; engine default.

- ✔ **10 s / 5 retries / queue**
- ✘ **fail fast, no retry**
- ✘ **30 s / unlimited retries**

**Rationale.** Bounded retries with a durable queue keep the system responsive during a one-hour outage.

**Consequences.** If the real answer differs: State the policy; the outbound client and scheduler contracts change.

_Affects:_ C-11

### D-15 — Assumed answer: compliance (Q-compliance) (proposed)

**Context.** The requirements do not say. Question: Q-compliance. Evidence: compliance_data pattern.

- ✔ **named regime + deletion + audit**
- ✘ **no regime**
- ✘ **HIPAA/PCI controls**

**Rationale.** The requirements name a data-protection regime or a deletion right.

**Consequences.** If the real answer differs: State the statutory deadline; the deletion job's deadline changes.

_Affects:_ C-14, C-4

### D-16 — Assumed answer: operations (Q-alerting) (proposed)

**Context.** The requirements do not say. Question: Q-alerting. No evidence in the text; engine default.

- ✔ **error rate + queue growth**
- ✘ **none**
- ✘ **per-endpoint SLO alerts**

**Rationale.** Two alerts catch most incidents without paging on noise.

**Consequences.** If the real answer differs: State the rules and the on-call; observability conventions change.

_Affects:_ C-8

### D-17 — Assumed answer: cost (Q-budget) (proposed)

**Context.** The requirements do not say. Question: Q-budget. No evidence in the text; engine default.

- ✔ **existing only**
- ✘ **managed services allowed**
- ✘ **strict monthly cap**

**Rationale.** The cheapest assumption; every decision already prefers the option needing no new infrastructure.

**Consequences.** If the real answer differs: State the budget; options adding infrastructure become available.

## Risks

| id | risk | likelihood | impact | mitigation |
|---|---|---|---|---|
| K-1 | Payloads or uploads without size limits exhaust memory or disk. | medium | medium | Enforce size limits at the surface; reject early with a clear error. |
| K-2 | Entities evolve; migrations run against live data. | medium | medium | Versioned migrations applied before deploy; additive changes first, removals one release later. |
| K-3 | A widespread failure disables many targets and emails every owner at once. | low | medium | Rate-limit notifications per owner and batch them. |
| K-4 | Per-target labels on metrics explode cardinality. | medium | low | Label by outcome and partition class, not by target id; expose per-target detail through the API instead. |
| K-5 | A management operation reachable without authentication. | low | high | Authenticate in one middleware for every management route; test every route unauthenticated. |
| K-6 | Personal data is copied into logs, reports and backups where deletion cannot reach it. | high | high | Log only pseudonymous ids; reports carry aggregates or pseudonyms; deletion covers backups by expiry. |
| K-7 | The legacy system's schema or outages leak into the new domain. | medium | medium | All translation in the adapter; the core never sees legacy types; the adapter degrades to read-only when the legacy system is down. |
| K-8 | Parts of the requirements were not recognised by the catalogue and received a generic decomposition. | medium | medium | Review the components marked generic; refine responsibilities and interfaces before briefing. |
| K-9 | [tampering] Store: Injection through query construction. | medium | medium | Parameterised queries only; no string-built SQL. Check: static check for string-formatted SQL finds nothing |
| K-10 | [information_disclosure] Store: Backups and dumps contain everything. | medium | high | Encrypt backups; restrict who can take them. Check: backup file is not readable without the key |
| K-11 | [denial_of_service] Notifier: Notification storms and template injection. | medium | medium | Rate-limit per recipient; escape template context. Check: 1,000 failures produce one digest per owner |
| K-12 | [spoofing] Authentication: Credential stuffing or leaked keys. | medium | medium | Hash keys at rest; allow revocation; rate-limit failures. Check: revoked key is rejected within seconds; brute force is throttled |
| K-13 | [elevation] Authentication: A caller acts on another tenant's resources. | medium | high | Every core operation takes the principal and checks ownership. Check: cross-tenant request returns 404/403 for every operation |
| K-14 | [spoofing] Legacy system adapter: The adapter trusts anything that looks like the legacy system. | medium | medium | Authenticate the legacy endpoint (mTLS or credentials); pin its address. Check: connection to an impostor host fails |
| K-15 | [tampering] Legacy system adapter: Malformed legacy records corrupt the domain. | medium | medium | Validate and translate every record; quarantine rejects with a report. Check: a malformed record is quarantined, not applied |
| K-16 | [repudiation] Data protection: A deletion cannot be proven later. | medium | medium | Record what was deleted where, with timestamps, in the audit log. Check: each completed request has a proof entry |
| K-17 | [information_disclosure] Data protection: An export goes to the wrong person. | medium | high | Exports are delivered only to the verified subject or an authorised operator; time-limited links. Check: export link expires and is bound to the requester |
| K-18 | [spoofing] Public HTTP API: Requests without a verified caller identity reach domain operations. | medium | medium | Authenticate every route in one middleware; deny by default. Check: every route returns 401 without credentials |
| K-19 | [tampering] Public HTTP API: Malformed or oversized bodies reach the core. | medium | medium | Schema-validate and size-limit at the surface; reject before parsing fully. Check: fuzz the body; oversize returns 413 |
| K-20 | [denial_of_service] Public HTTP API: A single caller saturates the service. | medium | medium | Per-caller rate limit and request timeouts. Check: burst from one key returns 429; others unaffected |
| K-21 | [information_disclosure] Public HTTP API: Stack traces or internal ids leak in error responses. | medium | high | Map exceptions to fixed error shapes; log details server-side only. Check: no traceback text in any 4xx/5xx body |

## Work packages

```mermaid
graph LR
  WP_1["WP-1 Audit log (S)"]
  WP_2["WP-2 Store + Observability (M)"]
  WP_3["WP-3 Data protection (S)"]
  WP_4["WP-4 Authentication + Scheduler (M)"]
  WP_5["WP-5 Notifier (S)"]
  WP_6["WP-6 Search index (S)"]
  WP_7["WP-7 Domain core (S)"]
  WP_8["WP-8 Batch job (S)"]
  WP_9["WP-9 Public HTTP API (S)"]
  WP_10["WP-10 Legacy system adapter (S)"]
  WP_1 --> WP_3
  WP_2 --> WP_3
  WP_2 --> WP_4
  WP_2 --> WP_5
  WP_2 --> WP_6
  WP_1 --> WP_7
  WP_2 --> WP_7
  WP_5 --> WP_7
  WP_2 --> WP_8
  WP_4 --> WP_8
  WP_7 --> WP_8
  WP_2 --> WP_9
  WP_4 --> WP_9
  WP_6 --> WP_9
  WP_7 --> WP_9
  WP_7 --> WP_10
```

**Waves** (packages in one wave may run in parallel):

1. WP-1, WP-2
2. WP-3, WP-4, WP-5, WP-6
3. WP-7
4. WP-10, WP-8, WP-9

_Critical path (12 person-days):_ WP-2 → WP-4 → WP-9

### WP-1 — Audit log (S)

Implement Audit log: Append-only record of who did what to which resource, queryable by resource and actor.

- **components**: C-4 · **implements**: I-4
- **depends on**: — · **satisfies**: R-6, R-10, R-17
- **write scope**: `app/audit.py`, `tests/test_audit.py`
- **acceptance**:
  - A-1 (test) unit tests of Audit log pass — `python -m pytest -q tests/test_audit.py`
  - A-2 (metric) R-10: retention/deletion rules exercised = all — data deletion and retention rules are exercised end to end — metric R-10
- **notes**: family: audit_log

### WP-2 — Store + Observability (M)

Implement Store: Owns persistence of the domain entities: durable writes, reads, listing, and the schema/migrations; Observability: Metrics registry and exposition, structured logging, health/readiness endpoints.

- **components**: C-1, C-8 · **implements**: I-1, I-8
- **depends on**: — · **satisfies**: R-9, R-10, R-11, R-13, R-20, R-21
- **write scope**: `app/store.py`, `tests/test_store.py`, `app/observability.py`, `tests/test_observability.py`
- **acceptance**:
  - A-3 (test) unit tests of Store, Observability pass — `python -m pytest -q tests/test_store.py tests/test_observability.py`
  - A-4 (metric) R-9: lost or duplicate updates under concurrent writes to one record = 0 updates — concurrent-update test: N parallel writers to one record end in the consistent state with no lost update — metric R-9
  - A-5 (metric) R-10: retention/deletion rules exercised = all — data deletion and retention rules are exercised end to end — metric R-10
  - A-6 (metric) R-11: ratio >= 99.5 % — kill one instance under load; error rate stays within the target — metric R-11
- **notes**: family: infra

### WP-3 — Data protection (S)

Implement Data protection: Retention schedules, deletion and export requests for a person's data, consent records; runs the deletions and proves them.

- **components**: C-14 · **implements**: I-14
- **depends on**: WP-1, WP-2 · **satisfies**: R-10, R-17
- **write scope**: `app/data_protection.py`, `tests/test_data_protection.py`
- **acceptance**:
  - A-7 (test) unit tests of Data protection pass — `python -m pytest -q tests/test_data_protection.py`
  - A-8 (metric) R-10: retention/deletion rules exercised = all — data deletion and retention rules are exercised end to end — metric R-10
- **notes**: family: compliance_data

### WP-4 — Authentication + Scheduler (M)

Implement Authentication: Authenticates callers and resolves them to a principal and scope; enforces authorization for management operations; Scheduler: Computes when deferred work runs next (backoff schedules, periodic jobs) and promotes due work.

- **components**: C-9, C-11 · **implements**: I-9, I-11
- **depends on**: WP-2 · **satisfies**: R-3, R-4, R-5, R-7, R-14, R-15, R-16
- **write scope**: `app/auth.py`, `tests/test_auth.py`, `app/scheduler.py`, `tests/test_scheduler.py`
- **acceptance**:
  - A-9 (test) unit tests of Authentication, Scheduler pass — `python -m pytest -q tests/test_auth.py tests/test_scheduler.py`
- **notes**: family: infra

### WP-5 — Notifier (S)

Implement Notifier: Sends operator/customer notifications through the configured channel with templating and rate limiting.

- **components**: C-7 · **implements**: I-7
- **depends on**: WP-2 · **satisfies**: R-3
- **write scope**: `app/notifier.py`, `tests/test_notifier.py`
- **acceptance**:
  - A-10 (test) unit tests of Notifier pass — `python -m pytest -q tests/test_notifier.py`
- **notes**: family: notification

### WP-6 — Search index (S)

Implement Search index: Full-text and filtered queries over the indexed entities.

- **components**: C-10 · **implements**: I-10
- **depends on**: WP-2 · **satisfies**: R-8, R-12
- **write scope**: `app/search.py`, `tests/test_search.py`
- **acceptance**:
  - A-11 (test) unit tests of Search index pass — `python -m pytest -q tests/test_search.py`
  - A-12 (metric) R-8: p95 latency <= 500 ms — load test at the stated rate; the stated percentile must meet the target — metric R-8
  - A-13 (metric) R-12: sustained rate at 20 3000 requests /day — load test at the stated rate; the stated percentile must meet the target — metric R-12
- **notes**: family: search

### WP-7 — Domain core (S)

Implement Domain core: Business rules and validation for the domain entities; the only module that changes state through the store.

- **components**: C-6 · **implements**: I-6
- **depends on**: WP-1, WP-2, WP-5 · **satisfies**: R-1, R-2, R-7, R-9, R-13, R-22, R-23
- **write scope**: `app/core.py`, `tests/test_core.py`
- **acceptance**:
  - A-14 (test) unit tests of Domain core pass — `python -m pytest -q tests/test_core.py`
  - A-15 (metric) R-9: lost or duplicate updates under concurrent writes to one record = 0 updates — concurrent-update test: N parallel writers to one record end in the consistent state with no lost update — metric R-9
- **notes**: family: crud_api

### WP-8 — Batch job (S)

Implement Batch job: Scheduled processing over stored records: extract, transform, aggregate, write results.

- **components**: C-12 · **implements**: I-12
- **depends on**: WP-2, WP-4, WP-7 · **satisfies**: R-5, R-7, R-15
- **write scope**: `app/batch.py`, `tests/test_batch.py`
- **acceptance**:
  - A-16 (test) unit tests of Batch job pass — `python -m pytest -q tests/test_batch.py`
- **notes**: family: batch_pipeline

### WP-9 — Public HTTP API (S)

Implement Public HTTP API: Translates HTTP requests into core calls: routing, request validation, error mapping, JSON.

- **components**: C-15 · **implements**: I-15
- **depends on**: WP-2, WP-4, WP-6, WP-7 · **satisfies**: R-1, R-2, R-8, R-12, R-13, R-18, R-19
- **write scope**: `app/surface_api.py`, `tests/test_surface_api.py`
- **acceptance**:
  - A-17 (test) unit tests of Public HTTP API pass — `python -m pytest -q tests/test_surface_api.py`
  - A-18 (metric) R-8: p95 latency <= 500 ms — load test at the stated rate; the stated percentile must meet the target — metric R-8
  - A-19 (metric) R-12: sustained rate at 20 3000 requests /day — load test at the stated rate; the stated percentile must meet the target — metric R-12
- **notes**: family: crud_api

### WP-10 — Legacy system adapter (S)

Implement Legacy system adapter: Anti-corruption layer in front of the existing system: translates its records and calls into our model, isolates its quirks and outages.

- **components**: C-13 · **implements**: I-13
- **depends on**: WP-7 · **satisfies**: R-7
- **write scope**: `app/legacy_adapter.py`, `tests/test_legacy_adapter.py`
- **acceptance**:
  - A-20 (test) unit tests of Legacy system adapter pass — `python -m pytest -q tests/test_legacy_adapter.py`
- **notes**: family: legacy_integration

## Traceability

| requirement | priority | components | work packages | acceptance |
|---|---|---|---|---|
| R-1 | must | C-6, C-15 | WP-7, WP-9 | A-14, A-15, A-17, A-18, A-19 |
| R-2 | must | C-6, C-15 | WP-7, WP-9 | A-14, A-15, A-17, A-18, A-19 |
| R-3 | must | C-2, C-3, C-7, C-11 | WP-4, WP-5 | A-9, A-10 |
| R-4 | must | C-11 | WP-4 | A-9 |
| R-5 | must | C-11, C-12 | WP-4, WP-8 | A-9, A-16 |
| R-6 | must | C-4 | WP-1 | A-1, A-2 |
| R-7 | must | C-5, C-6, C-11, C-12, C-13 | WP-4, WP-7, WP-8, WP-10 | A-9, A-14, A-15, A-16, A-20 |
| R-8 | must | C-10, C-15 | WP-6, WP-9 | A-11, A-12, A-13, A-17, A-18, A-19 |
| R-9 | must | C-1, C-6 | WP-2, WP-7 | A-3, A-4, A-5, A-6, A-14, A-15 |
| R-10 | must | C-1, C-4, C-14 | WP-1, WP-2, WP-3 | A-1, A-2, A-3, A-4, A-5, A-6, A-7, A-8 |
| R-11 | must | C-8 | WP-2 | A-3, A-4, A-5, A-6 |
| R-12 | must | C-10, C-15 | WP-6, WP-9 | A-11, A-12, A-13, A-17, A-18, A-19 |
| R-13 | must | C-1, C-6, C-15 | WP-2, WP-7, WP-9 | A-3, A-4, A-5, A-6, A-14, A-15, A-17, A-18, A-19 |
| R-14 | must | C-9 | WP-4 | A-9 |
| R-15 | must | C-11, C-12 | WP-4, WP-8 | A-9, A-16 |
| R-16 | could | C-9 | WP-4 | A-9 |
| R-17 | must | C-4, C-14 | WP-1, WP-3 | A-1, A-2, A-7, A-8 |
| R-18 | must | C-15 | WP-9 | A-17, A-18, A-19 |
| R-19 | should | C-15 | WP-9 | A-17, A-18, A-19 |
| R-20 | should | C-1 | WP-2 | A-3, A-4, A-5, A-6 |
| R-21 | must | C-8 | WP-2 | A-3, A-4, A-5, A-6 |
| R-22 | must | C-6 | WP-7 | A-14, A-15 |
| R-23 | must | C-6 | WP-7 | A-14, A-15 |

## Conventions

- **language**: python
- **test**: `python -m pytest -q`
- **lint**: `ruff check .`
- Type hints on every public function; dataclasses or pydantic for records.
- No business logic in the HTTP layer.
- Every management route goes through the authentication middleware; no route is exempt without a decision.
- Every component logs one structured line per unit of work with the correlation id.
- Prefer the boring option; a new piece of infrastructure needs a decision record.
- Python 3.12 as stated in the constraints.
- Stateless processes: configuration from the environment, no local files that a second instance would not see.

**Definition of done**

- Acceptance checks of the package pass.
- No file outside the write scope changed.
- Every public operation of the implemented interfaces exists with the declared inputs.
