"""Japanese requirements -> the canonical English shape the engine reads.

No translation is claimed. This is a glossary (actors, verbs, domain nouns, qualities,
technologies), a number/unit grammar (「300ms以内」→ ``within 300 ms``, 「1万件/秒」→
``10000 requests/s``, 「3名のチーム」→ ``Team of 3.``), a modality lexicon (「しなければ
ならない」→ must) and a particle-driven reordering (「利用者は注文を登録できる」→ ``Users can
register orders``). Every sentence is rewritten deterministically and the rewrite is
returned next to the original so a reader can check it; words the glossary does not know
are listed as *untranslated* and dropped from the English text rather than guessed.

The engine's own vocabulary is English, so this is the one place where another language
enters. The same mechanism (a glossary plus a reorder rule) would serve other SOV
languages; the tables here are Japanese only.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_JA_CHAR = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")


def is_japanese(text: str) -> bool:
    """True when at least a tenth of the letters are kana or kanji."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if _JA_CHAR.match(c)) >= max(1, len(letters) // 10)


# ---------------------------------------------------------------------------
# Glossary: surface form -> (english, role)
# roles: actor | verb | noun | modal | quality | tech | time | other
# ---------------------------------------------------------------------------

ACTORS = {
    "利用者": "users", "ユーザー": "users", "ユーザ": "users", "エンドユーザー": "users", "会員": "members",
    "管理者": "admins", "システム管理者": "admins", "運用者": "operators", "運用担当者": "operators", "運用担当": "operators",
    "オペレーター": "operators", "オペレータ": "operators", "開発者": "developers", "エンジニア": "engineers",
    "顧客": "customers", "お客様": "customers", "クライアント": "clients", "取引先": "customers", "テナント": "tenants",
    "スタッフ": "staff", "担当者": "staff", "従業員": "employees", "社員": "employees", "職員": "staff",
    "マネージャー": "managers", "管理職": "managers", "上長": "managers", "上司": "managers", "責任者": "managers",
    "店舗": "stores", "店員": "staff", "販売者": "sellers", "出品者": "sellers", "購入者": "buyers", "買い手": "buyers",
    "医師": "doctors", "患者": "patients", "看護師": "nurses", "薬剤師": "staff",
    "教師": "teachers", "講師": "teachers", "学生": "students", "生徒": "students", "受講者": "learners", "保護者": "guests",
    "ドライバー": "drivers", "運転手": "drivers", "乗客": "passengers", "配送員": "drivers", "配達員": "drivers",
    "訪問者": "visitors", "ゲスト": "guests", "閲覧者": "readers", "読者": "readers", "編集者": "editors", "著者": "authors",
    "審査者": "reviewers", "承認者": "managers", "申請者": "users", "市民": "citizens", "住民": "citizens",
    "外部サービス": "external services", "外部システム": "external services", "内部サービス": "internal services",
    "他システム": "external services", "連携先": "external services", "基幹システム": "external services",
    "デバイス": "devices", "端末": "devices", "機器": "devices", "センサー": "sensors", "センサ": "sensors",
    "車両": "vehicles", "トラック": "trucks", "ロボット": "devices", "バッチ": "job", "ジョブ": "job",
    "アプリ": "app", "アプリケーション": "application", "モバイルアプリ": "mobile app", "ツール": "tool", "コマンド": "command",
    "システム": "system", "本システム": "the system", "サービス": "service", "チーム": "team", "分析者": "analysts",
    "エージェント": "agents", "ボット": "bot",
}

