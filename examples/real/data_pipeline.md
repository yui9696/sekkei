# Marketing analytics pipeline

## Functional
- Ingest daily exports from Google Ads, Meta Ads and Salesforce (CSV/JSON on S3, ~50 files/day, up to 2 GB each).
- Normalise into a common schema, deduplicate, and load into Snowflake tables partitioned by day.
- Analysts query the tables from Looker; the pipeline must publish a data-freshness table.
- Re-run any day's load idempotently when a source re-delivers corrected files.
- Alert #data-alerts on Slack when a source is late by more than 2 hours or a load fails.

## Non-functional
- Data for day D is available in Snowflake by 06:00 UTC on D+1 (SLA), 99 % of days.
- Loads are exactly-once at the row level (no duplicate rows after re-runs).
- Cost: stay under the current Snowflake credit budget; prefer batch over streaming.

## Constraints
- Python 3.11, Airflow already running, dbt is used by analysts. AWS (S3, IAM). Team of 2 data engineers.
