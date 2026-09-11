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
    Archetype("email", "Email provider", "External email delivery service.", kind="external", layer=0, iface_kind="http", ops=[
        OpT("send", [("to", "str"), ("subject", "str"), ("body", "str")], "provider message id"),
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
    Archetype("batch", "Batch job", "Scheduled processing over stored records: extract, transform, aggregate, write results.",
              kind="job", layer=2, needs=["store", "scheduler"], iface_kind="module", ops=[OpT("run", [("window", "DateRange")], "JobReport", ["JobError"])]),
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
                          {"durability": 3, "simplicity": 3, "performance": 2, "isolation": 2, "scalability": 2, "cost": 3, "operability": 3}, needs=["postgres"]),
                   Option("Redis Streams with consumer groups",
                          ["high throughput", "built-in consumer groups and pending lists"],
                          ["durability depends on AOF/fsync configuration", "separate from the transactional store: needs an outbox"],
                          {"durability": 1, "simplicity": 2, "performance": 3, "isolation": 2, "scalability": 3, "cost": 2, "operability": 2}, needs=["redis"]),
                   Option("Managed broker (SQS/RabbitMQ/Kafka)",
                          ["scales independently", "delayed delivery built in (SQS)"],
                          ["new infrastructure and cost", "at-least-once semantics still need an outbox"],
                          {"durability": 3, "simplicity": 1, "performance": 3, "isolation": 2, "scalability": 3, "cost": 1, "operability": 2}, needs=["broker"]),
                   Option("In-memory queue",
                          ["simplest possible"], ["work is lost on crash", "single process only"],
                          {"durability": 0, "simplicity": 3, "performance": 3, "isolation": 1, "scalability": 0, "cost": 3, "operability": 2})],
                  ["queue", "ingest_api", "worker"], trigger=["async_delivery", "event_ingest", "batch_pipeline"]),
    DecisionPoint("store_tech", "Primary store",
                  "Domain records need durable, queryable storage.",
                  [Option("PostgreSQL", ["transactions", "indexes and JSON", "already available"], ["operational dependency"],
                          {"durability": 3, "performance": 3, "simplicity": 2, "scalability": 3, "cost": 2, "compliance": 3, "operability": 3}, needs=["postgres"], bonus_when=["postgres"], excludes=["no_database"]),
                   Option("SQLite", ["zero operations", "single file"], ["one writer at a time", "no network access"],
                          {"durability": 2, "performance": 2, "simplicity": 3, "scalability": 0, "cost": 3, "compliance": 2, "operability": 2}, excludes=["containers", "multi_instance", "no_database"]),
                   Option("Files (JSON/CSV on disk)", ["no dependencies", "human readable"], ["no transactions or concurrency"],
                          {"durability": 1, "performance": 1, "simplicity": 3, "scalability": 0, "cost": 3, "compliance": 1, "operability": 1}, excludes=["containers", "multi_instance"]),
                   Option("In-memory", ["fastest", "trivial"], ["lost on restart"],
                          {"durability": 0, "performance": 3, "simplicity": 3, "scalability": 0, "cost": 3, "compliance": 0, "operability": 2})],
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
                          {"durability": 0, "simplicity": 3, "performance": 3, "operability": 1})],
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
                          {"security": 3, "simplicity": 0, "usability": 1})],
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
    Pattern("event_ingest", "Event ingestion", [(r"\bpublish", 2), (r"\bevents?\b", 1), (r"\bproducer|internal services?\b", 1), (r"\bingest", 2), (r"\bemit", 1)],
            ["ingest_api", "core", "store", "queue"], ["event", "work_item"], ["ingest"], ["ingest_style", "queue_tech", "store_tech"], ["unbounded_input"],
            "Producers hand events to the system, which persists them before acknowledging."),
    Pattern("async_delivery", "Asynchronous delivery with retries",
            [(r"\bdeliver", 2), (r"\bwebhook", 2), (r"\bretr(?:y|ied|ies)\b", 2), (r"\bbackoff\b", 2), (r"\battempts?\b", 1), (r"at least once", 2), (r"\bqueue", 1), (r"\bworker", 1), (r"\bredeliver", 1)],
            ["queue", "worker", "scheduler", "dispatcher", "core", "store", "endpoint"], ["work_item", "attempt", "target"], ["deliver", "retry"],
            ["queue_tech", "retry_scheduling", "topology", "outbound_safety", "store_tech"], ["duplicate_delivery", "thundering_retry", "ssrf", "queue_bloat", "clock_skew"],
            "Work is queued durably and performed by workers with a retry schedule."),
    Pattern("signing", "Request signing", [(r"\bsign(?:ed|ing|ature)?\b", 2), (r"\bhmac\b", 2), (r"\bsecret", 1), (r"\brotat", 1)],
            ["signer", "secrets"], ["secret"], [], ["secret_storage"], ["secret_exposure", "clock_skew"],
            "Outbound requests carry an HMAC signature; secrets rotate with a grace window."),
    Pattern("notification", "Notifications", [(r"\bemail", 2), (r"\bnotif(?:y|ied|ication)", 2), (r"\bsms\b|\bslack\b", 2)],
            ["notifier", "email"], [], [], [], ["notification_storm"], "The system notifies people through an external channel."),
    Pattern("health_policy", "Automatic disable policy", [(r"disabled? automatically", 3), (r"fail(?:s|ing|ed)? continuously", 3), (r"\bcircuit", 2), (r"\bautomatically\b", 1)],
            ["policy", "core", "notifier"], [], ["disable"], [], ["notification_storm"], "Targets that keep failing are disabled by policy and the owner is told."),
    Pattern("observability", "Observability", [(r"\bmetrics?\b", 2), (r"\bprometheus\b", 2), (r"\bstructured logs?\b|\blogs?\b|\blogging\b", 1), (r"\bhealth", 1), (r"\balert", 1), (r"\bdashboard", 1), (r"\btrac(?:e|ing)\b", 1)],
            ["observability"], [], [], [], ["metric_cardinality"], "Metrics, structured logs and health endpoints for operations."),
    Pattern("auth", "Authentication and authorization", [(r"\bauthenticat", 2), (r"\bauthoriz", 2), (r"\blogin\b|\bsign[- ]in\b", 2), (r"\bapi keys?\b", 2), (r"\boauth\b|\bsso\b|\boidc\b", 2), (r"\bpermissions?\b|\broles?\b", 1), (r"\btoken", 1)],
            ["auth", "store"], ["principal"], [], ["auth_scheme"], ["auth_bypass"], "Callers are authenticated and authorized."),
    Pattern("rate_limiting", "Rate limiting", [(r"rate[- ]limit", 3), (r"\bthrottl", 2), (r"\bquota", 2)],
            ["ratelimit"], [], [], [], [], "Request budgets per caller."),
    Pattern("cache", "Caching", [(r"\bcach(?:e|ing)\b", 3)], ["cache"], [], [], ["cache_policy"], [], "Hot reads are cached."),
    Pattern("search", "Search", [(r"\bsearch", 2), (r"full[- ]text", 3), (r"\bfilter", 1)], ["search", "store"], [], [], [], [], "Users search and filter records."),
    Pattern("file_storage", "File storage", [(r"\bupload", 2), (r"\bfiles?\b", 1), (r"\battachment", 2), (r"\bblob", 2), (r"\bs3\b", 2), (r"\bimages?\b|\bphotos?\b|\bdocuments?\b", 1)],
            ["files", "core"], ["file"], [], [], ["unbounded_input"], "Files are uploaded, stored and served."),
    Pattern("batch_pipeline", "Batch processing", [(r"\bbatch", 2), (r"\bnightly\b|\bdaily\b|\bweekly\b|\bhourly\b", 2), (r"\betl\b", 3), (r"\bpipeline", 1), (r"\baggregat", 1), (r"\breport", 1)],
            ["batch", "scheduler", "store"], ["job_run"], ["batch_run"], ["store_tech", "topology"], ["schema_drift"], "Scheduled jobs process stored records in windows."),
    Pattern("scheduler_jobs", "Scheduled jobs", [(r"\bcron\b", 3), (r"\bschedul", 2), (r"\bevery (?:day|hour|minute|night|week)\b", 2), (r"\bperiodic", 2)],
            ["scheduler"], [], [], [], [], "Work runs on a schedule."),
    Pattern("cli_tool", "Command-line tool", [(r"command[- ]line", 3), (r"\bcli\b", 3), (r"\bterminal\b", 2), (r"\bflags?\b|\bsubcommands?\b", 2), (r"\bstdin\b|\bstdout\b|\bstderr\b|\bexit(?:s)? (?:with )?code", 2), (r"\bthe tool\b|\bthe user runs\b", 1)],
            ["cli", "core", "config"], [], ["cli_run"], ["store_tech"], [], "A command-line front end over the core."),
    Pattern("realtime", "Real-time push", [(r"\bwebsocket", 3), (r"real[- ]time", 2), (r"\bpush\b", 1), (r"\bstream", 1), (r"\bsse\b|server-sent", 3)],
            ["push", "core", "bus"], [], [], ["topology"], [], "Connected clients receive events as they happen."),
    Pattern("payments", "Payments", [(r"\bpayment", 3), (r"\binvoice", 2), (r"\bbilling\b", 2), (r"\bstripe\b|\bcharge\b", 2)],
            ["payments", "psp", "store"], [], [], [], ["duplicate_delivery"], "Charges and invoices through a payment provider."),
    Pattern("ml_inference", "Model inference", [(r"\binference\b", 3), (r"\bpredict", 2), (r"\bmodel\b", 1), (r"\bembedding", 2), (r"\bclassif", 1)],
            ["model", "core"], [], [], [], [], "Predictions are served from a versioned model."),
    Pattern("audit_log", "Audit log", [(r"\baudit", 3), (r"who did (?:it|what)", 3), (r"\bhistory\b", 1), (r"\brecorded with\b", 1), (r"\bchange log\b|\bchangelog\b", 2)],
            ["audit"], ["audit_entry"], [], [], [], "Changes are recorded append-only with the actor."),
    Pattern("import_export", "Import and export", [(r"\bexport", 2), (r"\bimport\b", 2), (r"\bcsv\b", 2)],
            ["exporter", "core"], [], [], [], ["unbounded_input"], "Records move in and out as files."),
    Pattern("outbound", "Outbound HTTP calls", [(r"\bcalls? (?:an? )?external", 2), (r"\bthird[- ]party api", 2), (r"\boutbound\b", 2), (r"\bfetch(?:es)? from\b", 1), (r"\bsubscriber urls?\b|\bendpoints?\b", 1)],
            ["dispatcher"], [], [], ["outbound_safety"], ["ssrf"], "The system calls external HTTP services."),
]

