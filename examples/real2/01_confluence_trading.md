# Order Management Service for the FX Options Desk — Design Doc

| Field | Value |
|---|---|
| Owner | Priya Natarajan (Rates & FX Platform) |
| Status | DRAFT v0.4 |
| Reviewers | Tom Beckett (Risk), Aiko Sato (Compliance), Platform SRE |
| Target | Q1 2027 go-live |

## 1. Background

The desk currently keys FX option orders into the vendor screen (Murex) by hand and re-keys fills into the risk book. Fat-finger errors caused two P1 incidents in 2026. We want an order management service (OMS) that sits between the trader UI and the venues, enforces pre-trade limits, and books fills automatically.

## 2. Goals

1. Traders submit, amend and cancel FX option orders (vanilla and barrier) from the desktop UI.
2. Every order is checked against the desk's pre-trade risk limits (delta, vega, notional per counterparty) before it reaches a venue.
3. Fills are booked into the risk book within 500 ms of receipt from the venue.
4. The service is the golden source for order state; the vendor screen becomes read-only.

## 3. Non-goals

- Pricing. Prices come from the existing PricingGrid service.
- Post-trade settlement and confirmations (stays in BackOfficeHub).

## 4. Requirements

| ID | Requirement | Priority |
|---|---|---|
| R-01 | A trader can submit a new order with instrument, notional, strike, expiry, direction and limit price. | Must |
| R-02 | A trader can amend the limit price or notional of a working order. | Must |
| R-03 | A trader can cancel a working order; a cancel must reach the venue within 200 ms p99. | Must |
| R-04 | Pre-trade limit check must complete within 50 ms p99 and must reject an order that breaches any limit with a reason code. | Must |
| R-05 | The risk officer can set and update limits per trader and per counterparty; changes take effect within 5 seconds. | Must |
| R-06 | Fills received from a venue are booked to the risk book within 500 ms; if booking fails the fill is retried and an alert is raised. | Must |
| R-07 | Every order, amend, cancel, reject and fill is written to an immutable audit trail retained for 7 years (MiFID II). | Must |
| R-08 | Compliance can replay the full order history of any trader for any trading day. | Must |
| R-09 | The system must handle 2,000 orders per minute sustained and 400 orders per second at the London open burst. | Must |
| R-10 | Availability 99.95% during trading hours (07:00–18:00 London). | Must |
| R-11 | Orders must be time-stamped with microsecond precision from a PTP-synchronised clock. | Should |
| R-12 | Kill switch: the risk officer can halt all order flow for a trader or the whole desk in one action. | Must |
| R-13 | Trader UI shows order state changes within 1 second. | Should |

## 5. Constraints

- Venues are connected over FIX 4.4 (Bloomberg, 360T). The existing FIXGateway service is reused; do not build a new FIX engine.
- Runs in the bank's on-prem Kubernetes (OpenShift). No public cloud.
- Team: 5 engineers, 1 SRE. Java is the desk standard; Kotlin acceptable.
- Must integrate with the existing entitlement service (EntitleX) for who-can-trade-what.
- Data must not leave the UK region.

## 6. Open questions

- Do barrier orders need a separate limit type? (Tom)
- Is the 7-year retention satisfied by the bank's WORM archive or do we keep our own copy?
