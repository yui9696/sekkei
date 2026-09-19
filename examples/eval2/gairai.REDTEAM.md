# Red-team report (engine self-audit)

3 finding(s) from 19 engine runs: 0 high, 2 medium, 1 info.

## medium

- **RT07** [R-1] no catalogue pattern recognised this sentence; it was placed by the engine's fallback
  - evidence: Patients departments choose doctors. The system can register, change and cancel available slots from appointments.
- **RT07** [R-2] no catalogue pattern recognised this sentence; it was placed by the engine's fallback
  - evidence: Staff can accept and register bookings patients. Staff can view bookings list the same day departments each.

## info

- **RT02** [constraint R-14 removed (Patients authenticate existing patient portal (OIDC).)] 1 decision(s) change: Caller authentication: OAuth2 / OIDC with the platform's identity provider → API keys per customer, hashed at rest, sent as a bearer token
