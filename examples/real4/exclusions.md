# Support desk

## Requirements
- Out-of-hours calls are excluded from the response-time SLA but must still be logged and answered the next business day.
- Deleted users are excluded from the export; the export must list them in a separate "removed" section.
- Test tenants (names starting with "zz-") are excluded from billing; the billing job must skip them and report how many were skipped.
- Agents can mark a ticket as "not a bug"; such tickets are excluded from the quality report.
- Attachments over 25 MB are excluded from email notifications and replaced by a download link.

## Out of scope
- Phone system integration.

## Constraints
- Ruby on Rails, PostgreSQL. Team: 3 engineers.