VERBS = {
    "登録": "register", "新規登録": "register", "作成": "create", "追加": "add", "投稿": "publish", "公開": "publish",
    "削除": "delete", "取り消し": "cancel", "取消": "cancel", "キャンセル": "cancel", "更新": "update", "編集": "edit",
    "変更": "change", "修正": "edit", "設定": "configure", "一覧表示": "list", "一覧": "list", "検索": "search",
    "絞り込み": "filter", "絞込": "filter", "閲覧": "view", "参照": "view", "表示": "view", "確認": "check",
    "取得": "get", "送信": "send", "送付": "send", "通知": "notify", "配信": "deliver", "再送": "retry",
    "出力": "export", "エクスポート": "export", "取り込み": "import", "取込": "import", "インポート": "import",
    "アップロード": "upload", "ダウンロード": "download", "承認": "approve", "却下": "reject", "差し戻し": "reject",
    "予約": "book", "注文": "order", "発注": "order", "支払い": "pay", "支払": "pay", "決済": "pay", "返金": "refund",
    "発送": "ship", "出荷": "ship", "割り当て": "assign", "割当": "assign", "アサイン": "assign", "招待": "invite",
    "共有": "share", "保存": "save", "集計": "aggregate", "計算": "compute", "算出": "compute", "生成": "generate",
    "記録": "record", "監視": "track", "追跡": "track", "認証": "authenticate", "認可": "authorize", "ログイン": "login",
    "評価": "rate", "有効化": "enable", "無効化": "disable", "同期": "sync", "変換": "convert", "解析": "parse",
    "スケジュール": "schedule", "検証": "validate", "署名": "sign", "印刷": "print", "集約": "aggregate",
    "移動": "move", "転記": "move", "読み込み": "load", "入力": "submit", "申請": "submit", "提出": "submit",
    "受付": "accept", "受け付け": "accept", "受信": "receive", "処理": "process", "実行": "run", "起動": "trigger",
    "要約": "summarize", "分類": "classify", "推論": "predict", "予測": "predict", "スキャン": "scan", "アーカイブ": "archive",
    "廃棄": "purge", "レポート出力": "export", "管理": "manage", "計測": "measure", "測定": "measure", "回収": "receive",
    "紐付け": "assign", "紐づけ": "assign", "照会": "query", "問い合わせ": "request", "リクエスト": "request",
    "オファー": "offer", "マッチング": "match", "課金": "charge", "請求": "charge", "タグ付け": "tag", "抽出": "extract",
    "分割": "split", "索引": "index", "レンダリング": "render", "描画": "render", "ローテーション": "rotate",
    "失効": "revoke", "取り下げ": "revoke", "承認依頼": "request", "コメント": "comment", "利用": "use", "使用": "use",
    "動かす": "run", "稼働": "run", "運用": "operate", "適用": "apply", "反映": "apply", "応答": "respond", "返す": "return",
    "呼び出す": "call", "呼び出し": "call", "連携": "integrate", "接続": "connect", "受け取る": "receive", "受け取り": "receive",
    "見る": "view", "書く": "write", "読む": "read", "貼る": "attach", "貼り付け": "attach",
    "並べ替え": "sort", "ソート": "sort", "絞る": "filter", "選ぶ": "choose", "選択": "choose", "指定": "set", "決定": "set",
    "開始": "start", "終了": "close", "完了": "complete", "停止": "stop", "再開": "resume", "中断": "cancel", "破棄": "discard",
    "復元": "restore", "復旧": "restore", "巻き戻し": "rollback", "検知": "detect", "検出": "detect", "判定": "check",
    "アラート": "alert", "警告": "alert", "エスカレーション": "escalate", "返信": "reply", "投票": "vote", "採点": "grade",
    "出題": "publish", "受験": "take", "提案": "propose", "推薦": "recommend", "レコメンド": "recommend", "翻訳": "translate",
    "圧縮": "compress", "展開": "extract", "配布": "distribute", "デプロイ": "deploy", "移行": "migrate", "取り消す": "cancel",
}

NOUNS = {
    "注文": "orders", "受注": "orders", "商品": "products", "製品": "products", "在庫": "stock", "在庫数": "stock counts",
    "顧客情報": "customer records", "顧客データ": "customer records", "請求書": "invoices", "見積書": "quotes", "見積": "quotes",
    "支払い情報": "payment details", "カード情報": "card details", "決済情報": "payment details", "通知": "notifications",
    "メール": "email", "電子メール": "email", "ファイル": "files", "画像": "images", "写真": "photos", "動画": "videos",
    "音声": "audio", "文書": "documents", "ドキュメント": "documents", "資料": "documents", "PDF": "pdf",
    "レポート": "reports", "報告書": "reports", "帳票": "reports", "予約": "bookings", "配送": "shipping", "配送状況": "shipping status",
    "イベント": "events", "ログ": "logs", "履歴": "history", "変更履歴": "change log", "操作履歴": "audit log", "監査ログ": "audit log",
    "権限": "permissions", "ロール": "roles", "役割": "roles", "トークン": "token", "パスワード": "password", "APIキー": "api keys",
    "セッション": "session", "カート": "cart", "アカウント": "accounts", "プロフィール": "profiles", "設定情報": "settings",
    "ダッシュボード": "dashboard", "地図": "map", "位置情報": "location", "現在地": "position", "位置": "position",
    "予定": "schedule", "カレンダー": "calendar", "会議室": "rooms", "部屋": "rooms", "診察予約": "appointments", "診察": "appointments",
    "処方": "prescriptions", "カルテ": "records", "売上": "sales", "売上データ": "sales", "給与": "payroll", "勤怠": "attendance",
    "出退勤": "attendance", "契約": "contracts", "案件": "deals", "チケット": "tickets", "問い合わせ内容": "inquiries",
    "メッセージ": "messages", "チャット": "chat", "記事": "articles", "コメント": "comments", "タグ": "tags", "カテゴリ": "categories",
    "キュー": "queue", "データベース": "database", "テーブル": "tables", "レコード": "records", "データ": "data", "件数": "counts",
    "統計": "statistics", "集計結果": "aggregates", "グラフ": "chart", "チャート": "chart", "画面": "screen", "ページ": "pages",
    "フォーム": "forms", "テンプレート": "templates", "コンテンツ": "content", "お知らせ": "announcements", "クーポン": "coupons",
    "ポイント": "points", "ランキング": "ranking", "レビュー": "reviews", "評価": "ratings", "お気に入り": "favourites",
    "検索結果": "search results", "キーワード": "keywords", "添付ファイル": "attachments", "添付": "attachments",
    "バックアップ": "backups", "スナップショット": "snapshots", "バージョン": "versions", "設定": "settings", "構成": "configuration",
    "秘密鍵": "secrets", "秘密情報": "secrets", "シークレット": "secrets", "証明書": "certificates", "署名": "signature",
    "Webhook": "webhooks", "ウェブフック": "webhooks", "エンドポイント": "endpoints", "URL": "url", "ID": "id",
    "個人情報": "personal data", "機微情報": "personal data", "マイナンバー": "personal data", "医療情報": "personal data",
    "温度": "temperature", "湿度": "humidity", "測定値": "readings", "計測値": "readings", "読み取り値": "readings",
    "テレメトリ": "telemetry", "アラート": "alerts", "警報": "alerts", "閾値": "threshold", "しきい値": "threshold",
    "従業員情報": "employee records", "学習履歴": "history", "成績": "grades", "課題": "assignments", "教材": "materials",
    "講座": "courses", "コース": "courses", "テスト": "tests", "回答": "answers", "質問": "questions", "投票": "votes",
    "支払い": "payments", "決済": "payments", "請求": "invoices", "料金": "charges", "金額": "amount", "残高": "balance",
    "口座": "accounts", "取引": "transactions", "トランザクション": "transactions", "領収書": "receipts", "返品": "returns",
    "配達": "delivery", "経路": "routes", "ルート": "routes", "車両情報": "vehicle records", "運行": "trips", "乗車": "rides",
    "エンティティ": "entities", "ワークフロー": "workflow", "承認フロー": "approval workflow", "稟議": "approval workflow",
    "状態": "state", "ステータス": "status", "進捗": "progress", "タスク": "tasks", "プロジェクト": "projects", "マイルストーン": "milestones",
    "モデル": "model", "埋め込み": "embeddings", "要約": "summaries", "翻訳": "translations", "言語": "language",
    "顧客": "customers", "利用者": "users", "ユーザー": "users", "管理者": "admins",   # as objects: 「利用者を招待できる」
    "倉庫": "warehouses", "入出庫": "stock movements", "入庫": "receipts", "出庫": "issues", "品目": "items", "数量": "quantity",
    "棚": "bins", "在庫管理": "stock management", "在庫品目": "stock items", "発注": "purchase orders", "納品": "deliveries",
    "従業員": "employees", "部署": "departments", "組織": "organisations", "拠点": "sites", "支店": "branches", "本部": "head office",
    "患者情報": "patient records", "予約枠": "slots", "枠": "slots", "空き": "availability", "座席": "seats", "席": "seats",
    "商品情報": "product records", "価格": "prices", "単価": "unit price", "税": "tax", "送料": "shipping fee", "割引": "discounts",
    "仕様": "specification", "要件": "requirements", "設計": "design", "画面遷移": "screens",
}

