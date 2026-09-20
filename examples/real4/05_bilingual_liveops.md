# LiveOps Event Service / ライブイベント基盤 — 設計前提メモ

Team: Tokyo (server) + Berlin (tools/data). 会議は英語、仕様は各担当の言語で書く。Both columns are normative. / 日英どちらも正です。

## 1. Goal / 目的

We run time-limited in-game events (login bonus, ranked season, gacha banner) for a mobile RPG with 2.3M MAU. Today each event is a hard-coded server deploy. We want events to be data: planners configure them in a tool, the server activates them on schedule, and rewards are granted without a deploy.

現状はイベントごとにサーバーをデプロイしている。プランナーがツールで設定し、サーバーがスケジュールで自動的に開始・終了し、報酬付与にデプロイを不要にする。

## 2. Requirements / 要件

### 2.1 Event definition / イベント定義

- EV-1. プランナーは管理ツールでイベント(種別・開始/終了日時・対象プラットフォーム・報酬テーブル)を作成し、下書き→レビュー→承認→公開の状態を持つこと。公開はレビュー担当とは別の承認者が行うこと。
- EV-2. An event definition is a versioned JSON document validated against a schema; a published version is immutable — a change creates a new version, and the server switches versions only at a boundary the planner chose (immediately, or at the next daily reset 04:00 JST).
- EV-3. イベント開始・終了はサーバー時刻(UTC)を正とし、クライアント時刻を信用しないこと。開始・終了の反映は全リージョンで30秒以内。
- EV-4. Events can be scheduled up to 90 days ahead; the tool shows a calendar of overlapping events and warns (does not block) when two events of the same kind overlap.

### 2.2 Progress and rewards / 進捗と報酬

- EV-5. プレイヤーのイベント進捗(ログイン日数、討伐数、ランクポイント)はプレイの度に更新され、`GET /v1/events/{event_id}/progress` で1秒以内に取得できること。
- EV-6. Rewards are granted exactly once per player per milestone, even if the client retries or two game servers process the same player concurrently; the grant is recorded with the event version that produced it.
- EV-7. イベント終了後の報酬受け取り期限は14日間。期限内に未受領の報酬はメールボックス(既存の `mailbox-service`)へ送ること。期限切れの報酬は付与してはならない。
- EV-8. Ranked seasons: leaderboards per event with rank tiers; the top 1,000 must be exact, the rest may be approximate (±1 %) and refreshed every 60 seconds.

### 2.3 Operations / 運用

- EV-9. プランナーは公開中のイベントを緊急停止できること(kill switch)。停止から60秒以内に全サーバーで新規進捗の更新と報酬付与が止まること。停止はロールバック可能であること。
- EV-10. A dry-run mode evaluates an event definition against a copy of yesterday's player data and reports how many players would hit each milestone and the total reward cost, before publishing.
- EV-11. すべての定義変更・公開・停止操作は操作者と共に記録し、2年間保持すること。
- EV-12. Data team (Berlin) receives every progress update and reward grant as an event on the existing Kafka cluster (topic `liveops.events`) within 5 minutes; the schema is registered in the schema registry and changes are backward compatible.

### 2.4 Non-functional / 非機能

- NF-1. ピーク: イベント開始直後の5分間に 120,000 req/s(進捗更新)、通常時 8,000 req/s。
- NF-2. Availability 99.95 % for progress reads and reward grants; the planner tool may be down for maintenance.
- NF-3. 個人情報はプレイヤーIDのみ扱い、氏名・メールアドレスは本基盤に持ち込まないこと。
- NF-4. Regions: JP (primary) and EU; a player's data lives in one region only; leaderboards are per region.

## 3. Constraints / 制約

- サーバー: Go、既存の Redis Cluster と Aurora MySQL、Kubernetes(EKS)。プランナーツール: TypeScript/React、Berlin チームが担当。
- The existing `mailbox-service`, `player-service` and `auth-service` are called over gRPC; no new synchronous dependency on `payment-service`.
- Team: Tokyo 4 server engineers, Berlin 2 tools engineers + 1 data engineer, 1 SRE shared.
- Launch: 2027年1月の周年イベントで使用(first event 2027-01-15)。

## 4. Not in scope / 対象外

- ガチャの確率テーブルそのもの(法務レビュー済みの既存モジュールを流用)。
- Push notifications to players about events (marketing tool).

## 5. Open questions / 未決事項

- Should the 04:00 JST daily reset also apply to EU players, or should EU use 04:00 CET?
- 承認者が不在の場合の代理承認をどうするか。
