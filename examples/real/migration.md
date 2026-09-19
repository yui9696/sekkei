# Order management: split the monolith

We run a Django monolith (orders, inventory, shipping, invoicing) for 8 years. Deploys take 40 minutes and a bug in invoicing takes down checkout. We want to extract **shipping** first as its own service while the rest stays, using a strangler pattern; the existing MySQL database stays the system of record for orders during the transition.

## Functional
- The shipping service owns shipments, carriers and tracking; the monolith calls it to create a shipment when an order is paid and to fetch tracking status.
- Carrier integrations (UPS, DHL, Yamato) fetch tracking updates every 15 minutes and on webhooks.
- Customers see tracking on the order page (served by the monolith).
- Operators can re-route a shipment to another carrier and see carrier errors.
- A one-off migration copies the last 2 years of shipment data (approx. 12 million rows) into the new service; after cut-over the monolith's shipping tables are read-only.

## Non-functional
- Creating a shipment must not add more than 200 ms to checkout (p95).
- Tracking updates: 40,000 shipments in flight; each polled every 15 minutes.
- No shipment may be lost or duplicated during cut-over; the cut-over must be reversible for 2 weeks.
- 99.9 % availability; if the shipping service is down, checkout must still succeed and shipments are created later.

## Constraints
- Python 3.12, existing MySQL 8 and RabbitMQ. Kubernetes. Team of 6 for 4 months. The monolith must keep deploying meanwhile.