QUALITIES = {
    "失われない": "must never be lost", "欠損しない": "must never be lost", "消失しない": "must never be lost", "紛失しない": "must never be lost",
    "失われてはならない": "must never be lost", "二重に": "double-applied", "重複して": "duplicate", "二重適用": "double-applied",
    "二重登録": "double-applied", "重複": "duplicate", "冪等": "idempotent", "べき等": "idempotent", "整合性": "consistency",
    "一貫性": "consistency", "同時に": "concurrently", "並行": "concurrent", "同時": "concurrent", "競合": "concurrent",
    "可用性": "availability", "稼働率": "availability", "ダウンタイム": "downtime", "無停止": "zero downtime", "冗長": "redundant",
    "フェイルオーバー": "failover", "障害時": "on failure", "障害": "failure", "復旧": "recovery", "耐障害": "resilient",
    "遅延": "latency", "レイテンシ": "latency", "応答時間": "latency", "応答": "respond", "スループット": "throughput",
    "性能": "performance", "パフォーマンス": "performance", "高速": "fast", "高負荷": "high load", "ピーク": "peak",
    "暗号化": "encrypted", "秘匿": "encrypted", "安全": "secure", "セキュリティ": "security", "監査": "audit",
    "権限管理": "permissions", "アクセス制御": "authorization", "多要素認証": "mfa", "二段階認証": "mfa",
    "メトリクス": "metrics", "監視": "metrics", "モニタリング": "metrics", "構造化ログ": "structured logs", "ログ出力": "logs",
    "ヘルスチェック": "health", "死活監視": "health", "トレース": "tracing", "スケール": "scale", "スケーラビリティ": "scalability",
    "水平スケール": "horizontal scaling", "ステートレス": "stateless", "コスト": "cost", "費用": "cost", "予算": "budget",
    "安価": "cheap", "保持期間": "retention", "保存期間": "retention", "保持": "retention", "削除要求": "delete their data",
    "忘れられる権利": "delete their data", "個人情報保護": "gdpr", "コンプライアンス": "compliance", "法令": "compliance",
    "影響を与えない": "must not affect others", "影響しない": "must not affect others", "遅延させない": "must not delay others",
    "ブロックしない": "must not block others", "妨げない": "must not block others", "分離": "isolated",
    "シンプル": "simple", "簡素": "minimal", "使いやすい": "easy to use", "ドキュメント整備": "documentation",
    "リアルタイム": "real-time", "即時": "immediately", "即座": "immediately", "非同期": "asynchronously", "順序": "order",
    "再試行": "retry", "リトライ": "retry", "指数バックオフ": "exponential backoff", "バックオフ": "backoff",
    "全文検索": "full-text search", "レート制限": "rate limit", "流量制限": "rate limit", "スロットリング": "throttling",
    "キャッシュ": "cache", "圧縮": "compressed", "バージョン管理": "versioned", "多言語": "i18n", "国際化": "i18n",
    "オフライン": "offline", "バックアップ": "backup", "災害対策": "disaster recovery", "DR": "disaster recovery",
    "目標復旧時間": "rto", "目標復旧時点": "rpo", "テスト": "tests", "自動テスト": "automated tests", "CI": "ci",
    "機能フラグ": "feature flags", "段階的": "gradual", "マルチテナント": "multi-tenant", "テナント分離": "tenant isolation",
    "ネットワーク": "network", "帯域": "bandwidth", "容量": "capacity", "ストレージ": "storage", "永続化": "persisted",
    "ロールバック": "rollback", "移行": "migration", "データ移行": "data migration", "既存システム": "legacy system",
    "レガシー": "legacy", "互換性": "compatibility", "後方互換": "backward compatible", "失われ": "lost", "失う": "lose",
    "下回る": "falls below", "下回った": "falls below", "上回る": "exceeds", "超える": "exceeds", "超えた": "exceeds",
    "発注点": "reorder level", "在庫切れ": "out of stock", "欠品": "out of stock", "遅い": "slow", "遅くても": "at most",
    "把握": "track", "背後": "behind", "既存": "existing", "同一": "same", "順番": "order", "順序通り": "in order", "一度だけ": "exactly once", "少なくとも一度": "at least once",
    "取りこぼさない": "must never be lost", "取りこぼし": "lost", "落とさない": "must never be lost", "確実に": "reliably",
    "エラー": "errors", "例外": "errors", "タイムアウト": "timeout", "接続数": "connections", "同時接続": "concurrent connections",
    "レスポンス": "response", "処理時間": "latency", "処理速度": "throughput", "秒間": "per second", "毎秒": "per second",
    "平文": "plaintext", "平文で": "in plaintext", "ハッシュ化": "hashed", "マスキング": "masked", "匿名化": "anonymised",
    "開発": "develop", "実装": "implement", "運用中": "in production", "本番": "production", "検証環境": "staging",
}

