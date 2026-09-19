Change Request CR-4471: Add split payments to the existing Checkout platform

Requested by: Merchant Success (Helena Vos)
Systems affected: checkout-api, payment-orchestrator, ledger-service, merchant-portal, notification-hub

1. Context
Marketplaces on our platform sell baskets that contain items from several sellers. Today checkout-api creates one PaymentIntent in payment-orchestrator, and ledger-service books the whole amount to the marketplace. Sellers are paid out by the marketplace manually. Three large marketplaces have asked for automatic split of a single payment across sellers at capture time.

2. Requested change
2.1 checkout-api must accept a basket whose line items carry a seller_id and a platform_fee_bps, and create one PaymentIntent with a split plan attached.
2.2 payment-orchestrator must, on successful capture, instruct the acquirer to settle each seller's share to the seller's connected account and the platform fee to the marketplace. Settlement instructions must be idempotent; a retry must never double-pay a seller.
2.3 ledger-service must book one ledger entry per seller share and one per fee, all linked to the original PaymentIntent, in the same transaction as the capture booking.
2.4 Refunds: a partial refund must be attributed to the correct seller share; the platform fee on the refunded portion is returned to the marketplace unless the marketplace opted to keep it.
2.5 merchant-portal must show sellers their pending and settled shares, and let the marketplace admin configure the default platform_fee_bps per seller.
2.6 notification-hub must send sellers a settlement notice (email and webhook) within 1 hour of settlement.

3. Non-functional
- Existing checkout latency budget is unchanged: 300 ms p95 for POST /checkout/sessions.
- Split settlement must complete within 24 hours of capture for 99.9% of payments.
- Ledger must remain balanced at all times; a nightly reconciliation job compares acquirer settlement reports with ledger entries and opens a ticket on any discrepancy.
- Volume: 1.2M payments/day, average 2.3 sellers per split basket, peak 150 checkouts/s.
- PCI DSS scope must not grow: no card data enters the new code paths.
- The existing Kafka topics payment.captured and payment.refunded are the integration points; do not add synchronous calls between payment-orchestrator and ledger-service.

4. Out of scope
- Seller onboarding / KYC (already handled by onboarding-service).
- Currency conversion between seller and marketplace currencies.

5. Rollout
- Feature flag per marketplace. Pilot with Nordic Crafts Market in November, GA in January.
- Migration: existing PaymentIntents are untouched; only new baskets with seller_id use the split path.
