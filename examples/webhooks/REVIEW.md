# Architecture review (engine)

What the engine could not do on its own, in order of importance.

## Decisions taken (scored trade-offs)

- D-1 API style: **REST/JSON over HTTP**
- D-2 Primary store: **PostgreSQL**
- D-3 Caller authentication: **API keys per customer, hashed at rest, sent as a bearer token**
- D-4 How producers publish: **HTTP publish endpoint with idempotency keys**
- D-5 Work queue technology: **PostgreSQL table with SELECT ... FOR UPDATE SKIP LOCKED**
- D-6 Where delayed retries wait: **not_before column on the work item; the scheduler promotes due rows**
- D-7 Process topology: **One image, role by flag: `api` and `worker` processes scale independently**
- D-8 Outbound request safety: **Resolve and block private/link-local ranges; pin the resolved IP; cap body size and redirects; per-request timeout**
- D-9 Storage of signing secrets: **Encrypted column (AES-GCM) with a key from the environment/KMS**
- D-10 Per-target isolation of outbound work: **Partition the queue by target; each lease takes one partition with a per-partition concurrency cap**

## Notes

- 16 components for a team of 3; consider merging adjacent layers.

Every requirement was recognised and every active quality has a tactic. Review the decisions above; they are the judgement calls.
