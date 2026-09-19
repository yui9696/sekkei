# 社内 Wiki 検索 API

## 機能要件
- ユーザーは keyword で Wiki ページを full-text search できること。結果は 500 ms 以内に返すこと。
- 検索結果は permission に従い、閲覧権限のないページは表示しないこと。
- 管理者は index を rebuild できること。rebuild は 1 時間以内に完了すること。
- 1 日あたり 20,000 queries、peak は 30 requests/s とすること。

## 制約
- チームは 3 名。Python。PostgreSQL が利用可能。既存の Confluence から夜間に同期すること。
