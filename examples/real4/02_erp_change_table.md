# ERP Customisation Specification — Procure-to-Pay for Brenner Maschinenbau

Project: NetSuite go-live Phase 2 (Procure-to-Pay)
Integrator: Fjord Consulting · Client sponsor: Ute Brenner (CFO) · Version 1.3 · 2026-09-16

## 1. Scope statement

Phase 2 customises the standard NetSuite Procure-to-Pay process for Brenner's three plants (Linz, Graz, Wels). The standard process is kept wherever the table below does not say otherwise. Each row of the change table is a deliverable. Rows with type STD are standard configuration and are listed for completeness only; they are not development work.

Out of scope for Phase 2: the Order-to-Cash changes (Phase 3), the shop-floor MES interface, and the migration of purchase orders created before 2024-01-01 (they stay in the legacy AS/400 and are looked up there when needed).

## 2. Change table

| ID | Module | Type | Change | Trigger / rule | Priority | Est. days |
|---|---|---|---|---|---|---|
| CR-001 | Purchasing | SCRIPT | Purchase requisitions above EUR 10,000 require a second approver from the plant controller group before conversion to a purchase order. | On requisition submit | Must | 3 |
| CR-002 | Purchasing | SCRIPT | Requisitions above EUR 100,000 additionally require CFO approval; the CFO can delegate for up to 14 days. | On requisition submit | Must | 2 |
| CR-003 | Purchasing | WORKFLOW | An approval not actioned within 3 working days is escalated to the approver's manager and a reminder email is sent daily. | Scheduled, hourly | Must | 2 |
| CR-004 | Purchasing | STD | Enable three-way match (PO, receipt, invoice). | Configuration | Must | 0 |
| CR-005 | Purchasing | SCRIPT | Three-way match tolerance: quantity ±2 %, price ±1 % or EUR 50, whichever is greater; invoices outside tolerance are put on hold and the buyer is notified. | On vendor bill save | Must | 4 |
| CR-006 | Vendors | SCRIPT | A new vendor cannot be used on a purchase order until the IBAN has been verified by a second person (four-eyes) and the verification is logged with both user IDs. | On PO save | Must | 3 |
| CR-007 | Vendors | SCRIPT | A change to a vendor's IBAN sends an email to the AP team lead and blocks payments to that vendor for 48 hours. | On vendor save | Must | 2 |
| CR-008 | Vendors | INTEGRATION | Vendor master synchronised from the SAP Ariba supplier portal every 15 minutes; Ariba is the system of record for vendor addresses, NetSuite for bank details. Conflicts are queued for AP review and never overwritten automatically. | Scheduled | Must | 8 |
| CR-009 | Receiving | UI | Plant warehouse staff receive goods on a tablet with barcode scanning of the delivery note; partial receipts allowed. | User action | Must | 6 |
| CR-010 | Receiving | SCRIPT | A receipt without a purchase order is not allowed; the tablet shows the open POs for the vendor instead. | On receipt | Must | 1 |
| CR-011 | AP | INTEGRATION | Vendor invoices arrive as PDF by email to invoices@brenner.at; an OCR service (ABBYY Vantage, already licensed) extracts header and lines; a bill is created in draft with a confidence score; below 90 % confidence the bill goes to a manual queue. | Email received | Must | 10 |
| CR-012 | AP | SCRIPT | Duplicate invoice detection on vendor + invoice number + amount within 12 months; duplicates are rejected with a reason. | On vendor bill save | Must | 2 |
| CR-013 | AP | WORKFLOW | Bill approval follows the PO approval chain; bills without PO follow a cost-centre-based chain defined in a maintained matrix (max 4 levels). | On bill submit | Must | 5 |
| CR-014 | Payments | SCRIPT | Payment runs on Tuesdays and Fridays at 10:00 create a SEPA pain.001 file per bank account; the file is uploaded to Raiffeisen via EBICS; the run is blocked if any vendor in it has a pending IBAN change. | Scheduled | Must | 6 |
| CR-015 | Payments | SCRIPT | Early-payment discounts (Skonto) are taken automatically when the payment date falls within the discount window; the discount amount is posted to account 4830. | On payment run | Should | 2 |
| CR-016 | Reporting | REPORT | Open commitments per plant and cost centre (POs received but not invoiced), refreshed nightly, visible to plant controllers. | Scheduled | Must | 3 |
| CR-017 | Reporting | REPORT | Days-payable-outstanding dashboard per plant, monthly, with a 13-month trend. | Scheduled | Should | 2 |
| CR-018 | Reporting | INTEGRATION | Export of all posted bills and payments to the group data warehouse (Snowflake) daily by 05:00 CET as Parquet files; a failed export must be retried and the controlling team informed by 07:00 if it still fails. | Scheduled | Must | 4 |
| CR-019 | Audit | SCRIPT | Every change to an approval limit, approval matrix or vendor bank detail is written to an audit record that cannot be edited or deleted, retained for 10 years (Austrian BAO §132). | On save | Must | 2 |
| CR-020 | Audit | REPORT | Segregation-of-duties report: users who can both create vendors and approve payments are listed weekly for the CFO. | Scheduled | Must | 1 |
| CR-021 | Purchasing | STD | Currency: EUR only; USD purchase orders are allowed but converted at the ECB daily rate. | Configuration | Must | 0 |
| CR-022 | Purchasing | SCRIPT | Blanket orders: call-offs against a blanket order cannot exceed the remaining blanket value; the buyer is warned at 80 %. | On PO save | Should | 3 |
| CR-023 | Legacy | INTEGRATION | Lookup of pre-2024 purchase orders in the AS/400 (DB2 over ODBC, read-only) from the PO screen; results are not copied into NetSuite. | User action | Could | 5 |
| CR-024 | Migration | DATA | One-time load of open POs, open bills and vendor master from the AS/400 for the cut-over weekend; reconciled to the cent against the AS/400 trial balance before go-live. | Cut-over | Must | 8 |
| CR-025 | Performance | NFR | The requisition screen must load in under 2 seconds and the payment run for up to 3,000 bills must complete in under 20 minutes. | — | Must | — |
| CR-026 | Availability | NFR | Business hours 06:00–20:00 CET on working days: no planned downtime; NetSuite's own SLA (99.5 %) is accepted for the platform. | — | Must | — |
| CR-027 | Security | NFR | Access via the corporate Azure AD SSO only; no local NetSuite passwords; the integration user for Ariba and Snowflake uses token-based auth rotated every 90 days. | — | Must | — |
| CR-028 | Volumes | NFR | About 1,400 purchase orders, 2,600 vendor bills and 900 payments per month across the three plants; 220 named users; 35 concurrent at peak (month end). | — | — | — |

## 3. Constraints

- SuiteScript 2.1 (JavaScript) only; no third-party bundles beyond the ones already installed (ABBYY connector, EBICS module).
- All customisations must be deployable through SuiteCloud SDF from Git; nothing is configured by hand in production.
- Cut-over weekend: 2027-01-09/10. UAT by the client team (4 people) in December.
- Fjord team: 2 developers, 1 functional consultant, 1 project manager (half time).

## 4. Acceptance

Each CR is accepted when its test script in the UAT workbook passes and the client's process owner signs the row. CR-024 additionally requires the reconciliation report signed by the CFO.
