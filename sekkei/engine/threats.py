"""STRIDE-lite threat model: threats per archetype, turned into risks with mitigations."""
from __future__ import annotations

from dataclasses import dataclass

from ..model import Design, Risk


@dataclass
class Threat:
    category: str      # spoofing | tampering | repudiation | information_disclosure | denial_of_service | elevation | ssrf
    description: str
    mitigation: str
    check: str         # how to prove the mitigation


THREATS: dict[str, list[Threat]] = {
    "surface_api": [
        Threat("spoofing", "Requests without a verified caller identity reach domain operations.", "Authenticate every route in one middleware; deny by default.", "every route returns 401 without credentials"),
        Threat("tampering", "Malformed or oversized bodies reach the core.", "Schema-validate and size-limit at the surface; reject before parsing fully.", "fuzz the body; oversize returns 413"),
        Threat("denial_of_service", "A single caller saturates the service.", "Per-caller rate limit and request timeouts.", "burst from one key returns 429; others unaffected"),
        Threat("information_disclosure", "Stack traces or internal ids leak in error responses.", "Map exceptions to fixed error shapes; log details server-side only.", "no traceback text in any 4xx/5xx body"),
    ],
    "ingest_api": [
        Threat("spoofing", "Any network peer can publish events.", "Authenticate producers (service credentials); allowlist event types.", "unauthenticated publish returns 401"),
        Threat("tampering", "Duplicate or replayed publishes create duplicate work.", "Idempotency key per event; reject or de-duplicate replays.", "replaying the same key does not enqueue twice"),
        Threat("denial_of_service", "A producer floods the ingest path.", "Per-producer rate limit; back-pressure with 429 and Retry-After.", "flood from one producer is throttled"),
    ],
    "dispatcher": [
        Threat("ssrf", "A customer-supplied URL points at internal or metadata addresses.", "Resolve and block private/link-local ranges; pin the resolved IP; forbid redirects to non-public hosts.", "URL to 169.254.169.254 / 10.0.0.1 / localhost is refused before connecting"),
        Threat("denial_of_service", "A slow or infinite response body ties up a worker.", "Per-request timeout; cap response size; stream and discard bodies.", "target that stalls is cut at the timeout; 100 MB body is cut at the cap"),
        Threat("information_disclosure", "Secrets or internal headers leak to targets.", "Send only the documented headers; never forward inbound headers.", "captured request has exactly the documented headers"),
    ],
    "secrets": [
        Threat("information_disclosure", "Secrets readable from a database dump or a read-only breach.", "Encrypt at rest with a key held outside the database; never log values.", "database dump contains no plaintext secret; grep logs for secret prefixes finds nothing"),
        Threat("elevation", "A rotated secret stays valid forever.", "Bound the grace window; expire old secrets by time.", "old secret rejected after the window"),
    ],
    "signer": [
        Threat("tampering", "Signatures without a timestamp can be replayed.", "Sign timestamp + body; document a tolerance window for verifiers.", "replay outside the window fails verification"),
    ],
    "queue": [
        Threat("denial_of_service", "A poison item is retried forever and blocks its partition.", "Attempt cap and dead-letter; per-partition concurrency cap.", "an always-failing item ends in the dead-letter after the cap"),
        Threat("tampering", "Items are processed twice after a crash between call and ack.", "Idempotent processing with the item id; ack only after the outcome is recorded.", "kill the worker mid-call; the item is redelivered exactly once more"),
    ],
    "store": [
        Threat("tampering", "Injection through query construction.", "Parameterised queries only; no string-built SQL.", "static check for string-formatted SQL finds nothing"),
        Threat("information_disclosure", "Backups and dumps contain everything.", "Encrypt backups; restrict who can take them.", "backup file is not readable without the key"),
    ],
    "auth": [
        Threat("spoofing", "Credential stuffing or leaked keys.", "Hash keys at rest; allow revocation; rate-limit failures.", "revoked key is rejected within seconds; brute force is throttled"),
        Threat("elevation", "A caller acts on another tenant's resources.", "Every core operation takes the principal and checks ownership.", "cross-tenant request returns 404/403 for every operation"),
    ],
    "files": [
        Threat("tampering", "Uploaded content is not what its type claims.", "Sniff content type; reject executables; size limits.", "renamed executable is rejected"),
        Threat("elevation", "Path traversal through user-supplied names.", "Generate storage keys; never use client names as paths.", "name '../x' cannot escape the store"),
    ],
    "notifier": [
        Threat("denial_of_service", "Notification storms and template injection.", "Rate-limit per recipient; escape template context.", "1,000 failures produce one digest per owner"),
    ],
    "cli": [
        Threat("tampering", "Untrusted input files or arguments reach a shell.", "Never build shell commands from input; parse files with a strict parser and a size limit.", "a file with a shell metacharacter in its name is handled without executing anything"),
    ],
    "admin_api": [
        Threat("spoofing", "Management operations reachable without authentication.", "Authenticate in one middleware for every management route; deny by default.", "every management route returns 401 unauthenticated"),
        Threat("repudiation", "No record of who changed what.", "Audit log entries for every management write with the principal.", "each write produces an audit entry"),
        Threat("elevation", "A customer manages another customer's resources.", "Ownership check on every resource operation.", "cross-customer access returns 404"),
    ],
    "push": [
        Threat("denial_of_service", "Unbounded connections.", "Cap connections per principal; idle timeouts.", "connection cap enforced"),
    ],
    "payments": [
        Threat("tampering", "Double charge on retry.", "Idempotency keys on every charge; reconcile provider webhooks.", "retrying a charge with the same key charges once"),
    ],
    "model": [
        Threat("denial_of_service", "Adversarial or oversized inputs exhaust inference capacity.", "Input size limits; batching with timeouts.", "oversize input rejected before inference"),
    ],
    "tenancy": [
        Threat("information_disclosure", "A store access without the tenant predicate returns another tenant's rows.", "All reads and writes go through the tenant context; no raw store access from surfaces.", "each operation issued as tenant A with tenant B's ids returns 404"),
        Threat("elevation", "The tenant id is taken from the request instead of the principal.", "Resolve the tenant from the authenticated principal only; reject tenant ids in bodies or headers.", "a request naming another tenant is ignored or refused"),
    ],
    "workflow": [
        Threat("elevation", "A requester approves their own item or skips a step.", "Transition rules name the roles allowed per action and exclude the requester; no direct state writes.", "self-approval and out-of-order transitions return NotPermitted/InvalidTransition"),
        Threat("repudiation", "Approvals cannot be attributed later.", "Every transition records the principal, time and comment in an append-only history.", "history has one row per transition with the actor"),
    ],
    "backup": [
        Threat("information_disclosure", "Backups are readable by whoever reaches the bucket.", "Encrypt backups; separate credentials for the backup location; restrict restore.", "backup object is unreadable without the key"),
        Threat("tampering", "A restore replaces live data with a stale or altered copy.", "Restores go to a scratch target first and require an operator confirmation; checksums verified.", "restore without confirmation is refused"),
    ],
    "sync": [
        Threat("tampering", "A device pushes changes to records it does not own.", "Apply pushed changes through the core with the device's principal; ownership checked per record.", "push for a foreign record returns 403 and is not applied"),
        Threat("denial_of_service", "A device pushes an unbounded change set.", "Cap changes per push; paginate pulls.", "oversize push returns 413"),
    ],
    "legacy_adapter": [
        Threat("spoofing", "The adapter trusts anything that looks like the legacy system.", "Authenticate the legacy endpoint (mTLS or credentials); pin its address.", "connection to an impostor host fails"),
        Threat("tampering", "Malformed legacy records corrupt the domain.", "Validate and translate every record; quarantine rejects with a report.", "a malformed record is quarantined, not applied"),
    ],
    "messaging": [
        Threat("information_disclosure", "A user reads a conversation they are not part of.", "Membership check on every read and send.", "non-member read returns 404"),
        Threat("denial_of_service", "A user floods a conversation.", "Per-sender rate limit and body size limit.", "burst from one sender returns 429"),
    ],
    "data_protection": [
        Threat("repudiation", "A deletion cannot be proven later.", "Record what was deleted where, with timestamps, in the audit log.", "each completed request has a proof entry"),
        Threat("information_disclosure", "An export goes to the wrong person.", "Exports are delivered only to the verified subject or an authorised operator; time-limited links.", "export link expires and is bound to the requester"),
    ],
    "reporting": [
        Threat("information_disclosure", "Aggregates over small groups re-identify people.", "Suppress rows below a minimum group size in person-level reports.", "a report over a group of one shows no row"),
    ],
}