TECH = {
    "コンテナ": "containers", "オンプレ": "on-prem", "オンプレミス": "on-prem", "単一リージョン": "single region",
    "標準ライブラリのみ": "standard library only", "標準ライブラリ": "standard library", "サーバーレス": "serverless",
    "サーバレス": "serverless", "クラウド": "cloud", "仮想マシン": "vm", "ロードバランサー": "load balancer",
    "ロードバランサ": "load balancer", "イングレス": "ingress", "ネットワークなし": "no network", "オブジェクトストレージ": "object storage",
    "メッセージブローカー": "broker", "メッセージキュー": "queue", "外部認証基盤": "identity provider", "認証基盤": "identity provider",
    "シングルサインオン": "sso", "時系列": "time-series", "ベクトル検索": "vector search", "全文検索エンジン": "search engine",
    "リレーショナルデータベース": "relational database", "データベースなし": "no database", "モバイル": "mobile",
    "スマートフォン": "mobile app", "ブラウザ": "browser", "ウェブ": "web", "Web": "web", "デスクトップ": "desktop",
    "組み込み": "embedded", "ラズパイ": "raspberry pi", "サーバー": "server", "サーバ": "server", "購買": "purchasing",
    "仕入先": "suppliers", "仕入": "purchasing", "会計": "accounting", "経理": "accounting", "人事": "hr", "マーケティング": "marketing",
    "CRM": "crm", "ERP": "erp", "基幹": "erp", "販売管理": "sales management", "生産管理": "production planning",
}

TIME = {
    "毎日": "daily", "日次": "daily", "毎週": "weekly", "週次": "weekly", "毎月": "monthly", "月次": "monthly",
    "毎時": "hourly", "毎分": "every minute", "夜間": "nightly", "深夜": "nightly", "定期的に": "periodically", "定期": "periodic",
    "月間": "monthly", "年間": "yearly", "営業時間": "business hours", "営業日": "business days", "即日": "same day",
}

MODALS = {
    "しなければならない": "must", "しなくてはならない": "must", "なければならない": "must", "ねばならない": "must",
    "必須": "must", "必ず": "always", "常に": "always", "決して": "never", "禁止": "must not", "してはならない": "must not",
    "してはいけない": "must not", "べきである": "should", "べき": "should", "望ましい": "should", "推奨": "should",
    "できる": "can", "可能": "can", "できること": "can", "できるようにする": "can", "してもよい": "may", "任意": "optionally",
    "将来的に": "later", "あれば良い": "nice to have", "あるとよい": "nice to have", "こと": "",
}

