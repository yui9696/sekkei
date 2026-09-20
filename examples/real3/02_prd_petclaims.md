# PRD: PawPay Claims — instant pet-insurance claim payouts

Author: Dani Reyes (PM, Claims) · Status: Ready for engineering review · Last edited 2026-09-14

## Problem

Policyholders wait 11 days on average for a claim to be paid. 38 % of NPS detractors cite claim speed. Vets refuse direct billing because we settle slowly. We lose 4 % of customers a year at renewal specifically citing claims.

## Goals and KPIs

| KPI | Today | Target (Q2 2027) |
|---|---|---|
| Median time to payout (straightforward claims) | 11 days | under 15 minutes |
| Claims auto-adjudicated without a human | 0 % | 60 % |
| Fraudulent payouts | unknown | below 0.5 % of paid amount |
| Claims per month | 42,000 | 70,000 |

## User segments

- **Policyholders** (280,000 active policies; mobile app 70 %, web 30 %). They submit claims and want money fast.
- **Vet clinics** (about 3,100 partnered). They upload invoices on behalf of policyholders and want direct settlement.
- **Claims handlers** (team of 45). They review anything the rules cannot decide.
- **Fraud analysts** (team of 6). They review flagged claims and configure rules.

## Requirements

### P0 — must ship

1. A policyholder can submit a claim from the app with a photo of the vet invoice and the pet's policy number; the invoice is read by OCR and the line items are shown back for confirmation.
2. A vet clinic can submit a claim on a policyholder's behalf through the clinic portal and choose direct settlement to the clinic's bank account.
3. The rules engine adjudicates every claim against the policy (excess, annual limit, waiting period, excluded conditions) and pays automatically when the invoice total is under £500 and no fraud rule fires.
4. Payouts go out via Faster Payments (our provider is Modulr) within 15 minutes of adjudication for at least 95 % of auto-approved claims.
5. Claims handlers see a queue of claims the rules could not decide, ordered by age, and can approve, partially approve (with a reason code) or reject; the policyholder is notified by push and email in each case.
6. A fraud score is computed for every claim from duplicate-invoice detection, claim frequency per pet, and clinic-level anomalies; claims scoring above the configured threshold are held for a fraud analyst.
7. A payment must never be issued twice for the same claim, including when the payment provider times out.
8. Every adjudication decision (automatic or human) is stored with the rule versions that produced it and is retained for 7 years for the FCA.

### P1 — should ship

9. Policyholders can see the status of every claim (submitted → adjudicating → approved/held/rejected → paid) with an estimated payout date.
10. Fraud analysts can edit fraud rules and thresholds in a UI without a deployment; changes take effect within 5 minutes and are versioned.
11. Weekly report to Finance of paid claims by policy product, exported as CSV to the Finance SFTP.

### P2 — nice to have

12. Direct integration with the top 3 practice-management systems (Vetstoria, ezyVet, Provet) so clinics do not re-key invoices.

## Non-functional

- Peak: Monday mornings, about 4× the average rate. Assume 70,000 claims/month at target.
- Claim submission and status pages: p95 under 800 ms.
- Availability 99.9 % for submission; the payout step may degrade to next-business-day without breaching the policy.
- Personal data (policyholder, pet medical history) under UK GDPR; invoices and medical records must be encrypted at rest and access logged.
- Do not store bank account numbers in our systems; use the provider's tokenised beneficiary references.

## Constraints and context

- Kotlin/Spring Boot services, PostgreSQL on AWS RDS, existing Kafka cluster, existing policy-admin system (Guidewire) exposing a SOAP API for policy lookup.
- OCR: we have a contract with Google Document AI.
- Team: 6 backend, 2 mobile, 1 data scientist, plus 1 SRE shared with another squad.
- Launch in the UK only; Ireland next year.

## Out of scope

- Underwriting and pricing.
- Changes to the mobile app's policy purchase flow.

## Open questions

- Do we need a claims handler override that bypasses the fraud hold? (Legal to confirm.)
- Is Modulr's 15-minute SLA contractual or best-effort?
