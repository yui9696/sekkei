# Red-team report (engine self-audit)

2 finding(s) from 17 engine runs: 0 high, 0 medium, 2 info.

## info

- **RT02** [constraint R-12 removed (Python 3.12, PostgreSQL and S3-compatible object storage ava)] 1 decision(s) change: Concurrency control for conflicting writes: Row locks inside a short transaction (SELECT ... FOR UPDATE) → Optimistic concurrency: version column checked on every update; conflict returns 409 and the caller retries
- **RT02** [constraint R-13 removed (Applicants authenticate with the bank's OIDC identity provid)] 1 decision(s) change: Caller authentication: OAuth2 / OIDC with the platform's identity provider → API keys per customer, hashed at rest, sent as a bearer token
