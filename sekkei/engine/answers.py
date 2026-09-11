"""Answers to the engine's own questions: evidence from the text first, defensible defaults second.

Every answer is (1) appended to the requirements as bullets in engine-marked sections so
it flows through the normal analysis, and (2) recorded as a proposed decision with the
options considered, the evidence and what to change if the real answer differs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .analysis import Analysis
from .gaps import Question

ASSUMED_HEADING = "Assumed by the engine"


@dataclass
class Answer:
    question_id: str
    topic: str
    answer: str                         # human sentence
    bullets: list[tuple[str, str]]      # (section: functional|nonfunctional|constraint, bullet text)
    options: list[str]
    rationale: str
    evidence: str                       # "" when a default
    if_wrong: str
    affects: list[str] = field(default_factory=list)   # archetype keys
    patterns: list[str] = field(default_factory=list)  # capability patterns this answer legitimately activates


def _has(an: Analysis, rx: str) -> bool:
    return re.search(rx, " ".join(s.text for s in an.sentences), re.I) is not None


def _max_count(an: Analysis) -> float:
    vals = [q.value for u in an.requirements for q in u.sentence.quantities if q.kind == "count"]
    return max(vals, default=0.0)


def answer(q: Question, an: Analysis) -> Answer | None:
    cli = "cli_tool" in an.patterns or "no_network" in an.constraints
    internal_users = _has(an, r"\bstaff\b|\bemployees?\b|\bmanagers?\b|\binternal\b|\bcompany\b")
    external_users = _has(an, r"\bcustomers?\b|\bvisitors?\b|\bsubscribers?\b|\bclients?\b|\bpublic\b")
    big = _max_count(an) >= 10000
    durable = "durability" in an.qualities or "consistency" in an.qualities
    A = Answer
    if q.id == "Q-lang":
        if _has(an, r"\bnpm\b|\bnode\b|\.ts\b"):
            return A(q.id, q.topic, "TypeScript on Node 20.", [("constraint", "TypeScript on Node 20 (assumed by the engine: Node/npm mentioned).")],
                     ["TypeScript on Node 20", "Python 3.12", "Go 1.22"], "Node/npm is mentioned in the text.", "npm/node mention", "Change the language line; layouts and test commands follow.", [])
        return A(q.id, q.topic, "Python 3.12.", [("constraint", "Python 3.12 (assumed by the engine).")],
                 ["Python 3.12", "TypeScript on Node 20", "Go 1.22"], "No language stated; Python has the shortest path for a small team and the engine's richest layout.", "",
                 "Change the language line; every work package's files and test commands follow.", [])
    if q.id == "Q-store":
        if cli:
            return A(q.id, q.topic, "SQLite in a local file.", [("constraint", "SQLite available (assumed by the engine: command-line tool / no network).")],
                     ["SQLite", "Files on disk", "PostgreSQL"], "A command-line or offline tool cannot assume a database server.", "cli/no network", "State the real store; the Primary store decision is rescored.", ["store"])
        return A(q.id, q.topic, "PostgreSQL.", [("constraint", "PostgreSQL available (assumed by the engine).")],
                 ["PostgreSQL", "SQLite", "MySQL"], ("Durability/consistency requirements" if durable else ("Counts of 10,000 or more" if big else "A networked service with several actors"))
                 + " favour a transactional server database; PostgreSQL is the engine's default when none is stated.", "durability/consistency signals" if durable else ("large counts" if big else ""),
                 "State the available database; the Primary store and Work queue decisions are rescored.", ["store", "queue"])
    if q.id == "Q-deploy":
        if cli:
            return A(q.id, q.topic, "Distributed as a single binary/script run on the user's machine.", [("constraint", "Deployed as a single binary (assumed by the engine).")],
                     ["single binary", "containers", "serverless"], "Command-line tools run where the user is.", "cli", "State the deployment; process topology follows.", ["cli"])
        return A(q.id, q.topic, "Stateless containers behind an existing ingress, several instances.", [("constraint", "Deployed as stateless containers behind an ingress (assumed by the engine).")],
                 ["containers behind an ingress", "single VM", "serverless functions"], "The default for a networked service; keeps instances interchangeable.", "",
                 "State the deployment; topology, statelessness conventions and store options change.", ["surface_api", "admin_api", "ingest_api", "worker"])
    if q.id == "Q-team":
        return A(q.id, q.topic, "A team of 2 for the first release.", [("constraint", "Team of 2 (assumed by the engine).")],
                 ["team of 2", "team of 1", "team of 5"], "No team stated; two people is the smallest team that can review each other's work. Simplicity is weighted accordingly.", "",
                 "State the team size; decision weights and the schedule change.", [])
    if q.id == "Q-rate":
        if cli:
            return A(q.id, q.topic, "Single-user interactive use; load is not a design driver.", [("nonfunctional", "Load is one user's interactive use; throughput is not a design driver (assumed by the engine).")],
                     ["single user", "shared server, 100 requests/s", "batch over millions of records"], "A command-line or offline tool serves one user at a time.", "cli/no network",
                     "State the data volume per run instead; the latency target and memory limits change.", ["cli"])
        from .sizing import implied_rate

        imp = implied_rate(an)
        if imp:
            rate = max(1, int(round(imp[0])))
            return A(q.id, q.topic, f"{rate:,} updates/s sustained (derived), 10x at peak.", [("nonfunctional", f"The system sustains {rate:,} updates/s with peaks of {rate * 10:,} updates/s (assumed by the engine: {imp[1]}).")],
                     [f"{rate:,} updates/s", f"{rate * 10:,} updates/s", f"{max(1, rate // 10):,} updates/s"], f"Derived from the text: {imp[1]}.", imp[1],
                     "State the measured rate; capacity estimates and the queue decision change.", ["queue", "surface_api"])
        n = _max_count(an)
        rate = max(10, int(n / 100)) if n else 100
        return A(q.id, q.topic, f"{rate:,} requests/s sustained, 10x at peak.", [("nonfunctional", f"The system sustains {rate:,} requests/s with peaks of {rate * 10:,} requests/s (assumed by the engine).")],
                 [f"{rate:,} requests/s", f"{rate // 10 or 1:,} requests/s", f"{rate * 10:,} requests/s"],
                 (f"Derived from the largest stated count ({int(n):,}) at 1 request per 100 items per second." if n else "No rate or count stated; 100 requests/s is a modest default for a first release."),
                 f"count {int(n):,}" if n else "", "State the measured or expected rate; capacity estimates and the queue decision change.", ["queue", "surface_api"])
    if q.id == "Q-volume":
        return A(q.id, q.topic, "10,000 primary records and 1,000 users in the first year.", [("nonfunctional", "The system holds 10,000 records and serves 1,000 users in the first year (assumed by the engine).")],
                 ["10,000 records / 1,000 users", "100,000 / 10,000", "1,000 / 100"], "No counts stated; the default keeps single-instance options viable and is easy to revise.", "",
                 "State the counts; isolation and capacity estimates change.", ["store"])
    if q.id == "Q-payload":
        return A(q.id, q.topic, "2 KB typical, 256 KB maximum per record.", [("nonfunctional", "Records are 2 KB on average and at most 256 KB (assumed by the engine).")],
                 ["2 KB / 256 KB", "16 KB / 1 MB", "256 bytes / 4 KB"], "Typical JSON record sizes; the maximum bounds request bodies.", "", "State the sizes; storage growth and body limits change.", ["surface_api", "ingest_api"])
    if q.id == "Q-latency":
        if cli:
            return A(q.id, q.topic, "Completes within 60 s on a laptop for the stated input size.", [("nonfunctional", "A run completes within 60 s on a laptop (assumed by the engine).")],
                     ["60 s", "10 s", "10 min"], "Interactive command-line use tolerates about a minute.", "cli", "State the target; the metric check changes.", ["cli"])
        return A(q.id, q.topic, "p95 under 300 ms for reads and under 1 s for writes.", [("nonfunctional", "Read operations complete within 300 ms p95 and writes within 1 s p95 (assumed by the engine).")],
                 ["300 ms / 1 s", "100 ms / 500 ms", "1 s / 5 s"], "Common interactive-API targets; measurable from day one.", "", "State the target; the metric acceptance checks change.", ["surface_api", "admin_api"])
    if q.id == "Q-availability":
        return A(q.id, q.topic, "99.9 % monthly; during an outage work is delayed, nothing accepted is lost.", [("nonfunctional", "Availability of 99.9 % monthly; accepted work is delayed but never lost during an outage (assumed by the engine).")],
                 ["99.9 %", "99.5 %", "99.99 %"], "Three nines is achievable with two instances and health-based restarts; anything higher needs multi-region.", "",
                 "State the target and what may be lost; topology and queue durability change.", ["queue", "observability"])
    if q.id == "Q-retention":
        return A(q.id, q.topic, "Records kept 90 days, audit history 1 year, then deleted by a nightly job.", [("functional", "Records are retained for 90 days and audit history for 1 year, after which a nightly job deletes them (assumed by the engine).")],
                 ["90 days / 1 year", "30 days / 90 days", "indefinite"], "Bounded retention limits storage growth and satisfies most data-minimisation rules.", "",
                 "State the retention; the deletion job and capacity change.", ["batch", "store"], ["batch_pipeline"])
    if q.id == "Q-backup":
        return A(q.id, q.topic, "Daily backups; RPO 24 h, RTO 4 h.", [("nonfunctional", "Backups run daily with a recovery point of 24 h and a recovery time of 4 h (assumed by the engine).")],
                 ["daily / 24 h / 4 h", "hourly / 1 h / 1 h", "none"], "The store's own daily backup is the cheapest credible baseline.", "", "State RPO/RTO; the store decision and a restore drill change.", ["store"])
    if q.id == "Q-migration":
        return A(q.id, q.topic, "Greenfield; no existing data to migrate.", [("constraint", "No existing data or system to migrate from (assumed by the engine).")],
                 ["greenfield", "one-shot import", "gradual cut-over"], "Nothing in the text names an existing system.", "", "Name the existing system; a migration package and risk are added.", [])
    if q.id == "Q-auth":
        if cli:
            return A(q.id, q.topic, "No authentication: the tool runs under the user's own account.", [("constraint", "No caller authentication; the tool runs as the invoking user (assumed by the engine).")],
                     ["none", "API key for a remote service", "OS keychain"], "Command-line tools inherit the user's identity.", "cli", "State how remote calls authenticate.", ["cli"])
        if internal_users and "idp" in an.constraints:
            return A(q.id, q.topic, "OIDC tokens from the company's identity provider.", [("constraint", "Authentication via the company's OIDC identity provider (assumed by the engine).")],
                     ["OIDC", "API keys", "mTLS"], "Internal users and an identity provider are mentioned.", "staff + identity provider", "State the scheme; the authentication decision is rescored.", ["auth"], ["auth"])
        if internal_users and not external_users:
            return A(q.id, q.topic, "Single sign-on with the company's identity provider (OIDC).", [("constraint", "Authentication via an OIDC identity provider (assumed by the engine: internal users).")],
                     ["OIDC", "API keys", "mTLS"], "Internal staff systems normally sit behind the company's SSO.", "staff/employees mentioned", "State the scheme; the authentication decision is rescored.", ["auth"], ["auth"])
        return A(q.id, q.topic, "API keys per customer, hashed at rest, sent as a bearer token.", [("constraint", "Authentication by API keys per customer (assumed by the engine).")],
                 ["API keys", "OIDC", "mTLS"], "External callers without a stated identity provider are simplest to serve with per-customer keys.", "customers/visitors mentioned" if external_users else "",
                 "State the scheme; the authentication decision is rescored.", ["auth"], ["auth"])
    if q.id == "Q-authz":
        return A(q.id, q.topic, "Callers see only resources they own; an admin role may see everything.", [("functional", "Every operation is scoped to the caller's own resources; an admin role may act on any resource (assumed by the engine).")],
                 ["owner-scoped + admin role", "flat (everyone sees everything)", "role matrix per resource"], "Ownership scoping is the minimum that prevents cross-tenant access.", "",
                 "State the roles; core operations and acceptance checks change.", ["core", "auth"], ["auth"])
    if q.id == "Q-external":
        return A(q.id, q.topic, "10 s timeout, 5 retries with exponential backoff, work queued while the external system is down.", [("nonfunctional", "External calls time out after 10 s; failures are retried 5 times with exponential backoff and work waits durably meanwhile (assumed by the engine).")],
                 ["10 s / 5 retries / queue", "fail fast, no retry", "30 s / unlimited retries"], "Bounded retries with a durable queue keep the system responsive during a one-hour outage.", "",
                 "State the policy; the outbound client and scheduler contracts change.", ["dispatcher", "scheduler", "queue"])
    if q.id == "Q-compliance":
        return A(q.id, q.topic, "Personal data handled under GDPR-style rules: deletion on request within 30 days; access logged.", [("functional", "Personal data is deleted on request within 30 days and access to it is logged (assumed by the engine).")],
                 ["GDPR-style deletion + audit", "no regime", "HIPAA/PCI controls"], "Email addresses or names are personal data almost everywhere; deletion on request is the common denominator.", "personal data mentioned",
                 "State the regime; audit and deletion paths change.", ["audit", "store"], ["audit_log"])
    if q.id == "Q-alerting":
        return A(q.id, q.topic, "Alert the team channel when the error rate exceeds 1 % for 5 minutes or a queue grows for 10 minutes.", [("nonfunctional", "An alert is raised when the error rate exceeds 1 % for 5 minutes or the queue depth grows for 10 minutes (assumed by the engine).")],
                 ["error rate + queue growth", "none", "per-endpoint SLO alerts"], "Two alerts catch most incidents without paging on noise.", "", "State the rules and the on-call; observability conventions change.", ["observability"])
    if q.id == "Q-budget":
        return A(q.id, q.topic, "Existing infrastructure only; no new managed services.", [("constraint", "Use existing infrastructure only; no new managed services (assumed by the engine).")],
                 ["existing only", "managed services allowed", "strict monthly cap"], "The cheapest assumption; every decision already prefers the option needing no new infrastructure.", "",
                 "State the budget; options adding infrastructure become available.", [])
    return None


def answers(qs: list[Question], an: Analysis) -> list[Answer]:
    out = []
    for q in qs:
        a = answer(q, an)
        if a is not None:
            out.append(a)
    return out


def augment(text: str, ans: list[Answer]) -> str:
    """Append the answers as bullets under engine-marked sections so analysis picks them up."""
    if not ans:
        return text
    sections = {"functional": [], "nonfunctional": [], "constraint": []}
    for a in ans:
        for sec, bullet in a.bullets:
            sections[sec].append(bullet)
    parts = [text.rstrip(), ""]
    titles = {"functional": "Functional", "nonfunctional": "Non-functional", "constraint": "Constraints"}
    for sec in ("functional", "nonfunctional", "constraint"):
        if sections[sec]:
            parts.append(f"## {titles[sec]} ({ASSUMED_HEADING})")
            parts += [f"- {b}" for b in sections[sec]]
            parts.append("")
    return "\n".join(parts)


def answers_markdown(ans: list[Answer]) -> str:
    if not ans:
        return "No questions were open; nothing was assumed.\n"
    s = ["| # | topic | question answered | engine's answer | basis | if the real answer differs |", "|---|---|---|---|---|---|"]
    for i, a in enumerate(ans, 1):
        basis = f"evidence: {a.evidence}" if a.evidence else "default"
        s.append(f"| {i} | {a.topic} | {a.question_id} | {a.answer} | {basis} — {a.rationale} | {a.if_wrong} |")
    return "\n".join(s) + "\n"
