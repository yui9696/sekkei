# Red-team report (engine self-audit)

1 finding(s) from 17 engine runs: 0 high, 0 medium, 1 info.

## info

- **RT02** [constraint R-13 removed (Applicants authenticate with the bank's OIDC identity provid)] 1 decision(s) change: Caller authentication: OAuth2 / OIDC with the platform's identity provider → API keys per customer, hashed at rest, sent as a bearer token
