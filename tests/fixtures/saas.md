# Expense approval SaaS

A multi-tenant service where employees submit expense claims and managers approve them; each customer organisation is a tenant and must never see another tenant's data.

## Functional
- Employees can create, edit and submit expense claims (amount, currency, receipt image, cost centre) through a REST API.
- Managers approve or reject submitted claims with a comment; a claim past its step deadline of 3 days escalates to the next manager.
- Finance staff can export approved claims as CSV and see monthly totals per cost centre on a dashboard.
- Employees can delete their data on request within 30 days (GDPR); every access to personal data is logged.
- Claims are exchanged nightly with the existing ERP system (SAP) which remains the system of record for payments.
- New features are released gradually to a percentage of tenants behind feature flags.
- The interface is available in Japanese and English with each tenant's timezone and currency.

## Non-functional
- 5,000 tenants and 200,000 employees; 50 claims/s at the end of the month.
- Listing claims returns within 400 ms p95.
- Backups run daily; recovery point 1 hour and recovery time 4 hours.
- 99.9 % monthly availability.
- Metrics for Prometheus and structured logs.

## Constraints
- Python 3.12, PostgreSQL available, containers behind an existing ingress, OIDC identity provider. Team of 4. Single region.

## Out of scope
- Payroll and payment execution (done by the ERP).
