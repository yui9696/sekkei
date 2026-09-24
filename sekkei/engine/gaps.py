"""The questions an architect asks before committing, derived from what the text does not say.

Every question carries the default assumption the engine used, so the design is usable
before the answer arrives and the answer changes exactly one thing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .analysis import Analysis


@dataclass
class Question:
    id: str
    topic: str
    question: str
    why: str
    assumption: str
    affects: str = ""   # what in the design changes with the answer


def _text(an: Analysis) -> str:
    return " ".join(s.text for s in an.sentences).lower()


#: What it looks like when the *text itself* answers one of the engine's questions. These are the
#: vocabulary of the possible answers, not of the question: a document that says "private VMs, no
#: public cloud" has answered the deployment question even though it never says the word "deploy".
#: The red team uses the same table to report an assumed answer on a topic the author wrote about.
TOPIC_SIGNALS: dict[str, str] = {
    "Q-deploy": r"\bdeploy|\brun as\b|\bhosted\b|\bbinar(?:y|ies)\b|\bpackage|\bcontainers?\b|\bdocker\b|\bkubernetes\b|\bk8s\b|\becs\b|\bfargate\b|\blambda\b|\bserverless\b|\bvms?\b|\bvirtual machines?\b|\bbare metal\b|\bon[- ]prem|\bdata ?cent(?:re|er)\b|\bpublic cloud\b|\bprivate cloud\b|\bmanaged service|\bapp service\b|\bheroku\b|\bsystemd\b|オンプレ|自社サーバ|データセンタ",
    "Q-auth": r"\bauthenticat|\bapi keys?\b|\boidc\b|\boauth\b|\blogin\b|\btokens?\b|\bsso\b|\bsingle sign[- ]on\b|\bsaml\b|\bldap\b|\bactive directory\b|\bentra\b|\bokta\b|\bkerberos\b|\bcorporate directory\b|\bmtls\b|\bclient certificates?\b|\bmagic link\b|認証|シングルサインオン",
    "Q-store": r"\bpostgres|\bmysql\b|\bsqlite\b|\bmariadb\b|\boracle\b|\bsql server\b|\bmongo|\bdynamo|\bcassandra\b|\bredis\b|\bs3\b|\bobject storage\b|\bfiles? on disk\b|\bdatabase\b|\bdata ?store\b|データベース",
    "Q-lang": r"\bpython\b|\btypescript\b|\bjavascript\b|\bnode(?:\.js| 1\d| 2\d)?\b|\bgo(?:lang| 1\.\d+)\b|\bjava\b|\bkotlin\b|\bc#\b|\b\.net\b|\brust\b|\bruby\b|\belixir\b|\bphp\b|\bscala\b",
    "Q-retention": r"\bretain|\bretention|\bkeep .{0,30}(?:days|months|years)|\bdelete .{0,20}after|\bpurge|\barchiv|保持|保存期間",
    "Q-backup": r"\bbackup|\brestore|\bdisaster|\brecover|\brpo\b|\brto\b|バックアップ",
    "Q-availability": r"\bavailabilit|\buptime\b|\b9\d(?:\.\d+)? ?%|\bsla\b|\bhigh[- ]availab|稼働率",
    "Q-rate": r"\b(?:requests?|events?|messages?|orders?|transactions?)\s*(?:/|per )\s*(?:s\b|sec|second|minute|hour|day)|\brps\b|\bqps\b|\bthroughput\b|件/",
    "Q-migration": r"\bmigrat|\bcut[- ]?over\b|\bbackfill\b|\bdual[- ]run\b|\bexisting [\w.]+ ?(?:data|system|database|instance|service|application|platform|tool|server)s?\b|\blegacy\b|移行",
    "Q-team": r"\bteam of \d|\b\d+[- ]person team\b|\bheadcount\b|\bfte\b|\bengineers?\b|\bdevelopers?\b|チーム|名体制",
}


def answered_in_text(qid: str, an: Analysis) -> list[str]:
    """The author's own sentences that speak to a question's topic (assumed bullets excluded)."""
    rx = TOPIC_SIGNALS.get(qid)
    if not rx:
        return []
    return [s.text for s in an.sentences if not s.assumed and re.search(rx, s.text, re.I)]


def questions(an: Analysis) -> list[Question]:
    low = _text(an)
    qs: list[Question] = []
    kinds = {u.kind for u in an.requirements}
    quals = an.qualities
    quantities = [q for u in an.requirements for q in u.sentence.quantities]
    has_rate = any(q.kind == "rate" for q in quantities)
    has_latency = any(q.kind == "latency" for q in quantities) or "latency" in low
    has_count = any(q.kind == "count" for q in quantities)
    has_size = any(q.kind == "size" for q in quantities)
    has_retention = bool(re.search(r"\bretain|\bretention|\bkeep .{0,30}(days|months|years)|\bdelete .{0,20}after|\bpurge|\barchiv", low))
    has_auth = bool(re.search(TOPIC_SIGNALS["Q-auth"], low, re.I))
    has_authz = bool(re.search(r"\brole|\bpermission|\bauthoriz|\btenant|\bper[- ]customer\b|\bowner", low))
    has_deploy = bool(an.constraints & {"containers", "serverless", "on_prem", "multi_instance"}) or re.search(TOPIC_SIGNALS["Q-deploy"], low, re.I)
    has_backup = bool(re.search(TOPIC_SIGNALS["Q-backup"], low, re.I))
    has_avail = "availability" in quals or re.search(r"\b99\.\d", low)
    external = bool(re.search(r"\bexternal\b|\bthird[- ]party\b|\bprovider\b|\bcustomer(?:'s|s'|-supplied) (?:url|endpoint)|\bwebhook|\bsubscriber", low))
    external_policy = bool(re.search(r"\btimeout|\bretr|\bcircuit|\bfallback|\bdegrade", low))
    pii = bool(re.search(r"\bemail\b|\bname\b|\baddress\b|\bphone\b|\bpii\b|\bpersonal\b|\buser data\b|\bcustomer data\b", low))
    compliance = "compliance" in quals or re.search(r"\bgdpr\b|\bhipaa\b|\bpci\b|\bsoc ?2\b|\bconsent\b", low)
    has_budget = bool(re.search(r"\bbudget|\bcost\b|\bper month\b|\$\d", low))
    has_alerting = bool(re.search(r"\balert|\bon[- ]call|\bpager", low))
    has_migration = bool(re.search(TOPIC_SIGNALS["Q-migration"], low, re.I)
                         or re.search(r"\breplace(?:s|ing)? (?:the|an?) (?:existing|current)", low))

    def q(id_: str, topic: str, question: str, why: str, assumption: str, affects: str = "") -> None:
        qs.append(Question(id_, topic, question, why, assumption, affects))

    if not an.languages:
        q("Q-lang", "stack", "Which language and runtime version will this be built in?",
          "It fixes the file layout, test commands and every brief's conventions.", "Python 3.11+ (engine default).", "conventions, work-package files")
    if not an.constraints & {"postgres", "mysql", "sqlite", "no_database"}:
        q("Q-store", "stack", "Is a database available (PostgreSQL/MySQL), or must the system manage its own storage (SQLite/files)?",
          "The primary-store decision and the queue decision are scored on this.", "No database stated; options needing one were scored as unavailable.", "D: Primary store, Work queue technology")
    if not has_deploy:
        q("Q-deploy", "stack", "How is it deployed: containers behind an ingress, a single binary/CLI, serverless, on-prem?",
          "Stateless-ness, process topology and configuration loading follow from it.", "Single deployable, may run as several instances (stateless conventions applied).", "D: Process topology; conventions")
    if an.team_size is None:
        q("Q-team", "people", "How many people will build and run it, and for how long?",
          "It weights simplicity in every decision and turns work packages into a calendar.", "Small team (simplicity weighted 0.8 when a team size <= 4 is stated; otherwise unweighted).", "decisions, schedule estimate")
    if not has_rate:
        q("Q-rate", "load", "What is the sustained and peak request/event rate (per second), and the growth over 12 months?",
          "Without a rate the queue, store and worker decisions cannot be sized and the capacity estimate is empty.", "No rate; performance tactics applied without numbers.", "capacity estimates, D: Work queue technology")
    if not has_count:
        q("Q-volume", "load", "How many of the main things exist (users, tenants, endpoints, items) now and in a year?",
          "Partitioning and isolation strategies depend on the count.", "Counts unknown; per-item isolation assumed cheap.", "D: isolation, capacity")
    if not has_size:
        q("Q-payload", "load", "How large is a typical and a maximum payload/record (KB)?",
          "Storage growth and body-size limits are computed from it.", "2 KB per record (engine assumption in the capacity estimate).", "capacity, input limits")
    if kinds and not has_latency:
        q("Q-latency", "quality", "What latency is acceptable for the main operations (a percentile and a number, e.g. p95 under 300 ms)?",
          "It becomes a measurable metric and a load-test acceptance check.", "No latency target; no performance acceptance check emitted.", "R: non-functional, acceptance checks")
    if not has_avail:
        q("Q-availability", "quality", "What availability is required (e.g. 99.9 % monthly), and what may be lost or delayed during an outage?",
          "Redundancy, health-based restart and queue durability follow from it.", "Best effort; single-instance failure delays work but loses nothing that was persisted.", "D: Process topology; risks")
    if not has_retention and ("store" in low or "record" in low or "history" in low or has_count):
        q("Q-retention", "data", "How long must records, logs and history be kept, and when/how are they deleted?",
          "Retention drives storage growth, archival jobs and compliance.", "Kept indefinitely; no archival job designed.", "capacity, batch jobs, compliance")
    if not has_backup:
        q("Q-backup", "data", "What is the backup/restore expectation (RPO/RTO)?",
          "It decides whether a managed store or an explicit backup job is needed.", "Store's own backups; no application-level backup.", "D: Primary store; risks")
    if has_migration is False and re.search(r"\bexisting\b|\bcurrent\b|\btoday\b", low):
        q("Q-migration", "data", "Is there existing data or a system being replaced, and must the cut-over be gradual?",
          "A migration path adds a package and a risk.", "Greenfield; no migration package.", "work packages, risks")
    human_facing = any(k in an.patterns for k in ("crud_api", "admin_api", "event_ingest", "file_storage", "realtime")) \
        or any(u.sentence.actors for u in an.requirements if u.kind == "functional")
    if not has_auth and human_facing:
        q("Q-auth", "security", "How are callers authenticated (API keys, OIDC/OAuth, mTLS), and who issues credentials?",
          "Every management route is gated on it; the auth decision is scored on it.", "API keys per caller, hashed at rest.", "D: Caller authentication; C: Authentication")
    if has_auth and not has_authz and not re.search(r"\bno (?:caller )?authentication\b", low):
        q("Q-authz", "security", "Who may do what: roles, tenants, ownership rules?",
          "Authorization checks live in the core and in every brief's acceptance.", "Callers see only resources they own; no roles.", "core operations, acceptance")
    if external and not external_policy:
        q("Q-external", "resilience", "For calls to external systems: timeouts, retry policy, and what happens when they are down for an hour?",
          "The outbound client and the queue are designed to these numbers.", "Timeout 10 s, retries per the delivery pattern, work queued during outages.", "C: Outbound HTTP client, D: retries")
    if pii and not compliance:
        q("Q-compliance", "compliance", "Is personal data involved, and which regime applies (GDPR/HIPAA/PCI)? Are deletion requests required?",
          "Adds audit, retention and deletion paths.", "Personal data present but no regime stated; no deletion path designed.", "C: Audit log; batch deletion job")
    if not has_alerting and "operability" in quals:
        q("Q-alerting", "operations", "Who is alerted on what (thresholds, on-call), and where do alerts go?",
          "Metrics exist; alert rules and their owners are a human decision.", "Metrics exposed; no alert rules designed.", "observability conventions")
    if not has_budget:
        q("Q-budget", "cost", "Is there a cost ceiling (infrastructure per month) or a preference for existing infrastructure only?",
          "Options that add infrastructure are scored on cost.", "Existing infrastructure preferred (cost weight only if stated).", "decisions")
    return qs


def questions_markdown(qs: list[Question]) -> str:
    if not qs:
        return "No open questions: the text states stack, load, latency, availability, retention, auth and deployment.\n"
    s = ["| # | topic | question | why it matters | assumed meanwhile | changes |", "|---|---|---|---|---|---|"]
    for i, x in enumerate(qs, 1):
        s.append(f"| {i} | {x.topic} | {x.question} | {x.why} | {x.assumption} | {x.affects} |")
    return "\n".join(s) + "\n"