OTHER = {
    "および": "and", "及び": "and", "かつ": "and", "または": "or", "又は": "or", "もしくは": "or", "ただし": "but", "場合": "when",
    "とき": "when", "際": "when", "後": "after", "前": "before", "以降": "after", "から": "from", "まで": "until", "ごと": "each",
    "毎": "each", "すべて": "all", "全て": "all", "全ての": "all", "すべての": "all", "各": "each", "任意の": "any", "特定の": "specific",
    "新しい": "new", "既存の": "existing", "自分の": "their own", "自身の": "their own", "複数": "multiple", "単一": "single",
    "一つ": "one", "1つ": "one", "自動的に": "automatically", "自動で": "automatically", "手動で": "manually", "直接": "directly",
    "経由で": "via", "経由": "via", "による": "by", "によって": "by", "として": "as", "向け": "for", "用": "for", "内": "within",
    "外": "outside", "間": "between", "中": "during", "上": "on", "下": "under", "対象": "target", "対象外": "out of scope",
    "範囲": "scope", "範囲外": "out of scope", "含む": "including", "含まない": "excluding", "除く": "excluding",
    "同じ": "same", "異なる": "different", "他の": "other", "別の": "another", "最新": "latest", "過去": "past",
    "現在": "current", "今後": "future", "以内に": "within", "以内": "within", "以下": "at most", "以上": "at least", "未満": "under",
    "超": "over", "程度": "about", "約": "about", "最大": "up to", "最小": "at least", "平均": "average", "合計": "total",
    "担当": "assigned", "状況": "status", "結果": "result", "内容": "content", "情報": "information", "一覧": "list",
    "詳細": "details", "概要": "summary", "種類": "type", "名称": "name", "名前": "name", "番号": "number", "日付": "date",
    "日時": "datetime", "期間": "period", "期限": "deadline", "締切": "deadline", "条件": "condition", "理由": "reason",
    "件": "items", "人": "users", "名": "users", "台": "devices", "社": "customers", "拠点": "sites", "店": "stores",
    "回": "times", "行": "rows", "枚": "images", "本": "items", "通": "messages", "箇所": "places",
    "が": "", "は": "", "を": "", "に": "", "へ": "", "で": "", "と": "", "の": "", "も": "", "や": "", "より": "", "など": "etc.",
    "する": "", "した": "", "され": "", "される": "", "させる": "", "れる": "", "られる": "", "ます": "", "です": "", "である": "", "だ": "",
    "ある": "", "いる": "", "なる": "", "行う": "", "行える": "can", "おこなう": "", "対して": "for", "について": "about", "関する": "about",
    "ため": "for", "ように": "so that", "よう": "", "また": "also", "さらに": "also", "なお": "note", "その": "the", "この": "this",
    "それ": "it", "これ": "this", "ない": "not", "なし": "none", "無し": "none", "有り": "with", "あり": "with",
}

# A surface form may have several readings (「注文」 is the verb *order* and the noun *orders*);
# the tokeniser keeps them all and the particle that follows decides.
GLOSSARY: dict[str, dict[str, str]] = {}
for _table, _role in ((OTHER, "other"), (TIME, "time"), (TECH, "tech"), (QUALITIES, "quality"), (NOUNS, "noun"),
                      (VERBS, "verb"), (MODALS, "modal"), (ACTORS, "actor")):
    for _k, _v in _table.items():
        GLOSSARY.setdefault(_k, {})[_role] = _v
_KEYS = sorted(GLOSSARY, key=len, reverse=True)
_GLOSS_RE = re.compile("|".join(re.escape(k) for k in _KEYS))
#: inflection tails after a verb/quality stem, consumed silently (「登録できる」「送信される」「失われず」)
_TAIL_RE = re.compile(r"(?:されない|されず|しない|せず|できない|できず|ない|なく|ず)|(?:される|され|させる|させ|できる|でき|して|した|する|します|しています|しました|られる|られ|れる|れ|る|た|て|き|し|ます|です|である|だ)+")
_NEG_RE = re.compile(r"^(?:されない|されず|しない|せず|できない|できず|ない|なく|ず)")
_PASSIVE_RE = re.compile(r"^(?:される|され|られる|られ|れる)")

SECTION_MAP = [
    (("対象外", "スコープ外", "非目標", "範囲外", "やらないこと", "除外"), "Out of scope"),
    (("非機能", "品質", "性能要件", "運用要件", "NFR"), "Non-functional"),
    (("制約", "前提", "環境", "技術スタック", "技術", "条件", "チーム"), "Constraints"),
    (("機能", "要件", "ユースケース", "ユーザーストーリー", "できること", "スコープ", "範囲"), "Functional"),
]

# ---------------------------------------------------------------------------
# Numbers and units
# ---------------------------------------------------------------------------

_JA_NUM = r"(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<big>万|億)?"
_UNIT_MAP = [
    (r"ミリ秒|ms", "ms"), (r"秒間|秒", "s"), (r"分間|分", "min"), (r"時間", "h"), (r"日間|日", "days"), (r"週間", "weeks"),
    (r"ヶ月|か月|カ月|ヵ月", "months"), (r"年間|年", "years"), (r"%|％|パーセント", "%"), (r"KB|MB|GB|TB", None), (r"バイト", "bytes"),
]
_PER = {"秒": "/s", "分": "/min", "時間": "/h", "日": "/day", "月": "/month"}
_COUNTER = {"件": "requests", "回": "requests", "リクエスト": "requests", "イベント": "events", "メッセージ": "messages", "通": "messages",
            "台": "devices", "人": "users", "名": "users", "社": "customers", "拠点": "sites", "店舗": "stores", "行": "rows",
            "レコード": "records", "ファイル": "files", "枚": "images", "本": "items", "個": "items", "点": "items", "件数": "items",
            "ユーザー": "users", "利用者": "users", "顧客": "customers", "デバイス": "devices", "センサー": "sensors", "端末": "devices",
            "車両": "vehicles", "商品": "products", "注文": "orders", "文書": "documents", "ドキュメント": "documents", "テナント": "tenants",
            "店": "stores", "端末台": "devices", "エンドポイント": "endpoints", "接続": "connections", "同時接続": "concurrent connections"}


def _num(m: re.Match) -> str:
    n = float(m.group("num").replace(",", ""))
    big = m.group("big")
    if big == "万":
        n *= 10_000
    elif big == "億":
        n *= 100_000_000
    return str(int(n)) if n.is_integer() else f"{n:g}"


