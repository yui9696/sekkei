# Field inspection app

Inspectors visit ~30 sites a day, often without mobile coverage, fill in checklists with photos and signatures, and the office sees results the same day.

- Inspectors log in with the company's Okta account; the app works offline for up to 3 days and syncs when back online.
- Checklists are defined by office staff (questions, photo required or not, allowed answers); a new version applies to inspections started after publication.
- Photos (up to 20 per inspection, ~3 MB each) upload in the background; an inspection is complete only when all photos are uploaded.
- Office staff review inspections on a web dashboard, filter by site/date/inspector, and export PDF reports.
- Conflicts: if two inspectors edit the same inspection offline, the later sync wins but both versions are kept.
- 400 inspectors, iOS and Android. Sync latency after reconnecting: under 1 minute for a day's work.
- Kotlin Multiplatform for the apps, Go backend, PostgreSQL, S3-compatible object storage on-prem. Team of 5.
