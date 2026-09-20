# Research Data Platform for the Institute of Population Health — architecture sketch

Written by the platform group after the workshop of 2026-09-11. Most of this document is the diagrams we drew; the text under each diagram is what the boxes and arrows mean. Where two workshop groups disagreed we recorded both positions; the steering committee has not resolved them.

## Diagram 1 — data flow (whiteboard, redrawn)

```
  [NHS Trusts x12] --(monthly SFTP, pseudonymised CSV)--> [Landing zone]
  [Cohort survey app] --(nightly export)--------------> [Landing zone]
  [Wearables vendor API] --(hourly pull)---------------> [Landing zone]
                                                              |
                                                     validate + link
                                                              v
                                                     [Linked cohort store]
                                                        /          \
                                          (approved project)     (audit)
                                              v                       v
                                      [Project workspace]        [Provenance log]
                                     (JupyterHub + R, per project)
                                              |
                                        output check
                                              v
                                       [Released outputs]
```

The twelve trusts each deliver one CSV bundle a month to the landing zone over SFTP; files are pseudonymised by the trust before delivery using the institute's key (we hold the key, the trusts hold the mapping). The survey app exports every night. The wearables vendor is polled every hour and returns JSON. Everything lands in the landing zone, is validated against the data dictionary, and linked on the pseudonymous ID into the linked cohort store. A researcher only ever works inside a project workspace, which is a JupyterHub environment (Python and R) that mounts a project-specific extract of the cohort store, read-only. Nothing leaves a workspace except through the output-checking step, where two trained checkers approve each file before it appears in released outputs. Every access and every release is written to the provenance log.

## Diagram 2 — approval (the arrow diagram)

```
  researcher --submits--> [Data access request] --reviewed by--> [Data Access Committee]
       ^                                                                 |
       |                                          approve / reject / ask for changes
       |                                                                 v
       +---------------(workspace provisioned within 2 working days)-----+
```

A researcher submits a data access request naming the variables and the years they need and attaches ethics approval. The Data Access Committee (five members, meets fortnightly, but urgent requests can be approved by any two members by email) approves, rejects, or asks for changes. On approval the workspace is provisioned automatically within two working days with exactly the approved variables, no more. Projects expire after 24 months and the workspace is destroyed 30 days after expiry, keeping only the released outputs and the provenance log.

## Diagram 3 — the box we argued about

```
   +--------------------------------------------------+
   |   Linked cohort store                            |
   |   group A: "PostgreSQL, one schema per source"   |
   |   group B: "Parquet on object storage + DuckDB"  |
   +--------------------------------------------------+
```

Group A wants a relational store because the linkage rules are joins and the Data Access Committee wants row-level access control. Group B wants columnar files because the wearables data alone is 40 TB and grows by 1.5 TB a month, and researchers want to scan whole cohorts. The committee did not decide. Both groups agree that raw wearables signals are retained for 10 years and that the linked store is rebuilt from the landing zone if it is ever corrupted.

## Notes on the sticky notes

- "No identifiable data ever enters the platform" (green sticky, agreed by everyone).
- "We need participants' email addresses to send the annual survey reminders" (yellow sticky, survey team). This is the survey app's job, not the platform's — but the survey team wants the reminder list generated from the cohort store, which would put email addresses in the platform.
- "Retention: delete everything 5 years after the study ends" (pink sticky, ethics officer).
- "Retention: keep the linked cohort indefinitely for future studies, it cost £4M to build" (pink sticky, director).
- "Researchers can download extracts to their laptops for conference deadlines" (yellow sticky, one PI). The output-checking group said no; the PI said this happens today.
- "All processing in the UK" (green sticky). "Use the vendor's US-hosted analytics for the wearables" (blue sticky, the wearables vendor's suggestion).
- Peak: 60 concurrent workspaces; typical 15. About 40 access requests a year. The monthly trust bundles total about 200 GB.
- Team: 3 data engineers, 1 platform engineer, 0.5 information governance officer. Existing: on-premises OpenStack with Ceph, and an Azure tenancy the university already pays for.
- Availability: nobody wrote a number. The workshop said "it's research, a day of downtime is fine, but losing data is not".

## What the steering committee has to decide

1. Diagram 3 (store technology).
2. Whether the survey reminder list is in or out.
3. Which retention statement is right.
4. Whether laptop extracts are allowed under any conditions.
5. Whether the wearables vendor's US analytics may be used for anything.