def numbers(s: str) -> str:
    """Rewrite Japanese quantities into the engine's number grammar. Comparators move in front."""
    s = re.sub(r"チーム\s*(?:は|が|:|：)?\s*(\d+)\s*(?:名|人)", r"Team of \1", s)
    s = re.sub(r"(?:開発者|エンジニア|メンバー|開発メンバー)\s*(?:は|が|:|：)?\s*(\d+)\s*(?:名|人)", r"Team of \1", s)
    s = re.sub(r"(\d+)\s*(?:名|人)\s*(?:の|で)?\s*(?:チーム|体制|開発体制|開発)", r"Team of \1", s)
    # 「N 秒ごと」「N 分おき」→ every N seconds (before the plain duration rule eats the number)
    s = re.sub(_JA_NUM + r"\s*(?P<unit>秒|分|時間)\s*(?:ごと|毎|おき|間隔)(?:に|で)?",
               lambda m: f"every {_num(m)} {'seconds' if m.group('unit') == '秒' else 'minutes' if m.group('unit') == '分' else 'hours'} ", s)
    # rate: 「毎秒 1万件」「1,000件/秒」「1000リクエスト/秒」「秒間 500 件」
    def rate(m: re.Match) -> str:
        return f"{_num(m)} {_COUNTER.get(m.group('what') or '', 'requests')}{_PER[m.group('per')]}"
    counters = "|".join(sorted(map(re.escape, _COUNTER), key=len, reverse=True))
    s = re.sub(_JA_NUM + r"\s*(?P<what>" + counters + r")?\s*(?:/|毎|あたり|につき|ごと)\s*(?P<per>秒|分|時間|日|月)", rate, s)
    s = re.sub(r"(?:毎|秒間|分間)?(?P<per>秒|分|時間|日|月)(?:間|あたり|に|毎)?\s*" + _JA_NUM + r"\s*(?P<what>" + counters + r")",
               lambda m: f"{_num(m)} {_COUNTER.get(m.group('what'), 'requests')}{_PER[m.group('per')]}", s)
    # percentiles: 「p95で」 stays; 「95パーセンタイル」
    s = re.sub(r"(\d{2,3})\s*パーセンタイル", r"p\1", s)
    # duration/latency with comparator suffix: 「300ms以内」「5秒以下」「10分未満」「99.9%以上」
    units = "|".join(u for u, _ in _UNIT_MAP)

    def dur(m: re.Match) -> str:
        unit = m.group("unit")
        en = next((e for rx, e in _UNIT_MAP if re.fullmatch(rx, unit)), None) or unit
        cmp = {"以内": "within", "以下": "at most", "未満": "under", "以上": "at least", "超": "over", "まで": "up to", "程度": "about"}.get(m.group("cmp") or "", "")
        core = f"{_num(m)} {en}"
        return f"{cmp} {core}" if cmp else core
    s = re.sub(_JA_NUM + r"\s*(?P<unit>" + units + r")\s*(?P<cmp>以内|以下|未満|以上|超|まで|程度)?(?:に|で)?", dur, s)
    # 「20万件の品目」「1,000人のユーザー」: the noun after の names the counted thing
    noun_keys = "|".join(sorted(map(re.escape, [k for k in NOUNS] + [k for k in ACTORS]), key=len, reverse=True))

    def cnt_of(m: re.Match) -> str:
        w = m.group("what2")
        en = NOUNS.get(w) or ACTORS.get(w) or "items"
        return f"{_num(m)} {en}"
    s = re.sub(_JA_NUM + r"\s*(?:件|人|名|台|個|社|本|点)\s*の\s*(?P<what2>" + noun_keys + r")", cnt_of, s)
    # counts with a counter: 「2,000台」「5名」「20万件」
    def cnt(m: re.Match) -> str:
        what = _COUNTER.get(m.group("what"), "items")
        tail = m.group("tail") or ""
        cmp = {"以内": "at most", "以下": "at most", "未満": "under", "以上": "at least", "超": "over"}.get(m.group("cmp") or "", "")
        # 「5名のチーム」→ Team of 5
        if tail:
            return f"Team of {_num(m)}"
        return f"{cmp} {_num(m)} {what}".strip()
    s = re.sub(_JA_NUM + r"\s*(?P<what>" + counters + r")\s*(?P<cmp>以内|以下|未満|以上|超)?(?P<tail>の?(?:チーム|体制|開発体制))?", cnt, s)
    return s


# ---------------------------------------------------------------------------
# Sentence rewriting
# ---------------------------------------------------------------------------


@dataclass
class Token:
    text: str
    role: str        # actor | verb | noun | modal | quality | tech | time | other | ascii | unknown | particle
    src: str = ""
    alts: dict[str, str] = field(default_factory=dict)
    negated: bool = False
    passive: bool = False
    can: bool = False


_PARTICLES = {"は": "topic", "が": "subject", "を": "object", "に": "to", "へ": "to", "で": "with", "と": "and", "の": "of", "も": "also",
              "や": "and", "より": "than", "から": "from", "まで": "until"}
_SEPS = "、,。.：:;；（）()「」『』【】・"
_ROLE_PRIORITY = ("actor", "noun", "verb", "quality", "tech", "time", "modal", "other")


