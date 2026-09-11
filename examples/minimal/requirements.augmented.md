# Newsletter signup

- Visitors can subscribe with an email address and confirm through a link sent by email.
- Admins can export the subscriber list as CSV.

## Functional (Assumed by the engine)
- Personal data is deleted on request within 30 days and access to it is logged (assumed by the engine).
- Records are retained for 90 days and audit history for 1 year, after which a nightly job deletes them (assumed by the engine).

## Non-functional (Assumed by the engine)
- The system sustains 100 requests/s with peaks of 1,000 requests/s (assumed by the engine).
- The system holds 10,000 records and serves 1,000 users in the first year (assumed by the engine).
- Records are 2 KB on average and at most 256 KB (assumed by the engine).
- Read operations complete within 300 ms p95 and writes within 1 s p95 (assumed by the engine).
- Availability of 99.9 % monthly; accepted work is delayed but never lost during an outage (assumed by the engine).
- Backups run daily with a recovery point of 24 h and a recovery time of 4 h (assumed by the engine).
- External calls time out after 10 s; failures are retried 5 times with exponential backoff and work waits durably meanwhile (assumed by the engine).

## Constraints (Assumed by the engine)
- Python 3.12 (assumed by the engine).
- PostgreSQL available (assumed by the engine).
- Deployed as stateless containers behind an ingress (assumed by the engine).
- Team of 2 (assumed by the engine).
- Authentication by API keys per customer (assumed by the engine).
- Use existing infrastructure only; no new managed services (assumed by the engine).
- No existing data or system to migrate from (assumed by the engine).
