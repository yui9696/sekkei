# Vendor Security Questionnaire — answers become the v2 platform requirements

Product: Kestrel People (HR & payroll SaaS for 200–2,000 employee companies)
Prepared for: Nordbank procurement (RFP 2026-771). Answers marked **COMMIT** are commitments the engineering team must deliver before contract signature (target: 2027-02-28). Answers marked **CURRENT** describe what exists today and are not requirements. Answers marked **N/A** are out of scope.

Engineering: please treat every COMMIT row as a requirement. Do not treat CURRENT rows as work.

## Section A — Data protection

| ID | Question | Answer | Status |
|---|---|---|---|
| A1 | Is customer data encrypted at rest? | Yes. All databases and object storage use AES-256 with keys held in the cloud KMS; keys rotate every 90 days. | CURRENT |
| A2 | Is customer data encrypted in transit? | Yes, TLS 1.2+ everywhere; TLS 1.3 will be enforced for all public endpoints. | COMMIT |
| A3 | Can the customer bring their own encryption key (BYOK)? | We will support customer-managed keys per tenant; revoking the key must make the tenant's data unreadable within 1 hour. | COMMIT |
| A4 | Where is data stored? | EU (Frankfurt) by default. Nordbank requires all data, backups and logs to stay in Sweden or Finland; we will add a Nordic region and pin Nordbank's tenant to it. | COMMIT |
| A5 | Do you delete data on termination? | We will delete all tenant data within 30 days of contract end and provide a signed deletion certificate. Backups expire within a further 35 days. | COMMIT |
| A6 | Do you retain payroll records for the statutory period? | Yes: payslips and payroll journals are retained for 7 years after the employee leaves, even after tenant termination if the customer opts in. | COMMIT |
| A7 | Is production data used in test environments? | Never. A masking job produces synthetic tenants for staging. | CURRENT |

## Section B — Access control

| ID | Question | Answer | Status |
|---|---|---|---|
| B1 | Do you support SSO? | We will support SAML 2.0 and OIDC with the customer's IdP; SSO can be made mandatory per tenant so that password login is disabled. | COMMIT |
| B2 | Do you support SCIM provisioning? | We will implement SCIM 2.0 (users and groups) so that leavers are deprovisioned within 15 minutes of removal in the IdP. | COMMIT |
| B3 | Is MFA available? | MFA (TOTP and WebAuthn) will be required for every user with the Payroll Admin or HR Admin role. | COMMIT |
| B4 | Is there role-based access control? | Roles: Employee, Manager, HR Admin, Payroll Admin, Auditor (read-only). A manager can only see the employees in their reporting line. An auditor cannot export bank details. | COMMIT |
| B5 | Do you support IP allow-listing? | Per tenant, optional. | COMMIT |
| B6 | How is privileged access by your staff controlled? | Support staff access to a tenant requires a customer-approved ticket, is limited to 8 hours, and every action is recorded. The customer can view the access log. | COMMIT |

## Section C — Logging and monitoring

| ID | Question | Answer | Status |
|---|---|---|---|
| C1 | Do you keep an audit log? | Every read of an employee's bank details, salary or national ID, and every change to any record, is written to an immutable audit log retained for 3 years. Nordbank can export it to their SIEM as JSON over HTTPS every 5 minutes. | COMMIT |
| C2 | Do you have intrusion detection? | Cloud-native IDS. | CURRENT |
| C3 | What are your alerting SLAs? | Security alerts are triaged within 30 minutes, 24×7. | CURRENT |

## Section D — Availability and continuity

| ID | Question | Answer | Status |
|---|---|---|---|
| D1 | What is your uptime commitment? | 99.9 % monthly for the web application and API, measured at the load balancer, excluding announced maintenance windows (max 4 hours per month, Sundays 02:00–06:00 CET). | COMMIT |
| D2 | What are your RPO and RTO? | RPO 15 minutes, RTO 4 hours, tested twice a year with a full failover to the secondary region. | COMMIT |
| D3 | Do you have a status page? | Yes. | CURRENT |
| D4 | Payroll deadlines | The payroll run for a tenant must complete within 2 hours of being started for tenants up to 2,000 employees; if it cannot complete, the run is rolled back entirely — a partially posted payroll is never left in the system. | COMMIT |

## Section E — Secure development

| ID | Question | Answer | Status |
|---|---|---|---|
| E1 | Do you perform penetration tests? | Annually by a CREST-accredited firm; summary shared under NDA. | CURRENT |
| E2 | Do you have a vulnerability disclosure programme? | Yes. | CURRENT |
| E3 | Are dependencies scanned? | Yes, on every build. Critical CVEs block deployment. | CURRENT |
| E4 | Are container images signed? | Images will be signed with cosign and the cluster will refuse unsigned images. | COMMIT |

## Section F — Integrations Nordbank needs

| ID | Question | Answer | Status |
|---|---|---|---|
| F1 | Payroll file to the bank | We will produce the ISO 20022 pain.001 file per payroll run and deliver it to Nordbank's SFTP with a PGP-signed manifest; the file must never contain an employee that was deprovisioned before the run. | COMMIT |
| F2 | HRIS import | Nightly import of the employee master from Workday (their HRIS) via the Workday REST API; conflicts are reported to the HR Admin, not auto-resolved. | COMMIT |
| F3 | Public API | Rate limit 600 requests per minute per API key; API keys expire after 12 months. | COMMIT |
| F4 | Webhooks | Not offered. | N/A |

## Section G — Scale (for information)

- Nordbank: 1,850 employees, 3 legal entities, monthly payroll, about 40 HR staff.
- Platform today: 310 tenants, 140,000 employees, peak load on the 25th of each month when payslips are published (about 60,000 payslip views in one hour).
- Team: 7 engineers, 1 security engineer, 1 SRE. Stack: TypeScript/NestJS, PostgreSQL, Redis, Kubernetes on AWS.