def threat_table(design: Design) -> list[tuple[str, str, Threat]]:
    """(component id, component name, threat) for every component whose archetype has threats."""
    out: list[tuple[str, str, Threat]] = []
    for c in design.components:
        key = next((t.split(":", 1)[1] for t in c.tags if t.startswith("archetype:")), "")
        for th in THREATS.get(key, []):
            out.append((c.id, c.name, th))
    return out


def inject_risks(design: Design) -> int:
    """Add one risk per component threat not already covered; returns how many were added."""
    existing = {k.description for k in design.risks}
    n = len(design.risks)
    added = 0
    for cid, cname, th in threat_table(design):
        desc = f"[{th.category}] {cname}: {th.description}"
        if desc in existing:
            continue
        n += 1
        added += 1
        design.risks.append(Risk(f"K-{n}", desc, "medium", "high" if th.category in ("ssrf", "elevation", "information_disclosure") else "medium",
                                 f"{th.mitigation} Check: {th.check}", [cid]))
        existing.add(desc)
    return added


def threats_markdown(design: Design) -> str:
    rows = threat_table(design)
    if not rows:
        return "No threat rules apply to these components.\n"
    s = ["| component | category | threat | mitigation | proof |", "|---|---|---|---|---|"]
    for cid, cname, th in rows:
        s.append(f"| {cid} {cname} | {th.category} | {th.description} | {th.mitigation} | {th.check} |")
    return "\n".join(s) + "\n"