def _pick(alts: dict[str, str], following: str) -> tuple[str, str]:
    """Choose a reading from the particle/inflection that follows the word."""
    if "actor" in alts and following[:1] in "はが":
        return alts["actor"], "actor"
    if "noun" in alts and (following[:1] in "をはがのへにと" or following[:2] in ("など", "一覧")):
        return alts["noun"], "noun"
    if "verb" in alts and "noun" not in alts and following[:1] in "をはがの":
        return alts["verb"], "noun"       # 「検索は」: the verb's name used as a thing
    if "verb" in alts and (following[:1] in "すしでさ" or following[:2] in ("でき", "され", "した", "する") or not following
                           or following[:1] in "、,。.：:）)"):
        return alts["verb"], "verb"
    if "actor" in alts and (following[:1] in "はが" or "noun" not in alts):
        return alts["actor"], "actor"
    for r in _ROLE_PRIORITY:
        if r in alts:
            return alts[r], r
    r, v = next(iter(alts.items()))
    return v, r


def _tokenise_list(s: str) -> list[Token]:
    out: list[Token] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch.isspace() or ch in _SEPS:
            i += 1
            continue
        if ch.isascii():
            j = i
            while j < n and s[j].isascii() and not s[j].isspace() and s[j] not in ",;:()":
                j += 1
            out.append(Token(s[i:j], "ascii"))
            i = j
            continue
        m = _GLOSS_RE.match(s, i)
        if m and (len(m.group(0)) > 1 or m.group(0) not in _PARTICLES):
            word = m.group(0)
            i = m.end()
            en, role = _pick(GLOSSARY[word], s[i:i + 4])
            tok = Token(en, role, word, GLOSSARY[word])
            if role in ("verb", "quality", "noun", "other") and i < n:
                tm = _TAIL_RE.match(s, i)
                if tm and tm.group(0):
                    tail = tm.group(0)
                    tok.negated = bool(_NEG_RE.match(tail)) or tail.endswith(("ない", "ず", "なく"))
                    tok.passive = bool(_PASSIVE_RE.match(tail))
                    tok.can = "でき" in tail and not tok.negated
                    if tok.negated and role != "verb" and en:
                        tok.text = "not " + en
                    i = tm.end()
            if en:
                out.append(tok)
            continue
        if ch in _PARTICLES:
            out.append(Token(_PARTICLES[ch], "particle", ch))
            i += 1
            continue
        j = i
        while j < n and not s[j].isascii() and s[j] not in _PARTICLES and s[j] not in _SEPS and not _GLOSS_RE.match(s, j):
            j += 1
        if j == i:
            i += 1
            continue
        out.append(Token(s[i:j], "unknown", s[i:j]))
        i = j
    return out


@dataclass
class Rewrite:
    source: str
    english: str
    untranslated: list[str] = field(default_factory=list)


#: fixed phrases folded into one modal before tokenising (inflection tails would otherwise split them)
_PRE = {"してはならない": "禁止", "してはいけない": "禁止", "しては行けない": "禁止", "してはならず": "禁止",
        "しなければならない": "必須", "しなくてはならない": "必須", "しなければいけない": "必須", "する必要がある": "必須",
        "なければならない": "必須", "ねばならない": "必須", "できるようにする": "できる", "できること": "できる",
        "できるようにしたい": "できる", "できるようになる": "できる", "する事": "する", "こと。": "。"}
_PRE_RE = re.compile("|".join(map(re.escape, sorted(_PRE, key=len, reverse=True))))


def _participle(v: str) -> str:
    if v.endswith("e"):
        return v + "d"
    if v.endswith("y") and v[-2:-1] not in "aeiou":
        return v[:-1] + "ied"
    return v + "ed"


