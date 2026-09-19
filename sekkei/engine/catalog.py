"""The knowledge base: capability patterns, quality tactics, technology rules, layouts.

Everything an architect "just knows" is written down here as data. A pattern is
recognised by signals in the text and brings archetypes (component templates), entity
templates, flow templates, decision points and risks. Archetypes are keyed globally so
patterns that share one (e.g. ``store``) merge into a single component.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class OpT:
    """Operation template."""
    name: str
    inputs: list[tuple[str, str]] = field(default_factory=list)
    output: str = ""
    errors: list[str] = field(default_factory=list)
    pre: str = ""
    post: str = ""
    description: str = ""


@dataclass
class Archetype:
    key: str
    name: str
    responsibility: str
    kind: str = "module"            # module | service | job | datastore | external | cli | ui
    layer: int = 1                  # 0 storage/external, 1 core, 2 integration/jobs, 3 surface
    needs: list[str] = field(default_factory=list)      # archetype keys this one calls
    ops: list[OpT] = field(default_factory=list)
    iface_kind: str = "module"      # kind of the interface it provides
    entities: list[str] = field(default_factory=list)   # entity template keys it owns


@dataclass
class EntityT:
    key: str
    name: str
    fields: list[tuple[str, str, str]]  # name, type, constraints
    description: str = ""


@dataclass
class FlowT:
    key: str
    name: str
    trigger: str
    steps: list[tuple[str, str, str]]   # from archetype, to archetype, description


@dataclass
class Option:
    name: str
    pros: list[str]
    cons: list[str]
    fit: dict[str, int]                 # quality -> 0..3
    needs: list[str] = field(default_factory=list)      # constraint tokens required (any of)
    excludes: list[str] = field(default_factory=list)   # constraint tokens that rule it out
    bonus_when: list[str] = field(default_factory=list) # constraint tokens that make this the stated choice (+1.0)
    max_rate: float = 0.0                                # items/s above which the option is penalised (0 = no ceiling)


@dataclass
class DecisionPoint:
    key: str
    title: str
    context: str
    options: list[Option]
    affects: list[str]                  # archetype keys
    trigger: list[str] = field(default_factory=list)   # pattern ids or quality names that activate it


@dataclass
class RiskT:
    key: str
    description: str
    likelihood: str
    impact: str
    mitigation: str
    affects: list[str]


@dataclass
class Pattern:
    id: str
    name: str
    signals: list[tuple[str, int]]      # (regex, weight); active when total weight >= 2
    archetypes: list[str]
    entities: list[str] = field(default_factory=list)
    flows: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class Tactic:
    quality: str
    signals: list[tuple[str, int]]
    archetypes: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    acceptance: str = ""                # acceptance template for metric checks
    convention: str = ""


@dataclass
class Layout:
    language: str
    module: str          # format with {key}
    test: str
    test_command: str    # format with {test}
    lint_command: str
    rules: list[str]
    test_all: str = ""   # run the whole suite


QUALITIES = ("durability", "consistency", "performance", "isolation", "availability", "security",
             "operability", "scalability", "simplicity", "cost", "compliance", "usability")

# ---------------------------------------------------------------------------
# Archetypes
# ---------------------------------------------------------------------------

ARCHETYPES: dict[str, Archetype] = {a.key: a for a in [
    Archetype("store", "Store", "Owns persistence of the domain entities: durable writes, reads, listing, and the schema/migrations.",
              kind="datastore", layer=0, iface_kind="class", ops=[
                  OpT("save", [("entity", "Entity"), ("record", "dict")], "id", ["ConflictError on duplicate key"], post="record is durable before return"),
                  OpT("get", [("entity", "Entity"), ("id", "str")], "record | None"),
                  OpT("list", [("entity", "Entity"), ("filter", "dict"), ("page", "Page")], "list[record], next page token"),
                  OpT("delete", [("entity", "Entity"), ("id", "str")], "bool"),
              ]),
    Archetype("core", "Domain core", "Business rules and validation for the domain entities; the only module that changes state through the store.",
              layer=1, needs=["store"], iface_kind="module"),
    Archetype("surface_api", "Public HTTP API", "Translates HTTP requests into core calls: routing, request validation, error mapping, JSON.",
              kind="service", layer=3, needs=["core"], iface_kind="http"),
    Archetype("admin_api", "Admin HTTP API", "Management surface for operators/customers: resource lifecycle and configuration; authenticated.",
              kind="service", layer=3, needs=["core", "auth"], iface_kind="http"),
    Archetype("ingest_api", "Ingest API", "Accepts events/records from producers, validates them, persists them, and enqueues work; acknowledges only after persistence.",
              kind="service", layer=3, needs=["core", "queue"], iface_kind="http", ops=[
                  OpT("POST /events", [("type", "str"), ("payload", "json"), ("idempotency_key", "str")], "202 {event_id}",
                      ["400 invalid payload", "409 duplicate idempotency key"], post="event persisted and enqueued before 202"),
              ]),
    Archetype("queue", "Work queue", "Durable, ordered hand-off of work items between the ingest path and the workers, with visibility timeout and dead-letter.",
              kind="datastore", layer=0, iface_kind="class", ops=[
                  OpT("enqueue", [("item", "WorkItem"), ("not_before", "datetime | None")], "None", post="item is durable before return"),
                  OpT("lease", [("partition", "str"), ("limit", "int"), ("visibility", "timedelta")], "list[WorkItem]", pre="items whose not_before has passed"),
                  OpT("ack", [("item_id", "str")], "None"),
                  OpT("nack", [("item_id", "str"), ("retry_at", "datetime | None")], "None", description="re-queue with a delay, or dead-letter when retries are exhausted"),
                  OpT("depth", [("partition", "str | None")], "int"),
              ]),
    Archetype("worker", "Worker", "Leases work items, performs the outbound action, records the outcome, and decides retry vs. final failure.",
              kind="job", layer=2, needs=["queue", "core", "scheduler"], iface_kind="module", ops=[
                  OpT("run_once", [("partition", "str")], "int processed", description="one lease/process/ack cycle; the loop and concurrency live in the process entry point"),
                  OpT("process", [("item", "WorkItem")], "Outcome", ["DeliveryError"], post="outcome recorded through core before ack"),
              ]),
    Archetype("scheduler", "Scheduler", "Computes when deferred work runs next (backoff schedules, periodic jobs) and promotes due work.",
              kind="job", layer=2, needs=[], iface_kind="module", ops=[
                  OpT("next_attempt", [("attempt", "int"), ("retry_after", "timedelta | None")], "datetime | None",
                      description="None when attempts are exhausted"),
                  OpT("promote_due", [("now", "datetime")], "int moved"),
              ]),
    Archetype("dispatcher", "Outbound HTTP client", "Performs the outbound HTTP call with timeouts, size limits, redirect and private-address protection, and returns a classified outcome.",
              layer=1, iface_kind="module", ops=[
                  OpT("post", [("url", "str"), ("body", "bytes"), ("headers", "dict"), ("timeout", "float")], "Outcome(status, latency, retry_after)",
                      ["TimeoutError", "ConnectionError", "BlockedAddressError"], pre="url resolves to a public address"),
              ]),
    Archetype("signer", "Signer", "Produces and verifies HMAC signatures over request bodies with the current and previous secrets.",
              layer=1, needs=["secrets"], iface_kind="module", ops=[
                  OpT("sign", [("body", "bytes"), ("timestamp", "int"), ("secret", "bytes")], "signature hex", post="HMAC-SHA256(timestamp + '.' + body)"),
                  OpT("headers", [("body", "bytes"), ("secrets", "list[bytes]")], "dict of signature headers", description="one header per valid secret during a rotation window"),
              ]),
    Archetype("secrets", "Secret store", "Holds per-endpoint signing secrets and their rotation history; encrypts at rest.",
              kind="datastore", layer=0, iface_kind="class", ops=[
                  OpT("current", [("endpoint_id", "str")], "list[Secret] valid now"),
                  OpT("rotate", [("endpoint_id", "str"), ("grace", "timedelta")], "Secret new", post="old secret stays valid until now + grace"),
              ]),
    Archetype("policy", "Health policy", "Evaluates per-target failure history against the disable policy and applies the consequence.",
              kind="job", layer=2, needs=["core", "notifier"], iface_kind="module", ops=[
                  OpT("evaluate", [("now", "datetime")], "list[action taken]", description="disables targets failing continuously beyond the window and notifies"),
              ]),
    Archetype("notifier", "Notifier", "Sends operator/customer notifications through the configured channel with templating and rate limiting.",
              layer=1, needs=["email"], iface_kind="module", ops=[
                  OpT("notify", [("recipient", "str"), ("template", "str"), ("context", "dict")], "message id", ["NotifyError"]),
              ]),
    Archetype("chat", "Chat provider", "External chat service (Slack/Teams) reached through a webhook or bot token.", kind="external", layer=0, iface_kind="http", ops=[
        OpT("post", [("channel", "str"), ("text", "str"), ("blocks", "json | None")], "message ts", ["429 rate limited"]),
    ]),
    Archetype("email", "Email provider", "External email delivery service.", kind="external", layer=0, iface_kind="http", ops=[
        OpT("send", [("to", "str"), ("subject", "str"), ("body", "str")], "provider message id"),
    ]),
    Archetype("external_service", "External HTTP service", "A service outside this design that we call over HTTP (an existing internal service or a third-party API).", kind="external", layer=0, iface_kind="http", ops=[
        OpT("call", [("method", "str"), ("path", "str"), ("body", "json | None")], "response", ["4xx", "5xx", "timeout"]),
    ]),
    Archetype("endpoint", "Customer endpoint", "The customer's HTTPS receiver; outside our control.", kind="external", layer=0, iface_kind="http", ops=[
        OpT("POST <url>", [("body", "json"), ("signature headers", "str")], "2xx on acceptance", ["4xx final", "5xx retry", "429 with Retry-After"]),
    ]),
    Archetype("observability", "Observability", "Metrics registry and exposition, structured logging, health/readiness endpoints.",
              layer=1, iface_kind="module", ops=[
                  OpT("counter", [("name", "str"), ("labels", "dict")], "Counter"),
                  OpT("histogram", [("name", "str"), ("labels", "dict")], "Histogram"),
                  OpT("gauge", [("name", "str"), ("labels", "dict")], "Gauge"),
                  OpT("GET /metrics", [], "Prometheus text exposition"),
                  OpT("GET /healthz", [], "200 when dependencies reachable"),
                  OpT("log", [("event", "str"), ("fields", "dict")], "None", description="one JSON line per event"),
              ]),
    Archetype("auth", "Authentication", "Authenticates callers and resolves them to a principal and scope; enforces authorization for management operations.",
              layer=1, needs=["store"], iface_kind="module", ops=[
                  OpT("authenticate", [("credentials", "str")], "Principal", ["AuthError"]),
                  OpT("authorize", [("principal", "Principal"), ("action", "str"), ("resource", "str")], "None", ["Forbidden"]),
              ]),
    Archetype("ratelimit", "Rate limiter", "Per-principal or per-key request budgets with a sliding window.",
              layer=1, iface_kind="module", ops=[OpT("check", [("key", "str"), ("cost", "int")], "Decision(allowed, retry_after)")]),
    Archetype("cache", "Cache", "Read-through cache with TTL and explicit invalidation.",
              layer=1, iface_kind="module", ops=[OpT("get_or_load", [("key", "str"), ("loader", "callable"), ("ttl", "int")], "value"),
                                                 OpT("invalidate", [("key", "str")], "None")]),
    Archetype("search", "Search index", "Full-text and filtered queries over the indexed entities.",
              layer=1, needs=["store"], iface_kind="module", ops=[OpT("index", [("entity", "Entity"), ("record", "dict")], "None"),
                                                                  OpT("query", [("text", "str"), ("filters", "dict"), ("page", "Page")], "hits")]),
    Archetype("files", "File storage", "Stores and serves uploaded files/blobs with content-type and size limits.",
              kind="datastore", layer=0, iface_kind="class", ops=[OpT("put", [("key", "str"), ("data", "bytes"), ("content_type", "str")], "FileRef"),
                                                                  OpT("get", [("key", "str")], "bytes | None")]),
    Archetype("loader", "Load job", "One idempotent load per source and day: read the delivered files, normalise to the common schema, deduplicate, write the day's partition (replace, never append) and record freshness.",
              kind="job", layer=2, needs=["files", "warehouse", "scheduler", "notifier"], iface_kind="module", ops=[
                  OpT("load", [("source", "str"), ("day", "date")], "LoadResult(rows, rejected, duration)", ["SourceLateError", "SchemaError"], pre="all files for (source, day) are present", post="the (source, day) partition equals the delivered files exactly; a re-run replaces it"),
                  OpT("freshness", [("source", "str")], "last loaded day and time"),
              ]),
    Archetype("warehouse", "Analytics warehouse", "The external analytics database (Snowflake/BigQuery/Redshift) the loads write to and analysts query; outside this design.", kind="external", layer=0, iface_kind="http", ops=[
        OpT("write_partition", [("table", "str"), ("day", "date"), ("rows", "iter")], "rows written"),
        OpT("query", [("sql", "str")], "rows"),
    ]),
    Archetype("batch", "Batch job", "Scheduled processing over stored records: extract, transform, aggregate, write results.",
              kind="job", layer=2, needs=["store", "scheduler"], iface_kind="module", ops=[OpT("run", [("window", "DateRange")], "JobReport", ["JobError"])]),
    Archetype("ui", "Local user interface", "Screen/panel that shows state and takes the user's inputs; talks only to the core.",
              kind="ui", layer=3, needs=["core"], iface_kind="module", ops=[
                  OpT("show", [("view", "str"), ("state", "dict")], "None"),
                  OpT("on_input", [("event", "InputEvent")], "None", description="forwards the user's action to the core"),
              ]),
    Archetype("mqtt_consumer", "MQTT consumer", "Subscribes to the broker's topics, validates and de-duplicates messages, persists them and acknowledges only after persistence.",
              kind="job", layer=3, needs=["core", "queue", "mqtt_broker"], iface_kind="event", ops=[
                  OpT("on_message", [("topic", "str"), ("payload", "bytes"), ("message_id", "str")], "None", ["ValidationError -> dead-letter topic"],
                      post="reading persisted (idempotent on message_id) before the broker ack"),
              ]),
    Archetype("mqtt_broker", "MQTT broker", "Existing broker operated elsewhere; delivers device messages at least once.", kind="external", layer=0, iface_kind="event", ops=[
        OpT("subscribe", [("topic", "str"), ("qos", "int")], "message stream"),
    ]),
    Archetype("sftp_target", "SFTP server", "External file drop for exports.", kind="external", layer=0, iface_kind="file", ops=[
        OpT("put", [("path", "str"), ("data", "bytes")], "None", ["transfer error -> retry next run"]),
    ]),
    Archetype("sms", "SMS provider", "External SMS gateway.", kind="external", layer=0, iface_kind="http", ops=[
        OpT("send", [("to", "str"), ("text", "str")], "provider message id"),
    ]),
    Archetype("geo", "Geospatial index", "Keeps current positions and answers nearest-neighbour queries within a radius.",
              layer=1, needs=["store"], iface_kind="module", ops=[
                  OpT("update_position", [("subject_id", "str"), ("lat", "float"), ("lon", "float"), ("at", "datetime")], "None"),
                  OpT("nearest", [("lat", "float"), ("lon", "float"), ("radius_m", "int"), ("limit", "int"), ("filter", "dict")], "list[(subject_id, distance_m)]"),
              ]),
    Archetype("cli", "Command line", "Parses arguments, calls the core, prints results, sets the exit code.",
              kind="cli", layer=3, needs=["core"], iface_kind="cli"),
    Archetype("config", "Configuration", "Loads and validates settings from environment/files; single typed object.",
              layer=0, iface_kind="module", ops=[OpT("load", [("env", "dict")], "Settings", ["ConfigError listing every invalid key"])]),
    Archetype("push", "Push gateway", "Long-lived connections (WebSocket/SSE) that fan out events to connected clients.",
              kind="service", layer=3, needs=["core"], iface_kind="http", ops=[OpT("subscribe", [("topic", "str")], "stream of events")]),
    Archetype("payments", "Payments", "Creates charges/invoices through the payment provider and reconciles their webhooks.",
              layer=1, needs=["psp", "store"], iface_kind="module", ops=[OpT("charge", [("customer", "str"), ("amount", "Money"), ("idempotency_key", "str")], "Charge", ["PaymentDeclined"])]),
    Archetype("psp", "Payment provider", "External payment service provider.", kind="external", layer=0, iface_kind="http", ops=[OpT("POST /charges", [], "charge")]),
    Archetype("model", "Model server", "Loads the model, serves predictions with batching and timeouts, versions the model.",
              kind="service", layer=1, iface_kind="module", ops=[OpT("predict", [("inputs", "list"), ("model_version", "str")], "predictions", ["ModelError"])]),
    Archetype("audit", "Audit log", "Append-only record of who did what to which resource, queryable by resource and actor.",
              kind="datastore", layer=0, iface_kind="class", ops=[OpT("append", [("actor", "str"), ("action", "str"), ("resource", "str"), ("details", "dict")], "None"),
                                                                  OpT("query", [("resource", "str | None"), ("actor", "str | None"), ("page", "Page")], "entries")]),
    Archetype("exporter", "Import/export", "Streams records to and from CSV/JSON with validation and partial-failure reporting.",
              layer=1, needs=["core"], iface_kind="module", ops=[OpT("export", [("entity", "Entity"), ("filter", "dict"), ("format", "csv|json")], "byte stream"),
                                                                 OpT("import_", [("entity", "Entity"), ("stream", "bytes"), ("format", "csv|json")], "ImportReport with per-row errors")]),
    Archetype("bus", "Event bus", "Publishes domain events to subscribers inside the system.",
              layer=1, iface_kind="event", ops=[OpT("publish", [("event", "Event")], "None"), OpT("subscribe", [("type", "str"), ("handler", "callable")], "None")]),

    Archetype("verifier", "Identity and credit checks", "Calls the external identity/credit providers with timeouts and retries, normalises their answers, records each check with its raw response and time.",
              layer=1, needs=["kyc_provider", "store"], iface_kind="module", ops=[
                  OpT("verify_identity", [("applicant_id", "str"), ("documents", "list[File]")], "IdentityCheck", ["ProviderUnavailableError", "IdentityMismatchError"],
                      post="check persisted with the provider's reference before return"),
                  OpT("credit_report", [("applicant_id", "str")], "CreditReport", ["ProviderUnavailableError"], description="cached for the application's lifetime"),
              ]),
    Archetype("kyc_provider", "Identity / credit provider", "External KYC and credit bureau services; rate limited, billed per call.", kind="external", layer=0, iface_kind="http", ops=[
        OpT("POST /verify", [("document", "bytes"), ("person", "dict")], "match | no match | review"), OpT("GET /report", [("person", "dict")], "credit report")]),
    Archetype("cdn", "CDN", "Edge cache in front of the object store; serves media by signed, expiring URLs.", kind="external", layer=0, iface_kind="http", ops=[
        OpT("GET <signed url>", [], "bytes with range support")]),
    Archetype("tenancy", "Tenant context", "Resolves the tenant of every request from the principal and scopes every store access to it; the only place tenant ids are compared.",
              layer=1, needs=["auth", "store"], iface_kind="module", ops=[
                  OpT("resolve", [("principal", "Principal")], "Tenant", ["UnknownTenantError"], post="tenant is the principal's tenant; never a request parameter"),
                  OpT("scope", [("tenant", "Tenant"), ("query", "Query")], "Query", description="adds the tenant predicate to every store query"),
              ], entities=["tenant"]),
    Archetype("workflow", "Workflow engine", "Runs the approval/state machine: allowed transitions, who may perform them, timeouts and escalation; every transition is recorded.",
              layer=1, needs=["store", "notifier"], iface_kind="module", ops=[
                  OpT("submit", [("item_id", "str"), ("actor", "Principal")], "WorkflowInstance", ["InvalidTransitionError"], post="state = submitted; approvers notified"),
                  OpT("transition", [("instance_id", "str"), ("action", "str"), ("actor", "Principal"), ("comment", "str")], "WorkflowInstance",
                      ["InvalidTransitionError", "NotPermittedError"], pre="action is allowed from the current state for this actor's role", post="transition appended to history before return"),
                  OpT("escalate_due", [("now", "datetime")], "int escalated", description="instances past their step deadline go to the next approver"),
              ], entities=["workflow_instance"]),
    Archetype("reporting", "Reporting", "Builds read models and aggregates (daily/weekly figures, KPIs) on a schedule or on demand; serves them to dashboards and exports.",
              kind="job", layer=2, needs=["store"], iface_kind="module", ops=[
                  OpT("build", [("report", "str"), ("window", "TimeWindow")], "ReportRun", post="aggregates written atomically; the previous version stays readable until then"),
                  OpT("read", [("report", "str"), ("filter", "dict")], "rows", description="serves the last completed run"),
              ], entities=["report_run"]),
    Archetype("backup", "Backup and restore", "Takes and verifies backups on a schedule, keeps them for the retention period, and performs restores to a point in time.",
              kind="job", layer=2, needs=["store"], iface_kind="module", ops=[
                  OpT("snapshot", [("now", "datetime")], "BackupRun", post="backup verified by a test restore or checksum before it counts"),
                  OpT("restore", [("point", "datetime"), ("target", "str")], "RestoreRun", ["BackupMissingError"], pre="a verified backup at or before point exists"),
              ], entities=["backup_run"]),
    Archetype("flags", "Feature flags", "Evaluates feature flags per principal/tenant with gradual rollout percentages; flags are data, not deploys.",
              layer=1, needs=["config"], iface_kind="module", ops=[
                  OpT("enabled", [("flag", "str"), ("subject", "Principal | Tenant")], "bool", description="stable per subject for a given percentage"),
              ], entities=["flag"]),
    Archetype("i18n", "Localisation", "Resolves locale, timezone and currency per request; formats messages, dates and amounts from message catalogues.",
              layer=1, iface_kind="module", ops=[
                  OpT("t", [("key", "str"), ("locale", "str"), ("args", "dict")], "str", description="falls back to the default locale; missing keys are logged, never blank"),
                  OpT("format", [("value", "datetime | Money"), ("locale", "str"), ("tz", "str")], "str"),
              ]),
    Archetype("legacy_adapter", "Legacy system adapter", "Anti-corruption layer in front of the existing system: translates its records and calls into our model, isolates its quirks and outages.",
              layer=2, needs=["legacy_system", "core"], iface_kind="module", ops=[
                  OpT("pull", [("since", "datetime")], "list[record]", ["LegacyUnavailableError"], description="incremental read; idempotent on re-run"),
                  OpT("push", [("record", "record")], "legacy id", ["LegacyRejectedError"], post="mapping stored so the record is not pushed twice"),
              ]),
    Archetype("legacy_system", "Existing system", "The system of record that already exists (ERP/CRM/database); outside our control.", kind="external", layer=0, iface_kind="http", ops=[
        OpT("read/write", [], "records", ["unavailable"]),
    ]),
    Archetype("sync", "Offline sync", "Reconciles changes made offline on devices with the server: change log, conflict rules, and resumable upload/download.",
              kind="service", layer=2, needs=["core", "store"], iface_kind="http", ops=[
                  OpT("POST /sync/push", [("device_id", "str"), ("changes", "list[Change]"), ("cursor", "str")], "list[Conflict], cursor",
                      ["409 conflict"], post="accepted changes are durable before the response"),
                  OpT("GET /sync/pull", [("device_id", "str"), ("cursor", "str")], "list[Change], cursor", description="changes since cursor, in order"),
              ]),
    Archetype("mobile", "Mobile app", "The client on the user's phone; keeps a local store for offline use and talks only to the API.",
              kind="ui", layer=3, needs=["surface_api"], iface_kind="module"),
    Archetype("messaging", "Messaging", "Conversations and messages between users: delivery, read state, unread counts, and fan-out to connected clients.",
              layer=1, needs=["store", "push"], iface_kind="module", ops=[
                  OpT("send", [("conversation_id", "str"), ("sender", "Principal"), ("body", "str")], "Message", ["NotAMemberError"], post="message durable before fan-out"),
                  OpT("mark_read", [("conversation_id", "str"), ("reader", "Principal"), ("up_to", "str")], "None"),
              ], entities=["message"]),
    Archetype("data_protection", "Data protection", "Retention schedules, deletion and export requests for a person's data, consent records; runs the deletions and proves them.",
              kind="job", layer=2, needs=["store", "audit"], iface_kind="module", ops=[
                  OpT("request_deletion", [("subject_id", "str"), ("requested_by", "Principal")], "DeletionRequest", post="request recorded with a deadline"),
                  OpT("run_due", [("now", "datetime")], "int completed", description="deletes or anonymises across every store; audit entry per subject"),
                  OpT("export", [("subject_id", "str")], "archive", description="everything held about the subject, machine readable"),
              ], entities=["deletion_request"]),
]}

# ---------------------------------------------------------------------------
# Entities and flows
# ---------------------------------------------------------------------------

ENTITIES: dict[str, EntityT] = {e.key: e for e in [
    EntityT("event", "Event", [("id", "uuid", "primary key"), ("type", "str", "indexed"), ("payload", "json", ""),
                               ("created_at", "timestamp", ""), ("idempotency_key", "str", "unique per producer")]),
    EntityT("work_item", "WorkItem", [("id", "uuid", "primary key"), ("partition", "str", "indexed; the isolation key"),
                                      ("payload_ref", "uuid", "references the event"), ("attempt", "int", ">= 0"),
                                      ("not_before", "timestamp", "indexed"), ("leased_until", "timestamp | null", "")]),
    EntityT("attempt", "DeliveryAttempt", [("id", "uuid", "primary key"), ("work_item_id", "uuid", "indexed"),
                                           ("attempt", "int", ""), ("status", "enum(success, retry, failed)", ""),
                                           ("response_code", "int | null", ""), ("started_at", "timestamp", ""),
                                           ("finished_at", "timestamp", ""), ("error", "str | null", "")]),
    EntityT("target", "Endpoint", [("id", "uuid", "primary key"), ("owner_id", "uuid", "indexed"), ("url", "https url", "validated; no private addresses"),
                                   ("event_types", "list[str]", ""), ("enabled", "bool", ""), ("disabled_reason", "str | null", ""),
                                   ("failing_since", "timestamp | null", "")]),
    EntityT("secret", "Secret", [("id", "uuid", "primary key"), ("endpoint_id", "uuid", "indexed"), ("value", "bytes", "encrypted at rest"),
                                 ("created_at", "timestamp", ""), ("valid_until", "timestamp | null", "set on rotation")]),
    EntityT("principal", "Principal", [("id", "uuid", "primary key"), ("kind", "enum(customer, operator, service)", ""), ("scopes", "list[str]", "")]),
    EntityT("record", "Record", [("id", "uuid", "primary key"), ("created_at", "timestamp", ""), ("updated_at", "timestamp", "")],
            "Generic domain record; refine per entity found in the requirements."),
    EntityT("file", "File", [("key", "str", "primary key"), ("content_type", "str", ""), ("size", "int", "<= configured limit"), ("owner_id", "uuid", "")]),
    EntityT("audit_entry", "AuditEntry", [("id", "uuid", "primary key"), ("actor", "str", ""), ("action", "str", ""), ("resource", "str", "indexed"), ("at", "timestamp", "")]),
    EntityT("job_run", "JobRun", [("id", "uuid", "primary key"), ("job", "str", ""), ("window_start", "timestamp", ""), ("window_end", "timestamp", ""), ("status", "enum", ""), ("report", "json", "")]),
    EntityT("tenant", "Tenant", [("id", "uuid", "primary key"), ("name", "str", ""), ("plan", "str", ""), ("status", "enum(active, suspended)", "")],
            "The isolation unit; every domain row carries tenant_id."),
    EntityT("workflow_instance", "WorkflowInstance", [("id", "uuid", "primary key"), ("item_id", "uuid", "indexed"), ("state", "str", "from the state machine"),
                                                        ("step_deadline", "timestamp", ""), ("history", "list[Transition]", "append-only")]),
    EntityT("report_run", "ReportRun", [("id", "uuid", "primary key"), ("report", "str", "indexed"), ("window_start", "timestamp", ""), ("window_end", "timestamp", ""),
                                        ("completed_at", "timestamp", ""), ("rows", "int", "")]),
    EntityT("backup_run", "BackupRun", [("id", "uuid", "primary key"), ("taken_at", "timestamp", ""), ("location", "str", ""), ("verified", "bool", "test restore or checksum"),
                                        ("expires_at", "timestamp", "retention")]),
    EntityT("flag", "FeatureFlag", [("key", "str", "primary key"), ("percentage", "int", "0..100"), ("allow", "list[str]", "subjects always on"), ("updated_at", "timestamp", "")]),
    EntityT("message", "Message", [("id", "uuid", "primary key"), ("conversation_id", "uuid", "indexed"), ("sender_id", "uuid", ""), ("body", "str", "size limited"),
                                   ("sent_at", "timestamp", ""), ("read_by", "list[uuid]", "")]),
    EntityT("deletion_request", "DeletionRequest", [("id", "uuid", "primary key"), ("subject_id", "uuid", "indexed"), ("requested_at", "timestamp", ""),
                                                    ("deadline", "timestamp", "statutory window"), ("completed_at", "timestamp", ""), ("proof", "json", "what was deleted where")]),
]}

FLOWS: dict[str, FlowT] = {f.key: f for f in [
    FlowT("ingest", "Publish an event", "producer calls the ingest API", [
        ("ingest_api", "core", "validate the event against known types"),
        ("core", "store", "persist the event"),
        ("ingest_api", "queue", "enqueue one work item per matching target; ack only after both are durable"),
    ]),
    FlowT("deliver", "Deliver a work item", "worker leases due items", [
        ("worker", "queue", "lease items of one partition"),
        ("worker", "core", "load target, secrets and payload"),
        ("worker", "queue", "ack on success, nack with retry_at on retryable failure, dead-letter when exhausted"),
    ]),
    FlowT("retry", "Retry after failure", "scheduler tick", [
        ("scheduler", "queue", "promote items whose not_before has passed"),
    ]),
    FlowT("manage", "Manage a resource", "authenticated management request", [
        ("admin_api", "auth", "authenticate and authorize"),
        ("admin_api", "core", "apply the change"),
        ("core", "store", "persist"),
    ]),
    FlowT("disable", "Disable a continuously failing target", "policy tick", [
        ("policy", "core", "read failure history and disable the target"),
        ("policy", "notifier", "notify the owner"),
    ]),
    FlowT("request", "Serve a request", "client calls the API", [
        ("surface_api", "core", "validate and apply"),
        ("core", "store", "read/write"),
    ]),
    FlowT("cli_run", "Run a command", "user runs the command line", [
        ("cli", "core", "parse arguments and call the operation"),
        ("core", "store", "read/write"),
    ]),
    FlowT("batch_run", "Run the batch job", "schedule fires", [
        ("batch", "store", "read the window of records"),
        ("batch", "store", "write results and the job report"),
    ]),
    FlowT("verify_identity", "Verify an applicant", "an application is submitted", [
        ("surface_api", "core", "application submitted"), ("core", "verifier", "verify_identity + credit_report"),
        ("verifier", "kyc_provider", "provider calls with timeout"), ("verifier", "store", "checks recorded with raw responses"),
        ("core", "store", "application state updated")]),
    FlowT("approve", "Approve an item", "an actor submits an item for approval", [
        ("surface_api", "workflow", "submit(item)"), ("workflow", "store", "instance saved, state = submitted"),
        ("workflow", "notifier", "approvers notified"), ("surface_api", "workflow", "transition(approve | reject) by an approver"),
        ("workflow", "store", "history appended, state updated"), ("workflow", "notifier", "requester notified of the outcome")]),
    FlowT("tenant_request", "Serve a tenant-scoped request", "authenticated request arrives", [
        ("surface_api", "auth", "principal resolved"), ("surface_api", "tenancy", "tenant resolved from the principal"),
        ("surface_api", "core", "operation with the tenant"), ("core", "store", "query scoped by tenant_id")]),
    FlowT("backup_restore", "Back up and restore", "schedule fires / operator requests a restore", [
        ("backup", "store", "snapshot taken; verified by a test restore or checksum; run marked verified"),
        ("backup", "store", "restore to the requested point (operator-triggered)")]),
    FlowT("sync_round", "Sync a device", "device comes online", [
        ("mobile", "sync", "POST /sync/push (local changes since cursor)"), ("sync", "core", "apply changes; detect conflicts"),
        ("sync", "mobile", "conflicts and new cursor"), ("mobile", "sync", "GET /sync/pull"), ("sync", "mobile", "server changes since cursor")]),
    FlowT("legacy_sync", "Exchange records with the existing system", "schedule fires", [
        ("legacy_adapter", "legacy_system", "pull(since)"), ("legacy_adapter", "core", "translated records applied"),
        ("legacy_adapter", "core", "records changed since the last run are read"), ("legacy_adapter", "legacy_system", "push; mapping stored")]),
]}

# ---------------------------------------------------------------------------
# Decision points (trade-offs scored against the active qualities)
# ---------------------------------------------------------------------------

DECISIONS: dict[str, DecisionPoint] = {d.key: d for d in [
    DecisionPoint("queue_tech", "Work queue technology",
                  "Work items must survive a crash and be leased by several workers.",
                  [Option("PostgreSQL table with SELECT ... FOR UPDATE SKIP LOCKED",
                          ["transactional with the domain data (persist + enqueue atomically)", "no new infrastructure", "easy to inspect"],
                          ["throughput bounded by the database (fine to ~10k items/s)", "needs a vacuum-friendly schema"],
                          {"durability": 3, "simplicity": 3, "performance": 2, "isolation": 2, "scalability": 2, "cost": 3, "operability": 3}, bonus_when=["postgres"], excludes=["no_database", "cli_tool"], max_rate=10000),
                   Option("Redis Streams with consumer groups",
                          ["high throughput", "built-in consumer groups and pending lists"],
                          ["durability depends on AOF/fsync configuration", "separate from the transactional store: needs an outbox"],
                          {"durability": 1, "simplicity": 2, "performance": 3, "isolation": 2, "scalability": 3, "cost": 2, "operability": 2}, needs=["redis"]),
                   Option("Managed broker (SQS/RabbitMQ/Kafka)",
                          ["scales independently", "delayed delivery built in (SQS)"],
                          ["new infrastructure and cost", "at-least-once semantics still need an outbox"],
                          {"durability": 3, "simplicity": 1, "performance": 3, "isolation": 2, "scalability": 3, "cost": 1, "operability": 2}, needs=["broker"], bonus_when=["broker"]),
                   Option("In-memory queue",
                          ["simplest possible"], ["work is lost on crash", "single process only"],
                          {"durability": 0, "simplicity": 3, "performance": 3, "isolation": 1, "scalability": 0, "cost": 3, "operability": 2}, max_rate=1000,
                          excludes=["durable_required", "containers", "multi_instance"])],
                  ["queue", "ingest_api", "worker"], trigger=["async_delivery", "event_ingest", "batch_pipeline"]),
    DecisionPoint("store_tech", "Primary store",
                  "Domain records need durable, queryable storage.",
                  [Option("PostgreSQL", ["transactions", "indexes and JSON", "widely available"], ["operational dependency"],
                          {"durability": 3, "performance": 3, "simplicity": 2, "scalability": 3, "cost": 2, "compliance": 3, "operability": 3}, bonus_when=["postgres"], excludes=["no_database", "mysql", "cli_tool", "no_network"]),
                   Option("MySQL / MariaDB (the stated database)", ["transactions", "already operated by the team"], ["weaker JSON and DDL ergonomics than PostgreSQL"],
                          {"durability": 3, "performance": 3, "simplicity": 2, "scalability": 3, "cost": 2, "compliance": 3, "operability": 3}, needs=["mysql"], bonus_when=["mysql"], excludes=["no_database"]),
                   Option("Managed document store (DynamoDB/MongoDB, as stated)", ["scales without operations", "flexible records"], ["no cross-record transactions by default", "query patterns must be designed up front"],
                          {"durability": 3, "performance": 3, "simplicity": 2, "scalability": 3, "cost": 1, "compliance": 2, "operability": 3}, needs=["document_db"], bonus_when=["document_db"], excludes=["no_database"]),
                   Option("SQLite", ["zero operations", "single file"], ["one writer at a time", "no network access"],
                          {"durability": 2, "performance": 2, "simplicity": 3, "scalability": 0, "cost": 3, "compliance": 2, "operability": 2}, excludes=["containers", "multi_instance", "no_database"]),
                   Option("Files (JSON/CSV on disk)", ["no dependencies", "human readable"], ["no transactions or concurrency"],
                          {"durability": 1, "performance": 1, "simplicity": 3, "scalability": 0, "cost": 3, "compliance": 1, "operability": 1}, excludes=["containers", "multi_instance"], bonus_when=["no_database"]),
                   Option("In-memory", ["fastest", "trivial"], ["lost on restart"],
                          {"durability": 0, "performance": 3, "simplicity": 3, "scalability": 0, "cost": 3, "compliance": 0, "operability": 2}, excludes=["containers", "multi_instance", "mysql", "postgres"])],
                  ["store"], trigger=["*"]),
    DecisionPoint("isolation", "Per-target isolation of outbound work",
                  "One slow or failing target must not delay work for the others.",
                  [Option("Partition the queue by target; each lease takes one partition with a per-partition concurrency cap",
                          ["a slow target only occupies its own slot", "fair scheduling across targets"],
                          ["more bookkeeping in the queue", "partition count = target count"],
                          {"isolation": 3, "performance": 2, "simplicity": 1, "scalability": 3, "availability": 3}),
                   Option("Single FIFO queue with a global worker pool",
                          ["simplest"], ["one slow target blocks pool slots for everyone (head-of-line blocking)"],
                          {"isolation": 0, "performance": 2, "simplicity": 3, "scalability": 2, "availability": 1}),
                   Option("Hash targets to N shards, one worker pool per shard",
                          ["bounded blast radius without per-target state"], ["a slow target still delays its shard"],
                          {"isolation": 2, "performance": 2, "simplicity": 2, "scalability": 2, "availability": 2})],
                  ["queue", "worker"], trigger=["isolation"]),
    DecisionPoint("retry_scheduling", "Where delayed retries wait",
                  "Failed deliveries must run again at a computed future time.",
                  [Option("not_before column on the work item; the scheduler promotes due rows",
                          ["one durable store for queued and delayed items", "trivial to inspect and to redeliver manually"],
                          ["a periodic scan (index on not_before)"],
                          {"durability": 3, "simplicity": 3, "performance": 2, "operability": 3}),
                   Option("Redis sorted set keyed by due time", ["cheap due-time queries"], ["a second store to keep consistent"],
                          {"durability": 1, "simplicity": 2, "performance": 3, "operability": 2}, needs=["redis"]),
                   Option("In-process timers", ["no store"], ["lost on restart"],
                          {"durability": 0, "simplicity": 3, "performance": 3, "operability": 1}, excludes=["durable_required", "containers", "multi_instance"])],
                  ["scheduler", "queue"], trigger=["async_delivery"]),
    DecisionPoint("topology", "Process topology",
                  "The same code base serves requests and performs background work.",
                  [Option("One image, role by flag: `api` and `worker` processes scale independently",
                          ["stateless containers", "independent scaling of ingress and outbound work", "one build"],
                          ["two deployables to operate"],
                          {"scalability": 3, "isolation": 2, "simplicity": 2, "availability": 3, "operability": 3, "cost": 2}),
                   Option("Single process with background threads", ["one deployable"], ["request latency competes with outbound work", "cannot scale roles separately"],
                          {"scalability": 1, "isolation": 1, "simplicity": 3, "availability": 1, "operability": 2, "cost": 3}),
                   Option("Separate services per concern (ingest, admin, delivery)", ["clear ownership"], ["three deployables for a team of three", "shared schema anyway"],
                          {"scalability": 3, "isolation": 3, "simplicity": 1, "availability": 3, "operability": 1, "cost": 1})],
                  ["surface_api", "admin_api", "ingest_api", "worker", "scheduler", "policy"], trigger=["async_delivery", "batch_pipeline", "scheduler_jobs"]),
    DecisionPoint("ingest_style", "How producers publish",
                  "Internal services must hand events to the system.",
                  [Option("HTTP publish endpoint with idempotency keys", ["language-agnostic", "one contract"], ["one network hop", "callers need retries"],
                          {"simplicity": 2, "durability": 3, "performance": 2, "operability": 3}),
                   Option("In-process client library that writes the outbox in the caller's transaction", ["no lost events at the source"], ["couples callers to our schema and language"],
                          {"simplicity": 1, "durability": 3, "performance": 3, "operability": 1}),
                   Option("Message bus topic", ["decoupled"], ["new infrastructure"],
                          {"simplicity": 1, "durability": 3, "performance": 3, "operability": 2}, needs=["broker"])],
                  ["ingest_api"], trigger=["event_ingest"]),
    DecisionPoint("auth_scheme", "Caller authentication",
                  "Management operations must be attributable to a customer or operator.",
                  [Option("API keys per customer, hashed at rest, sent as a bearer token", ["simple", "scriptable"], ["no delegation or expiry unless added"],
                          {"security": 2, "simplicity": 3, "usability": 2}),
                   Option("OAuth2 / OIDC with the platform's identity provider", ["single sign-on", "expiry and scopes"], ["integration effort"],
                          {"security": 3, "simplicity": 1, "usability": 3}, needs=["idp"], bonus_when=["idp"]),
                   Option("Mutual TLS", ["strong", "no secrets in headers"], ["certificate lifecycle for every customer"],
                          {"security": 3, "simplicity": 0, "usability": 1}, bonus_when=["client_certs"]),
                   Option("Email one-time code / magic link (no account needed)", ["no password, no sign-up", "works for occasional customers"], ["depends on email delivery", "weak against mailbox compromise"],
                          {"security": 2, "simplicity": 2, "usability": 3}, needs=["email_auth"], bonus_when=["email_auth"])],
                  ["auth", "admin_api"], trigger=["auth", "admin_api", "security"]),
    DecisionPoint("secret_storage", "Storage of signing secrets",
                  "Per-endpoint secrets are sensitive and must be readable by workers.",
                  [Option("Encrypted column (AES-GCM) with a key from the environment/KMS", ["one store", "workers read directly"], ["key rotation procedure needed"],
                          {"security": 2, "simplicity": 3, "operability": 2, "compliance": 2}),
                   Option("External secrets manager (Vault/KMS-backed)", ["audited access", "rotation built in"], ["latency and a new dependency on the hot path"],
                          {"security": 3, "simplicity": 1, "operability": 1, "compliance": 3}, needs=["vault"]),
                   Option("Plaintext column", ["simplest"], ["database dump exposes every customer secret"],
                          {"security": 0, "simplicity": 3, "operability": 3, "compliance": 0})],
                  ["secrets", "signer"], trigger=["signing"]),
    DecisionPoint("outbound_safety", "Outbound request safety",
                  "The system makes HTTP requests to customer-supplied URLs.",
                  [Option("Resolve and block private/link-local ranges; pin the resolved IP; cap body size and redirects; per-request timeout",
                          ["closes SSRF and slow-loris classes"], ["a resolver step per request"],
                          {"security": 3, "isolation": 2, "simplicity": 2}),
                   Option("Plain HTTP client with a timeout", ["simplest"], ["SSRF into internal networks", "unbounded response bodies"],
                          {"security": 0, "isolation": 1, "simplicity": 3})],
                  ["dispatcher"], trigger=["async_delivery", "outbound"]),
    DecisionPoint("concurrency", "Concurrency control for conflicting writes",
                  "Two callers may change the same record at the same time and the result must be consistent.",
                  [Option("Optimistic concurrency: version column checked on every update; conflict returns 409 and the caller retries",
                          ["no locks held across requests", "works with stateless instances"], ["callers must handle 409"],
                          {"consistency": 3, "performance": 3, "simplicity": 2, "scalability": 3}),
                   Option("Row locks inside a short transaction (SELECT ... FOR UPDATE)",
                          ["simple mental model", "no client retry"], ["lock waits under contention", "needs a transactional store"],
                          {"consistency": 3, "performance": 2, "simplicity": 3, "scalability": 2}, needs=["postgres", "mysql"]),
                   Option("Last write wins", ["nothing to implement"], ["lost updates"],
                          {"consistency": 0, "performance": 3, "simplicity": 3, "scalability": 3})],
                  ["store", "core"], trigger=["consistency"]),
    DecisionPoint("redundancy", "Redundancy for the availability target",
                  "The availability target must be met through instance failures and deploys.",
                  [Option("Two or more interchangeable instances per role behind the ingress, health checks, rolling deploys",
                          ["survives one instance failure", "zero-downtime deploys"], ["needs stateless instances and a shared store"],
                          {"availability": 3, "simplicity": 2, "cost": 2, "scalability": 3}),
                   Option("Single instance with health-based restart", ["simplest", "cheapest"], ["restart time is downtime", "deploys are downtime"],
                          {"availability": 1, "simplicity": 3, "cost": 3, "scalability": 1}),
                   Option("Active-active across two regions", ["survives a regional outage"], ["data replication and conflict handling", "cost"],
                          {"availability": 3, "simplicity": 0, "cost": 0, "scalability": 3}, excludes=["single_region"], bonus_when=["multi_region"])],
                  ["surface_api", "admin_api", "ingest_api", "worker", "push"], trigger=["availability"]),
    DecisionPoint("data_residency", "Where personal data may live",
                  "The requirements pin personal data to a jurisdiction.",
                  [Option("Single region in the stated jurisdiction for every store, queue, backup and log; no cross-region replication of personal data", ["simple to audit", "no transfer mechanism needed"], ["a regional outage is a full outage"],
                          {"compliance": 3, "simplicity": 3, "availability": 1, "cost": 3}, bonus_when=["data_residency"]),
                   Option("Primary in the stated jurisdiction; encrypted backups replicated to a second region under a transfer agreement", ["survives a regional loss"], ["transfer mechanism and key custody to document"],
                          {"compliance": 2, "simplicity": 1, "availability": 3, "cost": 1})],
                  ["store", "queue", "files"], trigger=["data_residency"]),
    DecisionPoint("orchestration", "How scheduled loads are orchestrated",
                  "Loads have dependencies, retries and a freshness SLA; something must run them and show their state.",
                  [Option("The existing orchestrator (Airflow/Dagster/Prefect) with one DAG per source", ["retries, backfills and a UI for free", "already operated"], ["another repository to keep in sync", "DAG code is not unit-tested by default"],
                          {"operability": 3, "simplicity": 2, "cost": 3, "durability": 3}, needs=["orchestrator"], bonus_when=["orchestrator"]),
                   Option("Cron-triggered container per load with state in the primary store", ["nothing new to operate"], ["backfills and dependencies are hand-written", "no UI"],
                          {"operability": 1, "simplicity": 3, "cost": 3, "durability": 2}),
                   Option("Application-level scheduler (the scheduler component) with a job table", ["state and retries in our own tables", "testable"], ["we own the scheduler bugs"],
                          {"operability": 2, "simplicity": 2, "cost": 3, "durability": 3})],
                  ["loader", "scheduler"], trigger=["etl_pipeline"]),
    DecisionPoint("time_series_store", "Time-series storage",
                  "High-rate readings must be written continuously and queried by time window.",
                  [Option("TimescaleDB hypertables in PostgreSQL (time partitioning, compression, retention policies)",
                          ["one database", "retention by policy", "fast window queries"], ["an extension to operate"],
                          {"performance": 3, "durability": 3, "simplicity": 2, "operability": 3, "cost": 3}, needs=["timeseries_db"], bonus_when=["timeseries_db"]),
                   Option("Plain PostgreSQL tables partitioned by day", ["no extension"], ["manual partition management", "slower window queries"],
                          {"performance": 2, "durability": 3, "simplicity": 3, "operability": 2, "cost": 3}, needs=["postgres"]),
                   Option("ClickHouse", ["columnar, very fast aggregation"], ["a second database", "eventual consistency"],
                          {"performance": 3, "durability": 2, "simplicity": 1, "operability": 1, "cost": 2}, needs=["clickhouse"])],
                  ["store"], trigger=["timeseries_db", "mqtt_ingest"]),
    DecisionPoint("vector_store", "Vector index for semantic search",
                  "Embeddings must be stored and searched by similarity.",
                  [Option("pgvector in PostgreSQL", ["one database", "transactional with the documents"], ["ANN performance limits at tens of millions of vectors"],
                          {"performance": 2, "simplicity": 3, "operability": 3, "cost": 3}, needs=["vector_db"], bonus_when=["vector_db"]),
                   Option("Dedicated vector database", ["scales to hundreds of millions of vectors"], ["a new service to operate", "sync with the source of truth"],
                          {"performance": 3, "simplicity": 1, "operability": 1, "cost": 1}),
                   Option("In-process index (FAISS/HNSW) rebuilt from the store", ["fast", "no service"], ["memory bound", "rebuild on restart"],
                          {"performance": 3, "simplicity": 2, "operability": 2, "cost": 3})],
                  ["search", "store"], trigger=["vector_db"]),
    DecisionPoint("api_style", "API style", "Clients need a programmable surface.",
                  [Option("REST/JSON over HTTP", ["universal tooling", "cacheable reads"], ["over-fetching on nested data"],
                          {"usability": 3, "simplicity": 3, "performance": 2}),
                   Option("gRPC", ["typed contracts", "streaming"], ["browser and debugging friction"],
                          {"usability": 2, "simplicity": 1, "performance": 3}),
                   Option("GraphQL", ["flexible queries"], ["complexity budget for a small team"],
                          {"usability": 2, "simplicity": 1, "performance": 2})],
                  ["surface_api", "admin_api"], trigger=["crud_api", "admin_api"]),
    DecisionPoint("cache_policy", "Caching", "Repeated reads dominate the request mix.",
                  [Option("Read-through cache with TTL and explicit invalidation on write", ["bounded staleness"], ["invalidation paths to maintain"],
                          {"performance": 3, "simplicity": 2, "operability": 2}),
                   Option("No cache; rely on database indexes", ["no staleness"], ["hot rows become the bottleneck"],
                          {"performance": 1, "simplicity": 3, "operability": 3})],
                  ["cache"], trigger=["cache"]),

    DecisionPoint("video_delivery", "How media reaches viewers",
                  "Large files are watched by many people at once; the application must not proxy the bytes.",
                  [Option("Object storage behind a CDN, signed expiring URLs, HTTP range requests; the application never streams bytes",
                          ["scales with viewers, not with instances", "resumable playback for free"], ["CDN cost by egress", "URL signing and expiry to get right"],
                          {"performance": 3, "scalability": 3, "cost": 2, "simplicity": 2, "availability": 3, "security": 2}),
                   Option("Signed URLs straight from object storage (no CDN)", ["simplest", "cheap at low volume"], ["latency and egress from one region", "storage bandwidth caps"],
                          {"performance": 1, "scalability": 2, "cost": 3, "simplicity": 3, "availability": 2, "security": 2}),
                   Option("Application streams the file", ["one place for authorisation"], ["every viewer holds an application connection", "memory and bandwidth on the instances"],
                          {"performance": 0, "scalability": 0, "cost": 2, "simplicity": 2, "availability": 1, "security": 3})],
                  ["files", "cdn"], trigger=["media"]),
    DecisionPoint("tenancy_model", "Tenant isolation model",
                  "Several customers share the deployment; their data must never mix.",
                  [Option("Shared schema with a tenant_id column on every table, enforced by the tenant context (and row-level security where available)",
                          ["one database to operate", "cheap per tenant", "cross-tenant analytics are simple"],
                          ["one missed predicate leaks data", "noisy tenants share resources"],
                          {"isolation": 2, "simplicity": 3, "cost": 3, "compliance": 2, "scalability": 3, "operability": 3, "security": 2}),
                   Option("Schema per tenant in one database", ["stronger isolation by construction", "per-tenant restore"],
                          ["migrations run N times", "connection pooling per schema"],
                          {"isolation": 3, "simplicity": 2, "cost": 2, "compliance": 3, "scalability": 2, "operability": 2, "security": 3}, needs=["postgres"]),
                   Option("Database (or deployment) per tenant", ["complete isolation", "per-tenant residency"],
                          ["cost and operations scale with tenants", "no cross-tenant queries"],
                          {"isolation": 3, "simplicity": 1, "cost": 0, "compliance": 3, "scalability": 1, "operability": 1, "security": 3})],
                  ["tenancy", "store"], trigger=["multi_tenant"]),
    DecisionPoint("workflow_impl", "How the approval workflow is implemented",
                  "Items move through states with rules about who may move them and when.",
                  [Option("Explicit state machine in code: a transitions table (state, action, role) -> state, history rows in the store",
                          ["readable and testable", "no new infrastructure"], ["custom UI for the workflow definition if it must change at runtime"],
                          {"simplicity": 3, "operability": 3, "cost": 3, "usability": 2, "compliance": 3}),
                   Option("Embedded workflow library (state-machine package)", ["declarative definitions", "guards and callbacks built in"],
                          ["another dependency", "persistence adapter to maintain"],
                          {"simplicity": 2, "operability": 2, "cost": 3, "usability": 2, "compliance": 2}),
                   Option("External BPM engine", ["business users edit the process", "rich tooling"],
                          ["a large system to operate", "a team of two cannot own it"],
                          {"simplicity": 0, "operability": 1, "cost": 1, "usability": 3, "compliance": 3})],
                  ["workflow"], trigger=["workflow"]),
    DecisionPoint("reporting_store", "Where reports are computed",
                  "Aggregations over history must not slow down the transactional path.",
                  [Option("Materialised aggregates built by a scheduled job into report tables in the primary database",
                          ["one database", "reports are a read of precomputed rows"], ["freshness = job interval", "aggregate design per report"],
                          {"performance": 2, "simplicity": 3, "cost": 3, "operability": 3, "scalability": 2}),
                   Option("Read replica queried directly", ["fresh", "no aggregate design"], ["heavy queries still hit a copy of the OLTP schema", "replica lag"],
                          {"performance": 2, "simplicity": 2, "cost": 2, "operability": 2, "scalability": 2}, needs=["postgres", "mysql"]),
                   Option("Columnar analytics store (ClickHouse / warehouse) fed by a pipeline", ["fast over years of data", "ad-hoc analytics"],
                          ["a second store and a pipeline", "eventual consistency"],
                          {"performance": 3, "simplicity": 1, "cost": 1, "operability": 1, "scalability": 3}, needs=["clickhouse"], bonus_when=["clickhouse"])],
                  ["reporting", "store"], trigger=["reporting"]),
    DecisionPoint("backup_strategy", "Backup and recovery",
                  "Data must be recoverable within the recovery time and point objectives.",
                  [Option("Managed daily snapshots plus continuous WAL archiving (point-in-time recovery), restore tested monthly",
                          ["RPO of minutes", "restore tested, not assumed"], ["storage cost of WAL", "a monthly drill to run"],
                          {"availability": 3, "durability": 3, "compliance": 3, "cost": 2, "simplicity": 2, "operability": 3}, needs=["postgres", "mysql"]),
                   Option("Nightly logical dump to object storage", ["simple", "portable"], ["RPO of a day", "restore time grows with data"],
                          {"availability": 1, "durability": 2, "compliance": 2, "cost": 3, "simplicity": 3, "operability": 2}),
                   Option("Cross-region replica with promotion runbook", ["survives a regional outage", "RPO near zero"], ["double the database cost", "failover drills"],
                          {"availability": 3, "durability": 3, "compliance": 3, "cost": 0, "simplicity": 1, "operability": 1}, excludes=["single_region"])],
                  ["backup", "store"], trigger=["backup_dr"]),
    DecisionPoint("pii_protection", "Protection of personal data",
                  "Personal data is stored and must be protected and deletable.",
                  [Option("Field-level encryption for identifiers and sensitive fields with a key outside the database; pseudonymous ids elsewhere",
                          ["a dump does not expose people", "deletion = key destruction where fields are only encrypted"],
                          ["cannot index encrypted fields", "key management"],
                          {"security": 3, "compliance": 3, "simplicity": 1, "performance": 2, "cost": 2}),
                   Option("Encryption at rest by the platform plus strict access control and audit", ["no application changes", "indexes work"],
                          ["anyone with database access sees everything"],
                          {"security": 2, "compliance": 2, "simplicity": 3, "performance": 3, "cost": 3}),
                   Option("Separate personal-data store with tokenised references", ["blast radius contained", "deletion in one place"],
                          ["joins across two stores", "a second store"],
                          {"security": 3, "compliance": 3, "simplicity": 1, "performance": 1, "cost": 1})],
                  ["data_protection", "store"], trigger=["compliance_data"]),
    DecisionPoint("sync_conflicts", "Conflict resolution for offline changes",
                  "Two devices may change the same record while offline.",
                  [Option("Server wins with per-field last-writer-wins and a conflict report to the device", ["simple", "predictable"], ["lost edits on the same field"],
                          {"consistency": 2, "simplicity": 3, "usability": 2, "performance": 3}),
                   Option("Version vectors: detect concurrent edits and ask the user", ["no silent loss"], ["UI for conflicts", "more bookkeeping"],
                          {"consistency": 3, "simplicity": 1, "usability": 2, "performance": 2}),
                   Option("CRDT per field type", ["merges automatically"], ["only for data that has a CRDT shape", "library dependency"],
                          {"consistency": 3, "simplicity": 0, "usability": 3, "performance": 2})],
                  ["sync"], trigger=["mobile_offline"]),
    DecisionPoint("legacy_integration", "Integration with the existing system",
                  "Records must flow between the new system and the one that already exists.",
                  [Option("API façade (anti-corruption layer) calling the legacy system's interfaces, with a translation layer and retries",
                          ["legacy schema never leaks in", "quirks isolated in one module"], ["depends on the legacy system's uptime"],
                          {"simplicity": 2, "durability": 2, "operability": 3, "consistency": 2, "cost": 3}),
                   Option("Scheduled batch file exchange (CSV/fixed format) through a shared drop", ["works with any system", "no live coupling"],
                          ["latency of the schedule", "reconciliation of partial files"],
                          {"simplicity": 3, "durability": 3, "operability": 2, "consistency": 1, "cost": 3}, bonus_when=["nightly_batch"]),
                   Option("Change data capture from the legacy database", ["near real time", "no legacy code changes"],
                          ["coupled to the legacy schema", "capture tooling to operate"],
                          {"simplicity": 1, "durability": 3, "operability": 1, "consistency": 3, "cost": 1})],
                  ["legacy_adapter"], trigger=["legacy_integration"]),
    DecisionPoint("release_strategy", "How changes reach users",
                  "Features must reach users gradually and be reversible.",
                  [Option("Feature flags with percentage rollout and a kill switch; deploys are separate from releases",
                          ["reversible without a deploy", "gradual exposure"], ["flag debt: remove flags after rollout"],
                          {"availability": 3, "operability": 3, "simplicity": 2, "usability": 3}),
                   Option("Blue/green deploys", ["instant rollback of the whole release"], ["all-or-nothing exposure", "double capacity during cutover"],
                          {"availability": 3, "operability": 2, "simplicity": 2, "usability": 1}),
                   Option("Rolling deploys only", ["nothing to build"], ["rollback = redeploy", "no partial exposure"],
                          {"availability": 2, "operability": 2, "simplicity": 3, "usability": 1})],
                  ["flags"], trigger=["feature_flags"]),
    DecisionPoint("i18n_approach", "Localisation approach",
                  "Text, dates and amounts must appear in each user's language and locale.",
                  [Option("Message catalogues in the code base (ICU message format), locale from the user's profile then the request",
                          ["translations reviewed with code", "plural and gender rules handled"], ["a release per translation change"],
                          {"simplicity": 3, "usability": 3, "operability": 3, "cost": 3}),
                   Option("Translations stored in the database and editable at runtime", ["no release for wording"], ["missing keys at runtime", "caching"],
                          {"simplicity": 2, "usability": 3, "operability": 2, "cost": 2})],
                  ["i18n"], trigger=["i18n"]),
    DecisionPoint("message_delivery", "Message delivery to connected clients",
                  "Messages must reach recipients who are online now and later.",
                  [Option("Store first, then fan out over the push gateway; clients catch up from the store on reconnect",
                          ["nothing lost when offline", "one source of truth"], ["a read on reconnect"],
                          {"durability": 3, "consistency": 3, "performance": 2, "simplicity": 3}),
                   Option("Publish to a broker topic per conversation; clients subscribe", ["scales fan-out"], ["history needs a separate store anyway", "new infrastructure"],
                          {"durability": 2, "consistency": 2, "performance": 3, "simplicity": 1}, needs=["broker"])],
                  ["messaging", "push"], trigger=["messaging"]),
]}

# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------

RISKS: dict[str, RiskT] = {r.key: r for r in [
    RiskT("duplicate_delivery", "At-least-once delivery means a target can receive the same event twice (crash between call and ack).",
          "high", "medium", "Send a stable event id and attempt number in headers; document idempotent consumption; never retry on 2xx.", ["worker", "queue"]),
    RiskT("thundering_retry", "Many targets fail at once (regional outage) and their retries align, creating a burst.",
          "medium", "medium", "Add jitter to the backoff schedule and cap concurrent deliveries per partition and globally.", ["scheduler", "worker"]),
    RiskT("ssrf", "Customer-supplied URLs can point at internal addresses or metadata services.",
          "high", "high", "Resolve before connecting, block private ranges, pin the IP, forbid redirects to non-public hosts.", ["dispatcher"]),
    RiskT("secret_exposure", "Signing secrets in the database are exposed by a dump or a read-only breach.",
          "medium", "high", "Encrypt at rest with a key outside the database; log secret reads; rotate on suspicion.", ["secrets"]),
    RiskT("queue_bloat", "Retried and dead-lettered items accumulate and slow the lease query.",
          "medium", "medium", "Partial index on (partition, not_before) for live items; archive terminal items on a schedule.", ["queue"]),
    RiskT("clock_skew", "Timestamp-based signatures and not_before scheduling depend on wall clocks.",
          "low", "medium", "Use the database clock for scheduling; tolerate a bounded skew window when verifying timestamps.", ["signer", "scheduler"]),
    RiskT("notification_storm", "A widespread failure disables many targets and emails every owner at once.",
          "low", "medium", "Rate-limit notifications per owner and batch them.", ["notifier", "policy"]),
    RiskT("single_writer", "A single-writer store becomes the ceiling under concurrent load.",
          "medium", "medium", "Keep write transactions short; measure before sharding.", ["store"]),
    RiskT("late_source", "A source delivers late or re-delivers corrected files; the day's partition is stale or double-counted.", "high", "medium",
          "Freshness table per source; alert after the stated lateness; loads replace a partition instead of appending, so a re-run is idempotent.", ["loader"]),
    RiskT("schema_drift", "Entities evolve; migrations run against live data.",
          "medium", "medium", "Versioned migrations applied before deploy; additive changes first, removals one release later.", ["store"]),
    RiskT("unbounded_input", "Payloads or uploads without size limits exhaust memory or disk.",
          "medium", "medium", "Enforce size limits at the surface; reject early with a clear error.", ["surface_api", "ingest_api", "files"]),
    RiskT("auth_bypass", "A management operation reachable without authentication.",
          "low", "high", "Authenticate in one middleware for every management route; test every route unauthenticated.", ["admin_api", "auth"]),
    RiskT("metric_cardinality", "Per-target labels on metrics explode cardinality.",
          "medium", "low", "Label by outcome and partition class, not by target id; expose per-target detail through the API instead.", ["observability"]),
    RiskT("unrecognised", "Parts of the requirements were not recognised by the catalogue and received a generic decomposition.",
          "medium", "medium", "Review the components marked generic; refine responsibilities and interfaces before briefing.", ["core"]),

    RiskT("kyc_outage", "The identity/credit provider is down or slow and applications pile up or time out.",
          "medium", "medium", "Timeouts and retries with backoff; queue the check and let the application wait in a 'pending verification' state; alert on provider error rate.", ["verifier"]),
    RiskT("media_egress", "Media egress cost and bandwidth grow with viewers, not with the team's plans.",
          "medium", "medium", "Serve through the CDN with caching headers; monitor egress per day; cap bitrate variants.", ["cdn", "files"]),
    RiskT("tenant_leak", "A query without the tenant predicate returns another customer's rows.",
          "medium", "high", "Every store access goes through the tenant context; a test issues each operation as tenant A against tenant B's ids and expects 404.", ["tenancy", "store"]),
    RiskT("workflow_stuck", "An instance waits forever on an approver who left.",
          "medium", "medium", "Step deadlines with escalation to the next role; a report of instances past their deadline.", ["workflow"]),
    RiskT("self_approval", "A requester approves their own item.",
          "medium", "high", "Transition rules forbid the requester's principal for approve/reject; tested per transition.", ["workflow"]),
    RiskT("report_staleness", "Dashboards show figures from a failed or late run without saying so.",
          "medium", "low", "Every report row carries the run's completion time; the UI shows it; alert when a run is late.", ["reporting"]),
    RiskT("backup_untested", "Backups exist but have never been restored.",
          "high", "high", "A scheduled test restore into a scratch environment; a backup is not counted as verified until it passes.", ["backup"]),
    RiskT("flag_debt", "Old flags stay in the code and multiply configurations.",
          "high", "low", "Each flag has an owner and an expiry; a check fails the build for flags past expiry.", ["flags"]),
    RiskT("legacy_coupling", "The legacy system's schema or outages leak into the new domain.",
          "medium", "medium", "All translation in the adapter; the core never sees legacy types; the adapter degrades to read-only when the legacy system is down.", ["legacy_adapter"]),
    RiskT("sync_conflict_loss", "Concurrent offline edits silently overwrite each other.",
          "medium", "medium", "Conflicts are detected per field and reported to the device; the losing version is kept in history.", ["sync"]),
    RiskT("pii_spread", "Personal data is copied into logs, reports and backups where deletion cannot reach it.",
          "high", "high", "Log only pseudonymous ids; reports carry aggregates or pseudonyms; deletion covers backups by expiry.", ["data_protection", "observability", "reporting"]),
    RiskT("missing_translation", "A missing message key ships as a blank or the key itself.",
          "medium", "low", "Fallback to the default locale; a build check that every key exists in the default catalogue.", ["i18n"]),
]}

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

PATTERNS: list[Pattern] = [
    Pattern("crud_api", "Resource API", [(r"\bapi\b", 1), (r"\bhttp\b|\brest\b", 1), (r"\bcreate\b|\bcreat", 1), (r"\blist\b", 1), (r"\bdelete\b|\bremove\b", 1), (r"\bendpoint", 1), (r"\bclient", 1)],
            ["surface_api", "core", "store"], ["record"], ["request"], ["api_style", "store_tech"], ["unbounded_input", "schema_drift"],
            "Clients read and write domain resources over HTTP."),
    Pattern("admin_api", "Management API", [(r"\badmin\b", 2), (r"\bmanage\b|\bmanagement\b", 2), (r"\bregister\b", 1), (r"\bconfigure\b|\bsettings\b", 1), (r"\bcustomers? (?:can|manage|register)", 2)],
            ["admin_api", "auth", "core", "store"], ["principal", "record"], ["manage"], ["auth_scheme", "api_style"], ["auth_bypass"],
            "Customers or operators manage resources through an authenticated API."),
    Pattern("event_ingest", "Event ingestion", [(r"\bpublish(?:es|ed|ing)? (?:an? )?events?\b", 3), (r"\bpublish", 1), (r"\bevents?\b", 1), (r"\bproducer|internal services?\b", 1), (r"\bingest(?:s|ed|ion)?\b(?! (?:daily|nightly|weekly|hourly)? ?(?:exports?|files?|csv|batch))", 1), (r"\bemit", 1), (r"\bevent stream|\bstream of events\b", 2)],
            ["ingest_api", "core", "store", "queue"], ["event", "work_item"], ["ingest"], ["ingest_style", "queue_tech", "store_tech"], ["unbounded_input"],
            "Producers hand events to the system, which persists them before acknowledging."),
    Pattern("async_delivery", "Asynchronous delivery with retries",
            [(r"\bdeliver(?:s|ed|y|ies|ing)?\b(?! to the billing| to the (?:data|analytics))", 2), (r"\bwebhook endpoints?\b|\bcustomer endpoints?\b|\bsubscriber", 3), (r"\bretr(?:y|ied|ies)\b", 2), (r"\bbackoff\b", 2), (r"\battempts?\b", 1), (r"\bat[- ]least[- ]once\b(?! delivery to)", 1), (r"\bqueue", 1), (r"\bworker", 1), (r"\bredeliver", 1)],
            ["queue", "worker", "scheduler", "dispatcher", "core", "store"], ["work_item", "attempt"], ["deliver", "retry"],
            ["queue_tech", "retry_scheduling", "topology", "outbound_safety", "store_tech"], ["duplicate_delivery", "thundering_retry", "ssrf", "queue_bloat", "clock_skew"],
            "Work is queued durably and performed by workers with a retry schedule."),
    Pattern("webhook_delivery", "Webhooks to customer endpoints",
            [(r"\bwebhook endpoints?\b|\bcustomer endpoints?\b|\bsubscriber urls?\b|\bregister(?:s|ed)? (?:webhook )?endpoints?\b", 3), (r"\bdeliver(?:s|ed|y)? .{0,40}\b(?:to every|to each|to the) (?:matching )?endpoint", 3), (r"\bsigned (?:json )?events?\b", 2)],
            ["endpoint", "dispatcher"], ["target"], [], ["outbound_safety"], ["ssrf"], "Events are delivered to endpoints customers registered."),
    Pattern("signing", "Request signing", [(r"\bsign(?:ed|ing|ature)?\b(?! urls?\b)(?!-in)(?! in\b)(?! up\b)", 2), (r"\bhmac\b", 2), (r"\bsecret", 1), (r"\brotat", 1)],
            ["signer", "secrets"], ["secret"], [], ["secret_storage"], ["secret_exposure", "clock_skew"],
            "Outbound requests carry an HMAC signature; secrets rotate with a grace window."),
    Pattern("notification", "Notifications", [(r"\bemail", 2), (r"\bnotif(?:y|ied|ication)", 2), (r"\bsms\b", 2), (r"\bping the owner\b|\bpages? the\b", 2)],
            ["notifier", "email"], [], [], [], ["notification_storm"], "The system notifies people through an external channel."),
    Pattern("chat_notification", "Chat-channel notifications", [(r"\bslack\b|\bteams\b|\bdiscord\b|\bchat channel\b", 3), (r"#[a-z][a-z0-9_-]+", 1)],
            ["notifier", "chat"], [], [], [], ["notification_storm"], "The system posts to a chat channel (Slack/Teams)."),
    Pattern("health_policy", "Automatic disable policy", [(r"disabled? automatically", 3), (r"fail(?:s|ing|ed)? continuously", 3), (r"\bcircuit", 2), (r"\bautomatically\b", 1)],
            ["policy", "core", "notifier"], [], ["disable"], [], ["notification_storm"], "Targets that keep failing are disabled by policy and the owner is told."),
    Pattern("observability", "Observability", [(r"\bmetrics?\b", 2), (r"\bprometheus\b", 2), (r"\bstructured logs?\b|\blogs?\b|\blogging\b", 1), (r"\bhealth", 1), (r"\balert", 1), (r"\bdashboard", 1), (r"\btrac(?:e|ing)\b", 1)],
            ["observability"], [], [], [], ["metric_cardinality"], "Metrics, structured logs and health endpoints for operations."),
    Pattern("auth", "Authentication and authorization", [(r"\bauthenticat", 2), (r"\bauthoriz", 2), (r"\blogin\b|\bsign[- ]in\b", 2), (r"\bapi keys?\b", 2), (r"\boauth\b|\bsso\b|\boidc\b", 2), (r"\bpermissions?\b|\broles?\b", 1), (r"\btoken", 1)],
            ["auth", "store"], ["principal"], [], ["auth_scheme"], ["auth_bypass"], "Callers are authenticated and authorized."),
    Pattern("rate_limiting", "Rate limiting", [(r"rate[- ]limit", 3), (r"\bthrottl", 2), (r"\bquota", 2)],
            ["ratelimit"], [], [], [], [], "Request budgets per caller."),
    Pattern("cache", "Caching", [(r"\bcach(?:e|es|ed|ing)\b", 3)], ["cache"], [], [], ["cache_policy"], [], "Hot reads are cached."),
    Pattern("search", "Search", [(r"\bsearch", 2), (r"full[- ]text", 3), (r"\bfilter", 1)], ["search", "store"], [], [], [], [], "Users search and filter records."),
    Pattern("file_storage", "File storage", [(r"\bupload", 2), (r"\bfiles?\b", 1), (r"\battachment", 2), (r"\bblob", 2), (r"\bs3\b", 2), (r"\bimages?\b|\bphotos?\b|\bdocuments?\b", 1)],
            ["files", "core"], ["file"], [], [], ["unbounded_input"], "Files are uploaded, stored and served."),
    Pattern("batch_pipeline", "Batch processing", [(r"\bbatch", 2), (r"\bnightly\b|\bdaily\b|\bweekly\b|\bhourly\b", 2), (r"\betl\b", 3), (r"\bpipeline", 1), (r"\baggregat", 1), (r"\breport", 1)],
            ["batch", "scheduler", "store"], ["job_run"], ["batch_run"], ["store_tech", "topology"], ["schema_drift"], "Scheduled jobs process stored records in windows."),
    Pattern("etl_pipeline", "Extract-transform-load pipeline", [(r"\bnormali[sz]e\b|\bdeduplicate\b|\bload(?:s|ed|ing)? into\b|\btransform", 2), (r"\bsnowflake\b|\bbigquery\b|\bredshift\b|\bwarehouse\b|\bdbt\b|\blooker\b", 2), (r"\bfiles?/day\b|\bexports? from\b|\bcsv/json\b|\bs3\b", 1), (r"\bfreshness\b|\bpartitioned by\b|\bre-?run\b", 1)],
            ["loader", "warehouse", "files", "scheduler"], ["job_run"], ["batch_run"], ["orchestration", "store_tech"], ["schema_drift", "late_source"], "Files from external sources are normalised and loaded into an analytics warehouse on a schedule."),
    Pattern("scheduler_jobs", "Scheduled jobs", [(r"\bcron\b", 3), (r"\bschedul", 2), (r"\bevery (?:day|hour|minute|night|week)\b", 2), (r"\bperiodic", 2), (r"\b\d+ (?:days?|hours?|minutes?) before\b", 2), (r"\breminders?\b", 2), (r"\bdeadline\b", 1)],
            ["scheduler"], [], [], [], [], "Work runs on a schedule."),
    Pattern("cli_tool", "Command-line tool", [(r"command[- ]line", 3), (r"\bcli tool\b|\bthe cli\b", 3), (r"\bcli\b", 1), (r"\bterminal\b", 2), (r"\bcommand[- ]line flags?\b|\s--[a-z]|\bsubcommands?\b", 2), (r"\bstdin\b|\bstdout\b|\bstderr\b|\bexit(?:s)? (?:with )?code", 2), (r"\bthe tool\b|\bthe user runs\b", 1)],
            ["cli", "core", "config"], [], ["cli_run"], ["store_tech"], [], "A command-line front end over the core."),
    Pattern("local_ui", "Local user interface", [(r"touch ?panel", 3), (r"\bscreen\b", 2), (r"\bgui\b", 3), (r"\bdisplay(?:s|ed)?\b", 1), (r"\bchart\b|\bgraph\b", 1), (r"\bbutton", 2), (r"\bpanel\b", 1)],
            ["ui", "core"], [], [], [], [], "A local screen shows state and takes inputs."),
    Pattern("mqtt_ingest", "MQTT ingestion", [(r"\bmqtt\b", 3), (r"\bbroker\b", 1), (r"\btopic", 1)],
            ["mqtt_consumer", "mqtt_broker", "core", "store", "queue"], ["event", "work_item"], [], ["queue_tech", "store_tech", "time_series_store"], ["duplicate_delivery", "queue_bloat"],
            "Devices publish over MQTT; the consumer persists before acknowledging."),
    Pattern("sftp_export", "SFTP export", [(r"\bsftp\b|\bftp\b", 3)], ["sftp_target", "exporter"], [], [], [], [], "Exports are dropped on an SFTP server."),
    Pattern("sms_notification", "SMS notification", [(r"\bsms\b|\btext message", 3)], ["notifier", "sms"], [], [], [], ["notification_storm"], "People are notified by SMS."),
    Pattern("geo", "Geospatial matching", [(r"\bnearest\b|\bnearby\b", 2), (r"\bgps\b|\bposition", 1), (r"\bpostgis\b|\bgeo(?!-?block)", 2), (r"\blocation", 1), (r"\bradius\b|\bwithin \d+ ?(?:km|m|miles)\b", 2)],
            ["geo", "core", "store"], [], [], ["store_tech"], [], "Positions are indexed and nearest matches are found."),
    Pattern("realtime", "Real-time push", [(r"\bwebsocket", 3), (r"real[- ]time", 2), (r"\bpush\b", 1), (r"\bstream", 1), (r"\bsse\b|server-sent", 3)],
            ["push", "core", "bus"], [], [], ["topology"], [], "Connected clients receive events as they happen."),
    Pattern("payments", "Payments", [(r"\bpayments?\b", 1), (r"\bpayment (?:provider|gateway|method)s?\b|\bprocess(?:es|ing)? payments?\b|\btake payments?\b", 3), (r"\binvoice", 2), (r"\bbilling\b", 1), (r"\bstripe\b|\bcharged?\b|\bcheckout\b", 2), (r"\bpay(?:s|ing)? (?:for|by|with)\b", 2)],
            ["payments", "psp", "store"], [], [], [], ["duplicate_delivery"], "Charges and invoices through a payment provider."),
    Pattern("ml_inference", "Model inference", [(r"\binference\b", 3), (r"\bpredict", 2), (r"\bmodel\b", 1), (r"\bembedding", 2), (r"\bclassif", 1), (r"\bllm\b", 2), (r"\bsummar", 1)],
            ["model", "core"], [], [], [], [], "Predictions are served from a versioned model."),
    Pattern("semantic_search", "Semantic search", [(r"\bembedding", 3), (r"\bsemantic search\b|\bsimilarity search\b|\bnearest neighbou?rs?\b", 3), (r"\bvector", 2)],
            ["search", "store"], [], [], ["vector_store"], [], "Records are searched by meaning through embeddings."),
    Pattern("audit_log", "Audit log", [(r"\baudit", 3), (r"who did (?:it|what)", 3), (r"\bwho (?:took|made|approved|changed|performed)\b", 2), (r"\bfor (?:regulators|auditors|compliance)\b", 2), (r"\bhistory\b", 1), (r"\brecorded with\b", 1), (r"\bmodel version\b", 1), (r"\bchange log\b|\bchangelog\b", 2)],
            ["audit"], ["audit_entry"], [], [], [], "Changes are recorded append-only with the actor."),
    Pattern("import_export", "Import and export", [(r"\bexport", 2), (r"\bimport\b", 2), (r"\bcsv\b", 2)],
            ["exporter", "core"], [], [], [], ["unbounded_input"], "Records move in and out as files."),
    Pattern("outbound", "Outbound HTTP calls", [(r"\bcalls? (?:an? |the )?(?:external|existing)", 2), (r"\bthird[- ]party api", 2), (r"\boutbound\b", 2), (r"\bfetch(?:es)? (?:tracking |updates? )?from\b", 1), (r"\bsubscriber urls?\b|\bcustomer endpoints?\b", 2), (r"\bexisting \w+ service exposes\b|\bcarrier integrations?\b|\bcalls? (?:the )?\w+ api\b", 2)],
            ["dispatcher", "external_service"], [], [], ["outbound_safety"], ["ssrf"], "The system calls external HTTP services."),
    Pattern("kyc", "Identity and credit verification", [(r"\bkyc\b", 3), (r"\bidentity verif", 3), (r"\bcredit (?:report|bureau|check|score)s?\b", 2), (r"\bverif(?:y|ies|ied) (?:the )?(?:applicant|customer|user)'?s? identity\b", 3), (r"\bsanctions? (?:list|screening)\b|\baml\b", 2)],
            ["verifier", "kyc_provider", "core"], [], ["verify_identity"], [], ["kyc_outage"], "Applicants are checked against external identity and credit sources."),
    Pattern("media", "Video and media delivery", [(r"\bvideos?\b", 2), (r"\bplayback\b|\bstream(?:s|ing)? (?:video|audio|media)\b", 2), (r"\bcdn\b", 3), (r"\bwatch(?:es|ing)?\b", 1), (r"\btranscod", 2)],
            ["files", "cdn"], [], [], ["video_delivery"], ["media_egress"], "Large media files are stored once and played by many."),
    Pattern("multi_tenant", "Multi-tenant SaaS", [(r"multi[- ]?tenan", 3), (r"\btenants?\b", 2), (r"\bper (?:customer|organi[sz]ation|workspace|account)\b", 2), (r"\borgani[sz]ations?\b|\bworkspaces?\b", 1), (r"\bnever (?:see|access) (?:each other|another)", 2)],
            ["tenancy", "auth", "store"], ["tenant"], ["tenant_request"], ["tenancy_model"], ["tenant_leak"], "Several customers share one deployment and must not see each other's data."),
    Pattern("workflow", "Approval workflow", [(r"\bapprov", 3), (r"\breject", 1), (r"\bworkflow\b", 3), (r"\bsubmit(?:s|ted)? (?:for|to)\b", 2), (r"\bescalat", 2), (r"\b(?:draft|submitted|approved|rejected)\b", 1), (r"\breview(?:er|ers|ed by)\b", 1)],
            ["workflow", "store", "notifier"], ["workflow_instance"], ["approve"], ["workflow_impl"], ["workflow_stuck", "self_approval"], "Items move through states and approvals."),
    Pattern("reporting", "Reporting and analytics", [(r"\bdashboards?\b", 1), (r"\breports?\b", 1), (r"\breporting\b", 2), (r"\banalytics\b", 3), (r"\bkpis?\b", 3), (r"\btrends?\b", 1), (r"\b(?:daily|weekly|monthly) (?:report|figures|totals|summary|sales)\b", 3), (r"\baggregat", 1)],
            ["reporting", "store"], ["report_run"], [], ["reporting_store"], ["report_staleness"], "Figures are aggregated over history for people to read."),
    Pattern("backup_dr", "Backup and disaster recovery", [(r"\bbackups?\b", 3), (r"\brestor(?:e|ed|ing)\b", 2), (r"\bdisaster\b", 3), (r"\brpo\b|\brto\b|recovery (?:point|time)", 3), (r"\bpoint[- ]in[- ]time\b", 3)],
            ["backup", "store"], ["backup_run"], ["backup_restore"], ["backup_strategy"], ["backup_untested"], "Data must be recoverable after loss."),
    Pattern("compliance_data", "Personal data protection", [(r"\bgdpr\b|\bhipaa\b|\bpci\b|\bappi\b", 3), (r"\bpersonal data\b|\bpii\b", 3), (r"\bconsent\b", 2), (r"\bdelete (?:their|my|all|a person's) data\b|\bright to (?:erasure|be forgotten)\b|\brequests? deletion\b|\bcopy of their data\b|\bdata portability\b", 3), (r"\banonymi[sz]", 2), (r"\bretention\b", 1), (r"\bdata subject\b", 3)],
            ["data_protection", "store", "audit"], ["deletion_request"], [], ["pii_protection"], ["pii_spread"], "Personal data is held and must be protected, exportable and deletable."),
    Pattern("feature_flags", "Feature flags and gradual rollout", [(r"feature[- ]flags?\b|feature[- ]toggles?\b", 3), (r"\bgradual(?:ly)? (?:roll|releas|expos)", 3), (r"\bcanary\b", 2), (r"\ba/b test", 2), (r"\bpercentage of users\b", 2)],
            ["flags", "config"], ["flag"], [], ["release_strategy"], ["flag_debt"], "Features reach users gradually and reversibly."),
    Pattern("i18n", "Localisation", [(r"\bi18n\b|\bl10n\b|\blocali[sz]", 3), (r"\bmulti(?:ple)?[- ]?languages?\b|\b(?:japanese|english|german|french|spanish|chinese|korean)\b.{0,20}\b(?:japanese|english|german|french|spanish|chinese|korean)\b", 3), (r"\blocales?\b", 2), (r"\btranslat", 2), (r"\btime ?zones?\b", 1), (r"\bcurrenc(?:y|ies)\b", 1)],
            ["i18n"], [], [], ["i18n_approach"], ["missing_translation"], "Users work in several languages and locales."),
    Pattern("mobile_offline", "Mobile app with offline use", [(r"\bmobile app\b|\bios\b|\bandroid\b|\bsmartphones?\b|\bfield\b|\btablets?\b", 1), (r"\bworks offline\b|\boffline[- ]first\b|\boffline for\b|\bwithout (?:mobile )?(?:coverage|a connection|connectivity)\b", 2), (r"\boffline\b", 1), (r"\bsync(?:s|ed|ing|hroni[sz]e)?\b(?! (?:job|picks|to the warehouse))", 1), (r"\bwhen back online\b|\bsyncs? when\b|\breconnect", 2), (r"\bwhen (?:back )?online\b|\bwithout (?:a )?(?:network|connection|signal)\b", 3)],
            ["mobile", "sync", "surface_api", "core", "store"], [], ["sync_round"], ["sync_conflicts"], ["sync_conflict_loss"], "People use the app on phones, sometimes without a connection."),
    Pattern("legacy_integration", "Integration with an existing system", [(r"\blegacy\b", 3), (r"\bexisting (?:[\w-]+ ){0,3}(?:system|systems|service|services|erp|crm|database|application|platform|monolith)\b", 3), (r"\bchange request\b|\bis reused\b|\bare changed, not replaced\b", 2), (r"\berp\b|\bcrm\b|\bmainframe\b", 2), (r"\bmigrat(?:e|ed|ion) (?:from|data)\b", 2), (r"\bsystem of record\b", 2), (r"\bintegrat(?:e|es|ed|ion) with\b", 1)],
            ["legacy_adapter", "legacy_system", "core"], [], ["legacy_sync"], ["legacy_integration"], ["legacy_coupling"], "Records flow to and from a system that already exists."),
    Pattern("messaging", "Messaging between users", [(r"\bchat\b", 3), (r"\b(?:direct |private )?messages? (?:to|between|each other)\b", 3), (r"\bconversations?\b", 2), (r"\binbox\b", 2), (r"\bunread\b", 2), (r"\bread receipts?\b", 3)],
            ["messaging", "push", "store"], ["message"], [], ["message_delivery"], [], "People send messages to each other inside the system."),
]

# ---------------------------------------------------------------------------
# Quality tactics
# ---------------------------------------------------------------------------

TACTICS: list[Tactic] = [
    Tactic("consistency", [(r"double[- ]applied", 3), (r"double[- ]book", 3), (r"\btwice\b", 2), (r"\bdouble[- ]click", 2), (r"\bduplicate", 2), (r"\bidempot", 2), (r"\bconcurrent", 2), (r"\bconsistent\b|\bconsistency\b", 2), (r"\bidempoten", 2), (r"exactly once", 2), (r"\brace\b", 2), (r"\blost updates?\b", 3)],
           decisions=["concurrency"], acceptance="concurrent-update test: N parallel writers to one record end in the consistent state with no lost update"),
    Tactic("durability", [(r"no .{0,20}lost", 3), (r"\bnever (?:be )?lost\b|\bnot (?:be )?lost\b", 3), (r"\bsave\b.{0,40}\b(?:later|reuse)\b", 2), (r"\bremember", 2), (r"\bsurviv", 2), (r"\bcrash", 2), (r"\bpersist", 2), (r"\bdurab", 2), (r"at least once", 2), (r"\backnowledg|\back\b", 1), (r"\bexactly once", 2)],
           risks=["duplicate_delivery"], acceptance="crash/kill test: no accepted item is lost and none is delivered without a durable record"),
    Tactic("performance", [(r"\blatency", 2), (r"\bp9[059]\b|\bp50\b", 2), (r"\bthroughput", 2), (r"/s\b|per second", 2), (r"\bsustained", 1), (r"\bunder \d", 1), (r"\bwithin \d", 1), (r"\bfast\b|\bquick", 1), (r"\bmemory\b", 1), (r"\bnever loads\b|\bstream(?:s|ing)?\b", 1), (r"\bin under\b", 1)],
           archetypes=["observability"], acceptance="load test at the stated rate; the stated percentile must meet the target"),
    Tactic("isolation", [(r"\bisolat", 3), (r"must not (?:delay|block|affect)", 3), (r"\bslow (?:endpoint|target|tenant|customer)", 2), (r"noisy neighbou?r", 3), (r"per[- ](?:endpoint|tenant|customer)", 1)],
           decisions=["isolation"], acceptance="one target stalled (timeouts) while others must keep meeting their latency target"),
    Tactic("availability", [(r"\bavailability\b", 2), (r"highly available", 3), (r"\buptime", 2), (r"\b99\.\d+\s*%", 3), (r"\bfailover", 2), (r"\bredundan", 2), (r"\bzero downtime", 2)],
           archetypes=["observability"], decisions=["redundancy"], acceptance="kill one instance under load; error rate stays within the target"),
    Tactic("security", [(r"\bsign(?:ed|ing|ature)", 1), (r"\bsecret", 1), (r"\bauth", 1), (r"\bencrypt", 2), (r"\bssrf", 3), (r"\bpermission", 1), (r"\bcompliance|\bgdpr|\bpii\b", 2), (r"\bsecure\b|\bsecurity\b", 2)],
           risks=["auth_bypass"], acceptance="security test: unauthenticated and cross-tenant requests are rejected; outbound calls to private ranges are blocked",
           convention="Every management route goes through the authentication middleware; no route is exempt without a decision."),
    Tactic("operability", [(r"\bmetrics?\b", 2), (r"\blogs?\b|\blogging", 1), (r"\bprometheus", 2), (r"\bops\b|\boperations?\b|\boperational\b|\boperability\b", 1), (r"\balert", 2), (r"\bhealth", 1), (r"\bdashboard", 1)],
           archetypes=["observability"], acceptance="the listed metrics are exposed and change under a smoke workload",
           convention="Every component logs one structured line per unit of work with the correlation id."),
    Tactic("scalability", [(r"\bscal", 2), (r"\bhorizontal", 2), (r"\bstateless", 2), (r"\bcontainers?\b", 1), (r"\d[\d,]*\s*(?:endpoints|users|tenants|customers|clients)", 1), (r"\bsustained", 1)],
           decisions=["topology"], convention="No in-process state that a second instance would not see; instances are interchangeable."),
    Tactic("simplicity", [(r"team of \d", 3), (r"\bsmall team", 3), (r"\bsimple\b|\bminimal\b", 1), (r"\bsingle region", 1), (r"\bone person\b|\bsolo\b", 3)],
           convention="Prefer the boring option; a new piece of infrastructure needs a decision record."),
    Tactic("cost", [(r"\bcost", 2), (r"\bbudget", 2), (r"\bcheap", 2), (r"\bfree tier", 2)],
           convention="No new managed service without a line in the cost model (`sekkei deliver` writes it); prefer the option that reuses what already runs."),
    Tactic("compliance", [(r"\bgdpr\b|\bhipaa\b|\bpci\b|\bsoc ?2\b|\bappi\b|\bdata residency\b", 3), (r"\bretention", 2), (r"\bpii\b|\bpersonal data", 2), (r"\baudit", 1), (r"\bdelete (?:their|my|all) data", 2)],
           archetypes=["audit"], acceptance="data deletion and retention rules are exercised end to end"),
    Tactic("usability", [(r"\bdeveloper experience", 2), (r"\bdocumentation", 1), (r"\bsdk\b", 2), (r"\beasy to", 1), (r"\bself[- ]service", 2)]),
]

# ---------------------------------------------------------------------------
# Constraint tokens and layouts
# ---------------------------------------------------------------------------

CONSTRAINT_TOKENS: list[tuple[str, str]] = [
    (r"\bpostgres(?:ql)?\b", "postgres"), (r"\bmysql\b|\bmariadb\b", "mysql"), (r"\bsqlite\b", "sqlite"),
    (r"\bredis\b", "redis"), (r"\bkafka\b|\brabbitmq\b|\bsqs\b|\bpub/?sub\b|\bnats\b", "broker"),
    (r"\bs3\b|\bblob storage\b|\bgcs\b|\bobject storage\b", "object_storage"),
    (r"\btimescale(?:db)?\b", "timeseries_db"), (r"\bpgvector\b", "vector_db"), (r"\bclickhouse\b", "clickhouse"),
    (r"\belasticsearch\b|\bopensearch\b", "search_engine"), (r"\bvault\b|\bkms\b|secrets manager", "vault"),
    (r"\boidc\b|\boauth\b|identity provider|\bidp\b|\bsso\b|\bentitlement service\b|\bokta\b|\bazure ad\b|\bentra\b|\bkeycloak\b|\bauth0\b|\bcognito\b|\bgoogle (?:sso|workspace login)\b|\bactive directory\b|\bldap\b", "idp"),
    (r"\bcontainers?\b|\bdocker\b|\bkubernetes\b|\bk8s\b|\becs\b|\baks\b|\beks\b|\bgke\b|\bheroku\b|\bcloud run\b", "containers"),
    (r"\bstateless\b|\bmultiple instances\b|\bbehind (?:a |our )?(?:load balancer|ingress)", "multi_instance"),
    (r"\blambda\b|\bserverless\b|\bcloud functions\b", "serverless"), (r"\bsingle region\b", "single_region"),
    (r"command[- ]line tool\b|\bcli tool\b|\bthe tool runs\b|\bcommand[- ]line (?:program|utility|interface)\b|\b(?:a|the) cli\b(?! (?:and|plus|or) )", "cli_tool"), (r"\bon[- ]prem", "on_prem"), (r"\bnightly\b|\bevery night\b|\bnightly batch\b|\bonce a day\b", "nightly_batch"),
    (r"\bdynamodb\b|\bmongodb\b|\bmongo\b|\bfirestore\b|\bcosmos ?db\b", "document_db"), (r"\btwo regions\b|\bmulti[- ]region\b|\bacross regions\b|\bmultiple regions\b", "multi_region"),
    (r"\bsnowflake\b|\bbigquery\b|\bredshift\b|\bdata warehouse\b|\bwarehouse tables?\b", "warehouse"), (r"\bairflow\b|\bdagster\b|\bprefect\b", "orchestrator"),
    (r"\bper[- ]device certificates?\b|\bclient certificates?\b|\bmtls\b|\bmutual tls\b|\bx\.?509\b", "client_certs"),
    (r"\bemail (?:verification|link|otp|one[- ]time code|magic link)\b|\bmagic link\b|\bpasswordless\b|\bwithout (?:an? )?(?:sign[- ]?up|account|registration)\b|\bno sign[- ]?up\b", "email_auth"),
    (r"\bdata residency\b|\bresidency\b|\bmust (?:stay|remain|be stored|be kept) in (?:the )?[a-z]+(?: region)?\b|\bmust not leave (?:the )?[a-z]+(?: region| project)?\b|\bdata (?:stays|remains) in\b|\bdomestic region\b|\brestricted to (?:the )?\w+ region\b|\bデータ所在\b", "data_residency"),
    (r"\bheroku\b|\brender\.com\b|\bfly\.io\b|\bcloud run\b|\bapp service\b|\bpaas\b", "paas"), (r"\bslack\b|\bteams\b|\bdiscord\b", "chat_channel"),
    (r"\bexactly[- ]once at the row level\b|\bidempotent(?:ly)?\b|\bre-?run\b", "idempotent_loads"), (r"\bno database\b|\bwithout a database\b", "no_database"), (r"\bno network\b|\bair[- ]gapped\b|\bworks offline\b|\boffline[- ]first\b|\boffline (?:use|mode|for up to)\b|\bwithout (?:a )?(?:network|connection|coverage)\b", "no_network"), (r"\bwindows\b", "windows"), (r"\blinux\b", "linux"), (r"\bmacos\b", "macos"),
]

LANGUAGE_TOKENS: list[tuple[str, str]] = [
    (r"\bpython\b", "python"), (r"\btypescript\b|\bnode(?:\.js)?\b", "typescript"), (r"\bgolang\b|\bgo 1\.\d+\b|\bin go\b|\bwritten in go\b|\bgo (?:service|binary|module)s?\b", "go"),
    (r"\brust\b", "rust"), (r"\bjava\b(?!script)", "java"), (r"\bkotlin\b", "kotlin"), (r"\bc#\b|\bdotnet\b|\.net\b", "csharp"),
    (r"\bruby\b", "ruby"), (r"\belixir\b", "elixir"),
]

LAYOUTS: dict[str, Layout] = {
    "python": Layout("python", "app/{key}.py", "tests/test_{key}.py", "python -m pytest -q {test}", "ruff check .",
                     ["Type hints on every public function; dataclasses or pydantic for records.", "No business logic in the HTTP layer."], "python -m pytest -q"),
    "typescript": Layout("typescript", "src/{key}.ts", "tests/{key}.test.ts", "npx vitest run {test}", "npx eslint .",
                         ["strict TypeScript; no `any` in exported signatures.", "No business logic in route handlers."], "npx vitest run"),
    "go": Layout("go", "internal/{key}/{key}.go", "internal/{key}/{key}_test.go", "go test ./internal/{key}/", "go vet ./...",
                 ["Errors are values; wrap with context.", "Interfaces are declared by the consumer."], "go test ./..."),
    "rust": Layout("rust", "src/{key}.rs", "tests/{key}.rs", "cargo test --test {key}", "cargo clippy -- -D warnings",
                   ["No unwrap outside tests.", "Public items documented."], "cargo test"),
    "java": Layout("java", "src/main/java/app/{Key}.java", "src/test/java/app/{Key}Test.java", "./gradlew test --tests app.{Key}Test", "./gradlew check",
                   ["Constructor injection; no static state."], "./gradlew test"),
    "kotlin": Layout("kotlin", "src/main/kotlin/app/{Key}.kt", "src/test/kotlin/app/{Key}Test.kt", "./gradlew test --tests app.{Key}Test", "./gradlew check", [], "./gradlew test"),
    "csharp": Layout("csharp", "src/App/{Key}.cs", "tests/App.Tests/{Key}Tests.cs", "dotnet test --filter {Key}Tests", "dotnet format --verify-no-changes", [], "dotnet test"),
    "ruby": Layout("ruby", "lib/app/{key}.rb", "spec/{key}_spec.rb", "bundle exec rspec {test}", "bundle exec rubocop", [], "bundle exec rspec"),
    "elixir": Layout("elixir", "lib/app/{key}.ex", "test/{key}_test.exs", "mix test {test}", "mix credo", [], "mix test"),
}
DEFAULT_LANGUAGE = "python"
