# Red-team report (engine self-audit)

3 finding(s) from 19 engine runs: 0 high, 2 medium, 1 info.

## medium

- **RT07** [R-1] no catalogue pattern recognised this sentence; it was placed by the engine's fallback
  - evidence: Patients departments choose doctors. The system can register, change and cancel available slots from appointments.
- **RT07** [R-2] no catalogue pattern recognised this sentence; it was placed by the engine's fallback
  - evidence: Staff can accept and register bookings patients. Staff can view bookings list the same day departments each.

## info

- **RT01** [R-14] deleting this constraint changes nothing: it coincides with what the engine assumes by default (still worth stating)
  - evidence: Patients authenticate existing patient portal (OIDC).