# ---------------------------------------------------------------------------
# Quality tactics
# ---------------------------------------------------------------------------

TACTICS: list[Tactic] = [
    Tactic("consistency", [(r"double[- ]applied", 3), (r"\bconcurrent", 2), (r"\bconsistent\b|\bconsistency\b", 2), (r"\bidempoten", 2), (r"exactly once", 2), (r"\brace\b", 2), (r"\blost updates?\b", 3)],
           decisions=["concurrency"], acceptance="concurrent-update test: N parallel writers to one record end in the consistent state with no lost update"),
    Tactic("durability", [(r"no .{0,20}lost", 3), (r"\bnever lost\b|\bnot (?:be )?lost\b", 3), (r"\bsave\b.{0,40}\b(?:later|reuse)\b", 2), (r"\bremember", 2), (r"\bsurviv", 2), (r"\bcrash", 2), (r"\bpersist", 2), (r"\bdurab", 2), (r"at least once", 2), (r"\backnowledg|\back\b", 1), (r"\bexactly once", 2)],
           risks=["duplicate_delivery"], acceptance="crash/kill test: no accepted item is lost and none is delivered without a durable record"),
    Tactic("performance", [(r"\blatency", 2), (r"\bp9[059]\b|\bp50\b", 2), (r"\bthroughput", 2), (r"/s\b|per second", 2), (r"\bsustained", 1), (r"\bunder \d", 1), (r"\bwithin \d", 1), (r"\bfast\b|\bquick", 1), (r"\bmemory\b", 1), (r"\bnever loads\b|\bstream(?:s|ing)?\b", 1), (r"\bin under\b", 1)],
           archetypes=["observability"], acceptance="load test at the stated rate; the stated percentile must meet the target"),
    Tactic("isolation", [(r"\bisolat", 3), (r"must not (?:delay|block|affect)", 3), (r"\bslow (?:endpoint|target|tenant|customer)", 2), (r"noisy neighbou?r", 3), (r"per[- ](?:endpoint|tenant|customer)", 1)],
           decisions=["isolation"], acceptance="one target stalled (timeouts) while others must keep meeting their latency target"),
    Tactic("availability", [(r"\bavailability\b", 2), (r"highly available", 3), (r"\buptime", 2), (r"\b99\.\d+\s*%", 3), (r"\bfailover", 2), (r"\bredundan", 2), (r"\bzero downtime", 2)],
           archetypes=["observability"], acceptance="kill one instance under load; error rate stays within the target"),
    Tactic("security", [(r"\bsign(?:ed|ing|ature)", 1), (r"\bsecret", 1), (r"\bauth", 1), (r"\bencrypt", 2), (r"\bssrf", 3), (r"\bpermission", 1), (r"\bcompliance|\bgdpr|\bpii\b", 2), (r"\bsecure\b|\bsecurity\b", 2)],
           risks=["auth_bypass"], acceptance="security test: unauthenticated and cross-tenant requests are rejected; outbound calls to private ranges are blocked",
           convention="Every management route goes through the authentication middleware; no route is exempt without a decision."),
    Tactic("operability", [(r"\bmetrics?\b", 2), (r"\blogs?\b|\blogging", 1), (r"\bprometheus", 2), (r"\bops\b|\boperat", 1), (r"\balert", 2), (r"\bhealth", 1), (r"\bdashboard", 1)],
           archetypes=["observability"], acceptance="the listed metrics are exposed and change under a smoke workload",
           convention="Every component logs one structured line per unit of work with the correlation id."),
    Tactic("scalability", [(r"\bscal", 2), (r"\bhorizontal", 2), (r"\bstateless", 2), (r"\bcontainers?\b", 1), (r"\d[\d,]*\s*(?:endpoints|users|tenants|customers|clients)", 1), (r"\bsustained", 1)],
           decisions=["topology"], convention="No in-process state that a second instance would not see; instances are interchangeable."),
    Tactic("simplicity", [(r"team of \d", 3), (r"\bsmall team", 3), (r"\bsimple\b|\bminimal\b", 1), (r"\bsingle region", 1), (r"\bone person\b|\bsolo\b", 3)],
           convention="Prefer the boring option; a new piece of infrastructure needs a decision record."),
    Tactic("cost", [(r"\bcost", 2), (r"\bbudget", 2), (r"\bcheap", 2), (r"\bfree tier", 2)]),
    Tactic("compliance", [(r"\bgdpr\b|\bhipaa\b|\bpci\b|\bsoc ?2\b", 3), (r"\bretention", 2), (r"\bpii\b|\bpersonal data", 2), (r"\baudit", 1), (r"\bdelete (?:their|my|all) data", 2)],
           archetypes=["audit"], acceptance="data deletion and retention rules are exercised end to end"),
    Tactic("usability", [(r"\bdeveloper experience", 2), (r"\bdocumentation", 1), (r"\bsdk\b", 2), (r"\beasy to", 1), (r"\bself[- ]service", 2)]),
]

