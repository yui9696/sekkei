# RFC 0007: Rate-limited public API gateway

Status: draft · Authors: platform team · Reviewers: TBD

## Motivation
Partners call our internal services directly through ad-hoc NGINX rules. We need one gateway that authenticates partners, enforces per-partner quotas and produces usage data for billing.

## Goals
1. Partners authenticate with API keys (rotatable, two active keys per partner).
2. Per-partner quotas: requests per minute and per day, configurable by operators through an admin API; excess returns `429` with `Retry-After`.
3. Every request is logged with partner, route, status, latency; usage is aggregated hourly for billing.
4. Operators can enable/disable a partner immediately.

## Non-goals
- Replacing internal service-to-service auth (mTLS stays).
- A developer portal UI (later).

## Requirements
- Sustained 5,000 requests/s across all partners, p99 added latency under 10 ms.
- Quota decisions must be consistent across gateway instances (a partner must not get 2x its quota by hitting two instances).
- Losing usage records for billing is not acceptable; at-least-once delivery to the billing pipeline is fine (it de-duplicates by request id).
- 99.99 % availability; the gateway must keep serving if the admin API or the billing pipeline is down.

## Constraints
- Go 1.22. Redis cluster and Kafka exist. Runs on Kubernetes across two regions. Team of 4.

## Alternatives considered
- Envoy with ext_authz: rejected for now, we lack Envoy expertise. See appendix.

```json
{"example": "config", "quota": {"per_minute": 600, "per_day": 100000}}
```
