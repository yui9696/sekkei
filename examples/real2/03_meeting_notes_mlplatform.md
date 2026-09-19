ML platform sync — 2026-09-15, 14:00, room 4B
Present: Dana (eng lead), Raj (ML), Wen (infra), Sofia (product), Kofi (security)

Dana: recap — we need feature store + model registry + batch scoring for the churn team by end of Q4. Three teams already asked. Today we agree scope.

Raj: feature store first. Data scientists define features in Python, features materialize hourly from the warehouse (BigQuery). Online lookups for the recommendation service need <20ms p99, offline training reads need point-in-time correctness.
  TODO Raj: list the 40 features churn needs by Friday.

Wen: online store — Redis or Bigtable? Redis is what we run already. Bigtable if we go past ~10M entity keys. Currently 3M customers.
  DECIDED: Redis for now, revisit at 8M keys.

Sofia: registry must record who trained the model, on which data snapshot, with which code commit. Otherwise audit (Kofi) blocks us.
Kofi: yes — model lineage is mandatory, and any model touching PII features needs a DPIA reference before promotion to prod. Also: no training data leaves the EU project.

Raj: batch scoring — score all 3M customers nightly, results land in the warehouse by 06:00 so the CRM sync picks them up. Scoring job must finish in under 2 hours. Retry once on failure, page on-call if second attempt fails.

Dana: model promotion flow: dev → staging → prod, with a required approval from the model owner AND a second reviewer for prod. Rollback to the previous prod version in one click.
  TODO Dana: write the promotion policy doc.

Wen: infra — GKE, Airflow already there for orchestration, don't add a second scheduler. Artifacts in GCS. Team is 3 platform engineers.

Sofia: adoption — the churn team wants a CLI and a small web UI to browse features and models. No UI for approvals is fine, Slack approvals are OK for v1.
  TODO Sofia: confirm with churn team whether Slack approvals are acceptable to audit.

Kofi: reminder — feature values are customer data, 12-month retention max for feature history; model artifacts kept 3 years.

Dana: out of scope for Q4: real-time/streaming features, GPU training, AutoML.

Actions:
- Raj: feature list (Fri)
- Dana: promotion policy (next Weds)
- Wen: capacity estimate for Redis at 3M keys × 40 features
- Sofia: Slack approval question
