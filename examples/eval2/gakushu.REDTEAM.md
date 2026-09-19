# Red-team report (engine self-audit)

2 finding(s) from 19 engine runs: 0 high, 1 medium, 1 info.

## medium

- **RT07** [R-3] no catalogue pattern recognised this sentence; it was placed by the engine's fallback
  - evidence: Employees can take tests. Employees can view explanations grades immediately.

## info

- **RT02** [constraint R-14 removed (Employees authenticate internal SSO (OIDC). Containers exist)] 1 decision(s) change: Caller authentication: OAuth2 / OIDC with the platform's identity provider → API keys per customer, hashed at rest, sent as a bearer token
