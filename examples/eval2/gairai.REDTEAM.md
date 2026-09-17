# Red-team report (engine self-audit)

4 finding(s) from 19 engine runs: 0 high, 3 medium, 1 info.

## medium

- **RT06** [decisions] 9 decisions are proposed from assumptions against 8 taken from the text; answer the questions in NOTES.md §1 before building
- **RT07** [R-1] no catalogue pattern recognised this sentence; it was placed by the engine's fallback
  - evidence: Patients departments choose doctors. The system can register, change and cancel available slots from appointments.
- **RT07** [R-2] no catalogue pattern recognised this sentence; it was placed by the engine's fallback
  - evidence: Staff can accept and register bookings patients. Staff can view bookings list the same day departments each.

## info

- **RT01** [R-14] deleting this constraint changes nothing: it coincides with what the engine assumes by default (still worth stating)
  - evidence: Patients authenticate existing patients OIDC.
