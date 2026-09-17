# Loan origination service

A digital lender takes personal-loan applications online, checks identity and credit, and hands approved loans to the core banking system.

## Functional
- Applicants can create an application (amount, term, income, employment), upload identity documents and payslips, and see the status of their application.
- The service verifies the applicant's identity through an external KYC provider and fetches a credit report from the bureau; both calls have a 10 s timeout.
- A scoring model predicts default risk from the application and the credit report; applications above the threshold are approved automatically, borderline ones go to an underwriter.
- Underwriters review borderline applications in a queue, request more documents, and approve or reject with a reason; an application waiting more than 2 business days escalates to a senior underwriter.
- Approved loans are exported nightly to the existing core banking system (system of record for the loan account) as a fixed-format file.
- Every decision is recorded with the model version, the inputs and who took it, for regulators.
- Applicants can download a copy of their data and request deletion after the retention period.

## Non-functional
- 2,000 applications per day; 1,000 pending applications at any time; scoring returns within 2 s p95.
- No application or decision is lost on a crash; a decision is never recorded twice.
- Personal and financial data are encrypted; access to documents is logged; decisions are retained for 7 years.
- 99.9 % monthly availability for the applicant surface; metrics for Prometheus; structured logs.

## Constraints
- Python 3.12, PostgreSQL and S3-compatible object storage available; containers behind an existing ingress; single region. Team of 5.
- Applicants authenticate with the bank's OIDC identity provider; underwriters with the corporate SSO.

## Out of scope
- Loan servicing and collections (core banking).
- Building the scoring model (a data-science team ships it as a versioned artifact).
