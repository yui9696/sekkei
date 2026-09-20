# Outbound webhooks for the billing platform

## Requirements
- Customers register webhook endpoints (URL + secret) in the dashboard; up to 10 endpoints per account.
- Every invoice event is delivered to each matching endpoint as a signed JSON payload; the signature is HMAC-SHA256 over the timestamp and body, sent in the X-Signature header.
- Customers can rotate the secret; both the old and new secret are valid for 24 hours.
- Deliveries are retried with exponential backoff for up to 3 days; an endpoint that fails continuously for 3 days is disabled automatically and the owner is emailed.
- Peak: 500 events per second.

## Constraints
- Python, PostgreSQL, Redis available. Team: 4 engineers.
