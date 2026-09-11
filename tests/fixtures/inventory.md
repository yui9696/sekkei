# Warehouse inventory service

A small company keeps stock in two warehouses and needs one source of truth for what is
where. Staff use handheld scanners and a web dashboard; the finance system reads totals.

## Functional
- Staff can add, move and remove stock items (SKU, quantity, warehouse, bin) through a REST API.
- Staff can search items by SKU, name or bin and list the stock of one warehouse with paging.
- Every stock change is recorded with who did it and when; managers can view the history of an item.
- Every night at 02:00 the system aggregates stock per SKU and exports a CSV report for the finance system.
- Managers receive an email when any SKU falls below its reorder level.

## Non-functional
- Search returns within 300 ms p95 for a catalogue of 200,000 items.
- Stock counts are never lost or double-applied: two scanners moving the same item concurrently must end in a consistent state.
- The service handles 50 requests/s sustained during shift changes.

## Constraints
- TypeScript on Node 20, PostgreSQL available. Team of 2. Deployed as containers behind an existing ingress.
- Authentication is handled by the company's OIDC identity provider; the service must accept its tokens.

## Out of scope
- Purchasing and supplier management.
- Barcode label printing.
