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
- Ops: metrics (queue depth, delivery success rate, attempt latency) exposed for
  Prometheus; structured logs.

Constraints
- Python 3.12, PostgreSQL available, Redis available. Single region. Team of 3.
- Must run as a set of stateless containers behind our existing ingress.
