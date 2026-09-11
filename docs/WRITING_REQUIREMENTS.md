# Writing requirements for `sekkei design`

The engine reads plain text or Markdown. It does not understand prose; it reads
**structure, modality and numbers**. Give it those and it does the rest.

## The template (`sekkei template`)

```markdown
# <System name>

<One or two sentences: who uses it, what problem it solves.>

## Functional
- <Actor> can <verb> <object> ... (one requirement per bullet; verbs like create/list/delete/search/export/rotate become operations)
- <What the system does>: numbers in the sentence become contract preconditions (retry schedule, limits, windows).

## Non-functional
- <Rate>: 1,000 requests/s sustained; 5,000 endpoints; 200,000 items.
- <Latency>: p95 under 300 ms for <operation>.
- <Durability/consistency>: no <thing> lost on crash; never double-applied.
- <Isolation/availability>: one slow <thing> must not delay others; 99.9 % monthly.
- <Operations>: metrics for Prometheus; structured logs; alert on <condition>.

## Constraints
- <Language and version>, <database/queue available>, <deployment: containers behind ingress / single binary / on-prem>.
- Team of <N>. <Single region>. <Standard library only>. <Authentication via OIDC provider>.

## Out of scope
- <Things the engine must not design for.>
```

## What each part does

| you write | the engine does |
|---|---|
| a `## Functional` / `Non-functional` / `Constraints` / `Out of scope` heading (or the bare word on its own line) | classifies every bullet under it; out-of-scope bullets become non-goals and never match a pattern |
| one bullet per requirement | one requirement entry, quoted verbatim, with a stable id |
| `must` / `never` / `at least once` — `should` — `may` / `optional` | priority must / should / could (bullets in Functional default to must) |
| an actor at the start (customers, staff, users, ops, internal services, the tool, …) | operations are derived only from sentences with an actor; "the system does X" sentences become contracts, not endpoints |
| numbers with units: `1,000 events/s`, `p95 under 5 s`, `300 ms`, `2 GB`, `99.9 %`, `5,000 endpoints`, `1 min, 5 min, 30 min` | metrics on non-functional requirements; preconditions on the contract that consumes them (retry schedule → scheduler, rotation window → secret store) |
| technology names: PostgreSQL, Redis, SQLite, Kafka/RabbitMQ/SQS, S3, Vault/KMS, OIDC/OAuth, containers/Kubernetes, serverless, "no database", "no network" | constraint tokens that rule options in or out of every decision and give the stated one a bonus |
| language names with versions (Python 3.12, TypeScript on Node 20, Go, Rust, Java, …) | file layout of every work package and the test commands |
| `team of 3`, `small team`, `single region` | the simplicity weight in every decision and the schedule estimate |
| words like webhook, deliver, retry, backoff, sign/HMAC/secret/rotate, publish/event, admin/manage, email/notify, audit/who did what, batch/nightly/export, search, upload, CLI/stdin/flags, websocket, payment, inference, cache, rate limit | capability patterns; each brings components, contracts, entities, flows, decision points and risks |

## Three sizes of input

**Minimal (a few lines).** The engine still produces a design; the review lists the
questions it would have asked and the assumptions it used instead:

```markdown
# Newsletter signup
- Visitors can subscribe with an email address and confirm through a link.
- Admins can export the subscriber list as CSV.
```

**Typical (a page).** See `examples/webhooks/requirements.md` — sections, one bullet
per requirement, numbers with units, a constraints block. This is the sweet spot.

**Long (a spec document).** Works; sentences outside the sections are treated as
requirements only if they carry modality (must/should/may). Use `## Out of scope` to
keep the engine from designing for what you excluded.

## What to do with the output

1. Read `REVIEW.md` first: the questions, the assumptions, anything unrecognised.
   Answer the questions by adding bullets to the requirements and run again — the
   design changes only where the answer matters.
2. `sekkei lint` is already clean. `sekkei plan` shows the waves.
3. `sekkei brief WP-1` and hand it to a coding agent; `sekkei accept` its report;
   `sekkei check --root .` once code exists.
