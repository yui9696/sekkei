# Webhook delivery service — requirements

We run a SaaS. Customers register webhook endpoints; when things happen in our platform
(order.created, order.paid, refund.issued, ...) we must deliver a signed JSON event to
every endpoint subscribed to that event type.

Functional
- Customers manage endpoints via an admin HTTP API: create/list/delete endpoints, choose
  event types, rotate the signing secret.
- Internal services publish events through an internal API (HTTP or in-process call).
- Each event is delivered at least once to every matching endpoint. Deliveries are retried
  with exponential backoff (1 min, 5 min, 30 min, 2 h, 12 h; 5 attempts) on 5xx/timeout.
  4xx (except 429) is final failure. 429 honours Retry-After.
- Every delivery carries an HMAC-SHA256 signature over the body with the endpoint's
  current secret, plus a timestamp header; after rotation, both old and new secrets are
  valid for 24 h.
- Customers can see delivery attempts per event (status, response code, timestamps) and
  manually redeliver.
- Endpoints that fail continuously for 3 days are disabled automatically and the customer
  is notified by email.

Non-functional
- 1,000 events/s sustained publish rate, 5,000 endpoints; delivery latency p95 under 5 s
  for a healthy endpoint.
- No event lost on process crash (persist before ack).
- Per-endpoint isolation: one slow endpoint must not delay others.
- metrics (queue depth, delivery success rate, attempt latency) exposed for
  Prometheus; structured logs.

Constraints
- Python 3.12, PostgreSQL available, Redis available. Single region. Team of 3.
- Must run as a set of stateless containers behind our existing ingress.

## Functional (Assumed by the engine)
- Domain records are kept indefinitely; logs and audit history are retained for 1 year, after which a nightly job deletes them (assumed by the engine).
- Personal data is deleted on request within 30 days and access to it is logged (assumed by the engine).

## Non-functional (Assumed by the engine)
- Records are 2 KB on average and at most 256 KB (assumed by the engine).
- Availability of 99.9 % monthly; accepted work is delayed but never lost during an outage (assumed by the engine).
- Backups run daily with a recovery point of 24 h and a recovery time of 4 h (assumed by the engine).
- An alert is raised when the error rate exceeds 1 % for 5 minutes or the queue depth grows for 10 minutes (assumed by the engine).

## Constraints (Assumed by the engine)
- No existing data or system to migrate from (assumed by the engine).
- Authentication by API keys per customer (assumed by the engine).
- Use existing infrastructure only; no new managed services (assumed by the engine).
