# EPIC-42: Customer self-service returns portal

**Labels:** backend, payments, q4  **Story points:** 34

## Stories

### RET-101 — As a customer, I want to request a return for an order item so that I get a refund
Acceptance criteria:
- Given a delivered order less than 30 days old, when I select an item and a reason, then a return request is created with status `requested`.
- Given an order older than 30 days, then the request is rejected with a clear message.
- The request must not be created twice if I double-click.

### RET-102 — As a warehouse operator, I want to mark returned items as received
- Scanning the RMA barcode marks the return `received`; the refund is issued to the original payment method (Stripe) within 5 business days.
- Partial receipts are allowed.

### RET-103 — As a support agent, I want to see all returns for a customer
- Search by email, order id or RMA; results within 500 ms (p95).
- Export to CSV.

### RET-104 — Notifications
- Email the customer on `requested`, `received`, `refunded`.
- Slack #returns-ops when a refund fails.

## Non-functional
- ~2,000 return requests/day, peaks 10x on the day after Black Friday.
- No refund may be issued twice. Ever.
- 99.9 % availability (monthly), EU data residency (GDPR).

## Tech notes
Existing order service exposes REST (`GET /orders/{id}`). Node 20 / TypeScript monorepo, Postgres on RDS, SQS available. Team of 3 (two backend, one full-stack). Feature-flag the rollout per country.
