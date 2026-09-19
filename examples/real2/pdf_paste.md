Inventory Replenishment Service — Functional Specification            Page 1 of 3
ACME Retail Ltd — Confidential

1 Purpose
The replenishment service computes reorder proposals for every store
each night and sends purchase orders to suppliers via EDI. Proposals
must be available to category managers by 05:00 local time.

2 Requirements
2.1 The service must compute a reorder proposal for each of the 850
stores and 120,000 SKUs nightly; the run must finish within 3 hours.
2.2 Category managers must be able to approve or reject proposals
in the web portal before 09:00; unapproved proposals are auto-
approved at 09:00.
2.3 Purchase orders must be sent to suppliers over EDI (AS2) within
15 minutes of approval.

Inventory Replenishment Service — Functional Specification            Page 2 of 3
ACME Retail Ltd — Confidential

2.4 Stock levels are read from the existing WMS (Manhattan) via its
REST API every hour.
2.5 The service must retain proposals and decisions for 3 years for
audit.
3 Non-functional
Availability 99.5% outside the nightly run window. Data stays in the
EU. Team of 6, Java/Spring is the standard.
Inventory Replenishment Service — Functional Specification            Page 3 of 3
