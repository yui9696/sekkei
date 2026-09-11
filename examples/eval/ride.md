# Ride dispatch backend

A city taxi cooperative needs a backend that matches ride requests to nearby drivers and tracks each trip.

## Functional
- Riders request a ride from the mobile app with a pickup and a drop-off location; the request is offered to the nearest available drivers.
- Drivers accept or decline an offer within 15 seconds; after three declines the request is offered to the next batch of drivers.
- Drivers send their GPS position every 5 seconds while online; riders see the assigned driver's position in real time.
- The system computes the fare from distance and time at the end of the trip and charges the rider's card through Stripe.
- Riders can rate a trip and see their trip history; operators can view all active trips on a dashboard.
- Operators receive an alert when no driver accepts a request within 2 minutes.

## Non-functional
- 300 concurrent trips and 2,000 online drivers at peak; position updates must be visible to the rider within 2 s p95.
- No accepted ride request or completed trip is lost on a crash.
- A driver's position history is kept 30 days for dispute handling, then deleted.

## Constraints
- Go 1.22, PostgreSQL with PostGIS available, Redis available. Team of 4. Kubernetes cluster in a single region.
- Riders and drivers authenticate with the company's OIDC provider; operators use the same provider with an operator role.

## Out of scope
- Route navigation and maps rendering (handled by the mobile apps).
