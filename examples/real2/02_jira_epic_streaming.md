Epic: VOD-2210 — Live-to-VOD clipping and playback for the sports app

Epic owner: Marcus Oyelaran
Sprint target: 2026.11 release train
Labels: video, playback, mobile, backend

Summary
Viewers of live matches want to clip the last 30 seconds of a stream and share it. Editorial wants to publish highlight reels within 2 minutes of a goal. Playback must keep working on 3G.

Stories

VOD-2211 As a viewer, I want to create a clip of the last 30 seconds of the live stream so that I can share it.
  Acceptance:
    Given I am watching a live stream
    When I tap "Clip" 
    Then a clip covering the previous 30 seconds is created within 10 seconds
    And I receive a shareable link
  Story points: 8

VOD-2212 As an editor, I want to trim a clip and publish it to the highlights rail so that fans see it quickly.
  Acceptance:
    Given a clip exists
    When I set in/out points and press Publish
    Then the clip appears in the highlights rail within 2 minutes
  Story points: 5

VOD-2213 As a viewer, I want playback to adapt to my bandwidth so that video does not stall on 3G.
  Acceptance:
    Given my bandwidth is 1 Mbps
    When I play a clip
    Then playback starts within 3 seconds and rebuffering is below 1% of watch time
  Story points: 13

VOD-2214 As a rights manager, I want clips to be geo-blocked according to the match's rights territory so that we do not breach league contracts.
  Acceptance:
    Given a match is licensed for UK and IE only
    When a viewer in FR requests the clip
    Then the request is refused with an explanatory message
  Story points: 5

VOD-2215 As an analyst, I want to see clip creation and play counts per match in the dashboard by the next morning.
  Story points: 3

VOD-2216 As a viewer, I want clips to be removed automatically when the rights window ends (typically 7 days after the match).
  Story points: 3

Technical notes (from grooming, 2026-09-08)
- Live ingest is already HLS via the existing LiveOrigin service; clips must be cut from the origin's segment store, not re-encoded from the player.
- Expect 50,000 concurrent viewers on a Premier League match, and up to 500 clip requests per second in the minute after a goal.
- Clips stored in S3, delivered via CloudFront. Signed URLs, 24-hour expiry.
- Rights data lives in the RightsDB (Postgres) owned by the Legal Tech team; we read it, never write.
- Mobile clients: iOS and Android, existing apps.
- Team of 4 backend + 2 mobile. Go for services, Python only for the analytics job.
- Must not store viewer IP addresses longer than 30 days (GDPR).
