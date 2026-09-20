---
rfc: 0042
title: Matchmaking Service v2 for Skyforge Arena
authors: [platform-team]
status: proposed
created: 2026-09-08
---

# RFC 0042: Matchmaking Service v2

## Summary

Replace the in-monolith matchmaker with a standalone service that forms 5v5 matches from a queue of players using skill rating (MMR), region and party constraints, and hands the formed match to the game-server allocator.

## Motivation

The current matchmaker runs inside the game backend monolith, holds all queues in one process, and cannot be scaled or restarted without dropping every queued player. At the last season launch (2026-06-02) we had 180,000 players in queue, the process hit 100 % CPU and median wait time rose to 9 minutes.

## Goals

- Players enter a queue for a game mode and are placed in a match with 9 other players whose MMR is within a window that widens with wait time.
- Parties of up to 5 stay together on the same team.
- Players are only matched with players in the same region, unless they have waited more than 90 seconds, after which adjacent regions are allowed.
- Median wait time under 30 seconds at peak; p95 under 2 minutes.
- Queue state survives a restart of any single service instance; a player must not be silently dropped from the queue.
- Cheaters flagged by the anti-cheat service are matched only with other flagged players.

## Non-goals

- Ranked ladder computation (MMR updates stay in the stats service).
- Custom lobbies.

## Detailed design

### Queue entry

```json
POST /v2/queue
{
  "player_id": "p_91f3",
  "party_id": "party_2a",
  "mode": "ranked_5v5",
  "region": "eu-west",
  "mmr": 1840
}
```

Returns `202` with a ticket id. `DELETE /v2/queue/{ticket}` leaves the queue. Clients poll `GET /v2/queue/{ticket}` every 2 seconds or subscribe over WebSocket.

### Matching loop

Every 1 second per (mode, region) shard, the matcher selects candidate tickets and tries to form matches with team MMR difference under 50. The MMR window per ticket is:

```yaml
window:
  initial: 100
  growth_per_10s: 50
  max: 600
```

### Match handoff

A formed match is written to the `matches.formed` Kafka topic and the allocator responds on `matches.allocated` with a server address within 5 seconds; if no server is allocated in 20 seconds the players return to the head of the queue with their original wait time.

### Data

Tickets live in Redis (one hash per ticket, one sorted set per shard keyed by enqueue time). Formed matches are persisted to PostgreSQL for 30 days for support and analytics.

## Rollout plan

1. Shadow mode: v2 forms matches but v1 still decides; compare match quality for 2 weeks.
2. 5 % of EU traffic on v2 behind a feature flag.
3. 100 % EU, then NA, then APAC, one week apart.
4. Remove v1 after 30 days at 100 %.

## Capacity

- Peak 200,000 concurrent queued players across 3 regions and 4 modes.
- 4,000 queue entries per second at season launch.
- 20,000 matches formed per minute at peak.

## Operations

- Team: 3 engineers on the platform team plus 1 embedded SRE.
- Go 1.23, Redis Cluster and Kafka already operated by the platform team, Kubernetes in three regions.
- Alert on-call if median wait time exceeds 60 seconds for 5 minutes.

## Alternatives considered

- Open Match (Google): rejected because it requires its own Kubernetes operator and our SRE team has no capacity for it this season.
- Keep the matchmaker in the monolith and shard by region: rejected because it does not solve restarts.

## Open questions

- Should parties with a wide MMR spread (over 400) be matched at the party's maximum or average MMR?
- Do we need a separate queue for console cross-play?