def rewrite_sentence(src: str) -> Rewrite:
    """One Japanese requirement sentence -> one English sentence in actor-verb-object order."""
    if not is_japanese(src):
        clean = unicodedata.normalize("NFKC", src).strip().rstrip("。")
        return Rewrite(src.strip(), clean + ("." if clean and not clean.endswith((".", "!", "?")) else ""), [])
    s = unicodedata.normalize("NFKC", src).strip().rstrip("。.")
    s = _PRE_RE.sub(lambda m: _PRE[m.group(0)], s)
    s = numbers(s)
    toks = _tokenise_list(s)
    unknown = [t.text for t in toks if t.role == "unknown"]
    toks = [t for t in toks if t.role != "unknown"]
    # out of scope, stated inline: 「購買は対象外」
    if any(t.text == "out of scope" for t in toks):
        words = [t.text for t in toks if t.role not in ("particle", "modal") and t.text != "out of scope"]
        return Rewrite(src.strip(), (" ".join(words).capitalize() + " (out of scope).").strip(), unknown)
    # modality: last modal wins (Japanese predicates end the sentence)
    modals = [t for t in toks if t.role == "modal"]
    modal = modals[-1].text if modals else ("can" if any(t.can for t in toks) else "")
    # actor: the first actor token followed by a topic/subject particle, else none
    actor = ""
    for k, t in enumerate(toks):
        if t.role == "actor" and k + 1 < len(toks) and toks[k + 1].role == "particle" and toks[k + 1].text in ("topic", "subject"):
            actor = t.text
            toks = toks[:k] + toks[k + 2:]
            break
    # objects: noun phrase immediately before an object particle
    objects: list[str] = []
    kept: list[Token] = []
    k = 0
    while k < len(toks):
        t = toks[k]
        if t.role == "particle" and t.text == "object" and kept and kept[-1].role in ("noun", "actor", "ascii", "quality", "other", "tech"):
            phrase = [kept.pop().text]
            while kept and kept[-1].role in ("noun", "ascii", "other", "tech") and kept[-1].text not in ("and", "or", "when", "after", "before", "within", "at most", "at least", "under"):
                phrase.insert(0, kept.pop().text)
            objects.append(" ".join(phrase))
            k += 1
            continue
        kept.append(t)
        k += 1
    verb_toks = [t for t in kept if t.role == "verb"]
    rest = [t for t in kept if t.role not in ("verb", "modal", "particle")]
    rest_words = [t.text for t in rest]
    negated = any(t.negated for t in verb_toks)
    passive = any(t.passive for t in verb_toks)
    verbs = [t.text for t in verb_toks]
    parts: list[str] = []
    if verbs:
        subj = actor or "the system"
        aux = {"can": "can", "must": "must", "should": "should", "may": "may", "must not": "must not", "always": "must always",
               "never": "must never", "optionally": "may", "later": "may later", "nice to have": "may", "": ""}.get(modal, modal)
        if not aux:
            aux = "can" if actor and actor not in ("system", "the system", "service", "job", "app", "application") else "must"
        if negated and "not" not in aux:
            aux = {"can": "must not", "must": "must not", "should": "should not"}.get(aux, aux + " not")
        obj = " and ".join(objects)
        if passive and actor:
            vs = ", ".join(_participle(v) for v in verbs[:-1]) + (" and " if len(verbs) > 1 else "") + _participle(verbs[-1])
            head = f"{subj.capitalize()} are {vs}" + (f" {obj}" if obj else "")
        else:
            vs = ", ".join(verbs[:-1]) + (" and " if len(verbs) > 1 else "") + verbs[-1]
            head = f"{subj.capitalize()} {aux} {vs}" + (f" {obj}" if obj else "")
        parts.append(head)
        if rest_words:
            parts.append(" ".join(rest_words))
    else:
        words = ([actor] if actor else []) + rest_words + ([" and ".join(objects)] if objects else [])
        if modal in ("must", "should", "must not", "always", "never"):
            words.append({"always": "must always", "never": "must never"}.get(modal, modal))
        parts.append(" ".join(w for w in words if w))
    en = re.sub(r"\s+", " ", " ".join(parts)).strip()
    en = en[:1].upper() + en[1:] if en else en
    if en and not en.endswith("."):
        en += "."
    return Rewrite(src.strip(), en, unknown)


# ---------------------------------------------------------------------------
# Document rewriting
# ---------------------------------------------------------------------------

_BULLET = re.compile(r"^\s*(?:[-*・●○■□▪◦•]|\d+[.)．]|[①-⑳])\s*")
_HEADING = re.compile(r"^\s*(#{1,6})\s*(.+?)\s*$")


@dataclass
class Normalised:
    text: str
    rewrites: list[Rewrite]
    untranslated: list[str]
    title: str
    #: English requirement unit (as the engine will see it) -> the Japanese line it came from
    sources: dict[str, str] = field(default_factory=dict)

    def to_markdown(self) -> str:
        s = ["## Input normalisation (Japanese → canonical English)\n",
             "The engine reads English. Each Japanese sentence was rewritten with a glossary and a particle-driven reorder; "
             "check the right-hand column — it is what was designed, not the left.\n",
             "| source | rewritten as |", "|---|---|"]
        s += [f"| {r.source.replace('|', '¦')} | {r.english.replace('|', '¦')} |" for r in self.rewrites]
        if self.untranslated:
            s.append("\nWords the glossary does not know (dropped from the English; add them to the text in English or extend the glossary): "
                     + ", ".join(f"「{w}」" for w in sorted(set(self.untranslated))))
        return "\n".join(s) + "\n"


def _section(title: str) -> str | None:
    t = unicodedata.normalize("NFKC", title)
    for keys, en in SECTION_MAP:
        if any(k in t for k in keys):
            return en
    return None


def _split_sentences(s: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=。)\s*", s) if p.strip()]


def normalise(text: str) -> Normalised:
    """Whole document: headings mapped to the engine's sections, bullets rewritten one by one, prose sentence by sentence."""
    out: list[str] = []
    rewrites: list[Rewrite] = []
    unknown: list[str] = []
    sources: dict[str, str] = {}
    title = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            out.append("")
            continue
        if not is_japanese(line):
            out.append(line)
            continue
        hm = _HEADING.match(line)
        if hm:
            hashes, t = hm.groups()
            if len(hashes) == 1 and not title:
                title = t
                words = [tok.text for tok in _tokenise_list(unicodedata.normalize("NFKC", t)) if tok.role not in ("particle", "unknown", "modal")]
                out.append("# " + (" ".join(words).title() if words else "System"))
                continue
            sec = _section(t)
            out.append(f"{hashes} " + (sec or rewrite_sentence(t).english.rstrip(".")))
            continue
        bm = _BULLET.match(line)
        body = _BULLET.sub("", line).strip() if bm else line.strip()
        sec = _section(body) if not bm and len(body) <= 12 and not body.endswith("。") else None
        if sec:
            out.append("## " + sec)
            continue
        ens = []
        for sent in _split_sentences(body):
            rw = rewrite_sentence(sent)
            rewrites.append(rw)
            unknown += rw.untranslated
            if rw.english:
                ens.append(rw.english)
        en = " ".join(ens)
        if en:
            sources[en] = body
            for e in ens:
                sources.setdefault(e.strip(), body)
        out.append(("- " + en) if bm else en)
    return Normalised("\n".join(out).strip() + "\n", rewrites, unknown, title, sources)