# ---------------------------------------------------------------------------
# Constraint tokens and layouts
# ---------------------------------------------------------------------------

CONSTRAINT_TOKENS: list[tuple[str, str]] = [
    (r"\bpostgres(?:ql)?\b", "postgres"), (r"\bmysql\b|\bmariadb\b", "mysql"), (r"\bsqlite\b", "sqlite"),
    (r"\bredis\b", "redis"), (r"\bkafka\b|\brabbitmq\b|\bsqs\b|\bpub/?sub\b|\bnats\b", "broker"),
    (r"\bs3\b|\bblob storage\b|\bgcs\b", "object_storage"), (r"\bvault\b|\bkms\b|secrets manager", "vault"),
    (r"\boidc\b|\boauth\b|identity provider|\bidp\b|\bsso\b", "idp"),
    (r"\bcontainers?\b|\bdocker\b|\bkubernetes\b|\bk8s\b|\becs\b", "containers"),
    (r"\bstateless\b|\bmultiple instances\b|\bbehind (?:a |our )?(?:load balancer|ingress)", "multi_instance"),
    (r"\blambda\b|\bserverless\b|\bcloud functions\b", "serverless"), (r"\bsingle region\b", "single_region"),
    (r"\bon[- ]prem", "on_prem"), (r"\bno database\b|\bwithout a database\b", "no_database"), (r"\bno network\b|\boffline\b|\bair[- ]gapped\b", "no_network"), (r"\bwindows\b", "windows"), (r"\blinux\b", "linux"), (r"\bmacos\b", "macos"),
]

LANGUAGE_TOKENS: list[tuple[str, str]] = [
    (r"\bpython\b", "python"), (r"\btypescript\b|\bnode(?:\.js)?\b", "typescript"), (r"\bgo(?:lang)?\b", "go"),
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
