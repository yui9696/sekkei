Post-mortem: INC-2291 — e-discovery ingestion stalled for 31 hours

Date of incident: 2026-08-19 to 2026-08-20
Severity: SEV-1 (a court production deadline was missed for one matter)
Facilitator: Owen Park · Incident commander: Leila Haddad
Status: action items agreed, engineering to implement

Summary

The ingestion pipeline that processes custodian data (PST mailboxes, SharePoint exports, Slack exports) into the review platform stopped making progress for 31 hours. A single 48 GB PST with a corrupted attachment caused the extractor to crash-loop, and because ingestion is a single sequential queue, every other matter's data waited behind it. The matter team for Halvorsen v. Meridian missed a production deadline and had to request an extension.

Timeline

- 08-19 02:14 UTC: nightly ingestion picks up the PST for matter M-1187.
- 08-19 02:31: extractor process exits with an out-of-memory error; the orchestrator restarts it; it fails again on the same file.
- 08-19 09:05: a reviewer reports that no new documents appeared for matter M-1203 overnight.
- 08-19 11:40: on-call identifies the crash loop; there is no dashboard showing queue depth per matter.
- 08-20 09:20: the file is moved aside by hand; ingestion resumes; backlog of 2.1 million documents clears by 08-20 21:00.

Root causes

1. Ingestion is one FIFO queue shared by all matters; one bad file blocks everything.
2. The extractor has no per-file resource limits or retry budget.
3. No alert fires on ingestion stall; the only alert is on host CPU.

What went well

- The extension was granted; no data was lost.

Action items (these are the requirements for the remediation project)

AI-1 (must): Ingestion shall process each matter in its own queue so that a failure in one matter does not delay another. Owner: platform. Due: 2026-10-31.
AI-2 (must): A file that fails extraction 3 times shall be quarantined with the error recorded, and the matter's case manager shall be notified by email within 10 minutes; the rest of the matter's files continue.
AI-3 (must): Each extractor run shall be limited to 8 GB of memory and 2 hours of wall time; a file exceeding either is quarantined, not retried.
AI-4 (must): The operations dashboard shall show, per matter, queue depth, documents processed in the last hour, and the age of the oldest unprocessed file; on-call shall be paged when the oldest file in any matter is older than 4 hours.
AI-5 (should): Case managers shall be able to raise the priority of a matter so that its files are processed before other matters' files.
AI-6 (should): Ingestion throughput shall be at least 500,000 documents per hour across all matters, so that a 2 million document backlog clears within 4 hours.
AI-7 (could): Extraction of PST attachments shall be attempted with a second library (libpff) when the primary extractor fails, before quarantining.
AI-8 (must): Every document shall carry a chain-of-custody record (source file, hash, extraction time, extractor version) that is never modified after creation; it is required for admissibility.
AI-10 (must): Case managers shall be able to pause and resume ingestion for a matter from the operations dashboard; a paused matter's files stay queued and are not lost.
AI-11 (should): Every quarantined file shall be listed in a weekly summary email to the platform team with the error class and the matter id.
AI-9 (must): Processed documents shall be de-duplicated by content hash across the matter; near-duplicates are out of scope.

Constraints noted in the meeting

- Java 21, existing RabbitMQ, PostgreSQL 15 and the on-prem object store (MinIO). The review platform's index (Elasticsearch 8) is consumed by a separate team and is not changed by this project.
- Team: 3 engineers for 8 weeks; Leila is the tech lead.
- Data must not leave the customer's jurisdiction; the platform runs per customer in a single region.

Follow-ups not in scope

- Rewriting the review platform's search.
- Migrating off RabbitMQ.
