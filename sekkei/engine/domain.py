"""The domain model read from the sentences: entities with typed fields, relations, state machines, invariants.

Four reviewers scored the data model 0/2 on every specification because an entity was a noun
with ``(id, created_at)``. This module reads what the text actually says about its things:

* **fields** — a parenthesis after the noun (``items (SKU, quantity, warehouse, bin)``), a
  ``with A, B and C`` list after a create/submit verb, a possessive (``the order's limit
  price``), an attribute set or amended (``amend the limit price of a working order``);
  types are inferred from the field name (price → Money, expiry → timestamp, quantity → int …);
* **relations** — ``X belongs to exactly one Y``, ``per Y``, ``each Y has N X``, ``Y's X``;
* **state machines** — transactional verbs applied to the entity (submit, approve, reject,
  cancel, ship, acknowledge, quarantine …) become states; ``dev → staging → prod`` and
  ``booked → changed → cancelled`` arrow lists are read as ordered states;
* **invariants** — ``never randomised twice``, ``never modified after creation``, ``exactly
  one``, ``in the same transaction as``, ``must not be deleted`` become constraints with the
  sentence that states them.

Everything carries the requirement ids it came from, so a reader can dispute it. Nothing is
invented: an entity without stated fields keeps only ``id`` and ``created_at`` and says so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import text as T
from .analysis import Analysis, ReqUnit

# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------

#: verbs whose object is a thing the system keeps
#: verbs whose object is a thing the system keeps, with lower weight (generic CRUD)
KEEPING = {"collect", "acquire", "select", "form", "persist", "keep", "hold", "track", "monitor", "manage", "view", "list", "search",
           "export", "delete", "update", "edit", "cancel", "get", "show", "display", "validate", "process", "handle", "match", "filter", "sort"}
TRANSACTIONAL = {"create", "register", "submit", "book", "order", "reserve", "upload", "publish", "request", "record", "add", "store",
                 "save", "issue", "log", "file", "generate", "assign", "schedule", "import", "send", "accept", "offer",
                 "charge", "tag", "rate", "randomise", "randomize", "enrol", "enroll", "quarantine", "capture", "settle", "refund",
                 "consent", "withdraw", "unblind", "adjudicate", "allocate", "dispatch", "provision", "onboard", "reimburse", "disburse",
                 "ingest", "clip", "grant", "redeem", "purchase", "quote", "bill", "unlock", "flag", "escalate", "acknowledge", "amend"}
#: verbs that move a thing between states
STATE_VERBS = {"submit": "submitted", "approve": "approved", "reject": "rejected", "cancel": "cancelled", "publish": "published",
               "unpublish": "unpublished", "ship": "shipped", "book": "booked", "quarantine": "quarantined", "acknowledge": "acknowledged",
               "escalate": "escalated", "resolve": "resolved", "close": "closed", "accept": "accepted", "decline": "declined",
               "expire": "expired", "withdraw": "withdrawn", "activate": "active", "disable": "disabled", "enable": "enabled",
               "suspend": "suspended", "archive": "archived", "complete": "completed", "settle": "settled", "capture": "captured",
               "refund": "refunded", "pay": "paid", "retry": "retrying", "fail": "failed", "deliver": "delivered", "dispatch": "dispatched",
               "amend": "amended", "fill": "filled", "halt": "halted", "revoke": "revoked", "restore": "restored", "promote": "promoted",
               "unblind": "unblinded", "confirm": "confirmed", "release": "released", "reopen": "reopened", "start": "started", "stop": "stopped",
               "randomise": "randomised", "randomize": "randomized", "enrol": "enrolled", "enroll": "enrolled", "consent": "consented",
               "adjudicate": "adjudicated", "allocate": "allocated", "provision": "provisioned", "deprovision": "deprovisioned",
               "reimburse": "reimbursed", "disburse": "disbursed", "flag": "flagged", "unlock": "unlocked", "lock": "locked", "grant": "granted",
               "redeem": "redeemed", "pause": "paused", "resume": "resumed", "reinstate": "reinstated", "quote": "quoted", "bill": "billed"}
_TERMINAL = {"rejected", "declined", "cancelled", "canceled", "expired", "failed", "withdrawn", "closed", "discarded", "deleted", "revoked", "voided", "refunded"}
_STATE_WORDS = {"pending", "working", "open", "closed", "active", "inactive", "draft", "live", "expired", "scheduled", "queued",
                "processing", "done", "failed", "succeeded", "new", "approved", "rejected", "cancelled", "canceled", "submitted",
                "published", "archived", "paid", "unpaid", "settled", "shipped", "delivered", "acknowledged", "escalated", "quarantined",
                "suspended", "withdrawn", "confirmed", "booked", "changed", "resolved", "dev", "staging", "prod", "production"}
#: field-name patterns → type
_TYPES = [
    (r"(?:^|_)(?:at|date|expiry|expires|deadline|time|timestamp|due|start|end|window|since|until)$|^(?:date|time) of", "timestamp"),
    (r"price|amount|fee|notional|total|cost|share|balance|payout|premium|salary|budget|strike|limit|excess|deductible|allowance|charged|paid", "Money"),
    (r"quantity|count|number of|points|size|attempts|retries|depth|(?:^|_)age$|level|stock|kits|seats|capacity|estimate|hours$|days$", "int"),
    (r"percent|rate$|ratio|bps|discount|probability|score", "decimal"),
    (r"email", "email"), (r"url|link|uri|endpoint", "url"), (r"phone|mobile number", "phone"),
    (r"(?:^|_)(?:id|ref|reference|key|code|sku|number|no)$|_id$|identifier", "ref"),
    (r"status|state|type|kind|direction|category|role|priority|severity|tier|method|channel|mode|arm|reason code|slot|zone", "enum"),
    (r"enabled|disabled|flag|opted|active$|required$|is_|has_", "bool"),
    (r"hash|checksum|digest|signature", "bytes"), (r"file|attachment|document|pdf|image|photo|video|export", "file"),
    (r"address|location|position|coordinates|gps|geo", "address"), (r"currency", "currency"), (r"locale|language", "locale"),
    (r"name|title|label|subject|description|notes?|comment|message|text|body|content|reason|instrument|term", "str"),
]
_FIELD_STOP = {"and", "or", "etc", "e.g", "eg", "i.e", "the", "a", "an", "of", "with", "per", "each", "both", "only", "also", "such", "as",
               "at", "least", "most", "than", "more", "less", "one", "two", "three", "if", "any", "all", "some", "other", "same", "own"}
_REL_STOP = {"time", "day", "hour", "minute", "second", "week", "month", "year", "request", "response", "call", "second", "system",
             "service", "api", "process", "run", "way", "case", "basis", "default", "team", "tenant", "customer", "user",
             "person", "people", "staff", "operator", "admin", "take", "let", "object", "thing", "things", "cloud",
             "cannot", "must", "should", "may", "can", "will", "shall", "not", "never", "return", "handout", "hand-out",
             "burst", "flow", "open", "price", "prices", "value", "values", "part", "parts",
             "step", "steps", "action", "actions", "change", "changes", "control", "controls", "check", "checks", "state", "states",
             "result", "results", "kind", "kinds", "type", "types", "section", "sections", "page", "pages", "screen", "screens",
             "rule", "rules", "field", "fields", "table", "tables", "row", "rows", "column", "columns", "code", "codes",
             "sequence", "queue", "queues", "topic", "topics", "endpoint", "endpoints", "email", "emails", "sms", "webhook", "webhooks",
             "notice", "notices", "notification", "notifications", "message", "messages", "provider", "providers", "vendor",
             "image", "images", "version", "versions", "library", "libraries", "attempt", "attempts", "share", "shares", "entry", "entries",
             "batch", "batches", "duplicate", "duplicates", "copy", "copies", "list", "lists", "set", "sets", "number", "numbers", "latest", "precision",
             "percentage", "percentages", "portion", "fraction", "majority", "subset", "sample", "samples", "trail", "trails", "total", "totals",
             "night", "nights", "morning", "mornings", "evening", "afternoon", "weekend", "weekends", "today", "tomorrow", "yesterday", "quarter", "quarters",
             "date", "dates", "reason", "reasons", "identity", "identities", "period", "periods", "interval", "intervals", "accuracy", "loss"}
_UNITS = {"min", "mins", "sec", "secs", "ms", "hr", "hrs", "kb", "mb", "gb", "tb", "pct", "km", "cm", "mm", "kg", "usd", "eur", "gbp", "jpy"}
_TECH_WORDS = T.TECH_WORDS
_NOUN_VERBS = ("order", "request", "offer", "match", "charge", "claim", "booking", "record", "report", "export", "import", "alert", "schedule",
               "release", "measure", "filter", "share", "rate", "reading", "listing", "setting", "rating", "building", "meeting", "shipping",
               "training", "billing", "vote", "comment", "review", "invoice", "payment", "ticket", "document", "file", "form", "plan", "test",
               "run", "job", "task", "deal", "trip", "ride", "quote", "grade", "score", "post", "message", "call", "visit", "transfer", "deposit",
               "fill", "clip", "flag", "lock", "unlock", "issue", "return", "refund", "quarantine", "block", "bill", "estimate", "reply")
_ACTORISH = {"member", "members", "employee", "employees", "user", "users", "customer", "customers", "tenant", "tenants", "role", "roles",
             "team", "teams", "person", "people", "staff", "operator", "operators", "admin", "admins", "participant", "participants", "player", "players"}
_ALT_PAREN = re.compile(r"^\s*[a-z][a-z0-9-]*(?:\s*(?:/|,|\s+and\s+|\s+or\s+)\s*[a-z][a-z0-9-]*){1,2}\s*$", re.I)

_ARROW_LIST = re.compile(r"((?:[a-z][a-z_-]{1,20}(?:\s*/\s*[a-z][a-z_-]{1,20})*)(?:\s*(?:→|->|=>|⟶)\s*(?:[a-z][a-z_-]{1,20}(?:\s*/\s*[a-z][a-z_-]{1,20})*)){1,6})", re.I)
#: "is placed, then confirmed by the merchant, then shipped" — an ordered sequence of participles
_THEN_SEQ = re.compile(r"\b(?:is|are|gets|becomes)\s+([a-z]+(?:ed|en))\b((?:[^.;]{0,40}?,?\s*(?:then|and then|after that|next)\s+(?:[a-z]+\s+){0,2}([a-z]+(?:ed|en))\b){1,5})", re.I)
_THEN_ITEM = re.compile(r"(?:then|and then|after that|next)\s+(?:[a-z]+\s+){0,2}([a-z]+(?:ed|en))\b", re.I)
#: "may cancel it until it is shipped", "cannot be confirmed later" after "declined", "must confirm or decline … otherwise expires"
_UNTIL = re.compile(r"\b(?:can|may|must|could)\s+([a-z]+)\s+(?:it|them|the [a-z]+|an? [a-z]+)?\s*(?:until|before|as long as it is not|unless it is)\s+(?:it\s+)?(?:is|has been|was)\s+([a-z]+(?:ed|en))\b", re.I)
_OTHERWISE = re.compile(r"\b(?:must|shall|should)\s+([a-z]+)(?:\s+or\s+([a-z]+))?\s+(?:an?|the|it)?\s*[a-z]*\s*within\s+[^,;.]{1,30},?\s*(?:otherwise|or else|failing which)\s+(?:the\s+[a-z]+\s+|it\s+)?([a-z]+s?)\b", re.I)
_HAS_LIST = re.compile(r"\b(?:the|a|an|each|every)?\s*(?:[a-z][a-z-]{2,}\s+)?([a-z][a-z-]{2,})s?\s+(?:has|have|carries|carry|records?|stores?|includes?|contains?|holds?|consists of|is made of|comprises?|is described by|is identified by|is defined by|tracks?|keeps?)\s+(?:a |an |the |its |their )?((?:[a-z][a-z' -]{1,30}?(?:,\s*|\s+and\s+|\s*/\s*)){1,8}[a-z][a-z' -]{1,30})(?=[.;:)]|\s+(?:so that|before|after|which|that|for)\b|$)", re.I)
_PAREN = re.compile(r"\b([a-z][a-z-]{2,})s?\s*\(([^)]{3,120})\)", re.I)
_WITH_LIST = re.compile(r"\b(?:with|including|carrying|containing|comprising)\s+((?:[a-z][a-z' -]{1,30}?(?:,\s*|\s+and\s+|\s*/\s*)){1,8}[a-z][a-z' -]{1,30})(?=[.;:)]|\s+(?:and|so that|before|after|from|to|through|via|that|which|for)\b|$)", re.I)
_POSSESSIVE = re.compile(r"\b(?:the|a|an|each|every|its|their)?\s*([a-z][a-z-]{2,})'s\s+([a-z][a-z-]{2,}(?:\s[a-z-]{2,})?)\b", re.I)
_ATTR_OF = re.compile(r"\b(?:set|update|amend|change|edit|configure|define|raise|lower|adjust|record|show|view|display)s?\s+(?:the\s+|a\s+|an\s+)?([a-z][a-z-]{2,}(?:\s[a-z-]{2,})?)\s+(?:of|on|for)\s+(?:a|an|the|each|every|any|its|their)?\s*(?:working|open|existing|given|selected)?\s*([a-z][a-z-]{2,})\b", re.I)
_BELONGS = re.compile(r"\b(?:an?|each|every|the)\s+([a-z][a-z-]{2,})\s+(?:belongs to|is owned by|is part of|is attached to|refers to|references)\s+(?:exactly\s+)?(?:one|a|an|the|its)\s+([a-z][a-z-]{2,})\b", re.I)
_HAS_MANY = re.compile(r"\b(?:an?|each|every|the)\s+([a-z][a-z-]{2,})\s+(?:has|contains|holds|carries|consists of|is made of|includes)\s+(?:one or more|several|many|multiple|a list of|\d+|zero or more|up to \d+|at least \d+|line)?\s*([a-z][a-z-]{2,})s\b", re.I)
_PER = re.compile(r"\b([a-z][a-z-]{2,})s?\s+per\s+([a-z][a-z-]{2,})\b", re.I)
_INVARIANT = [
    (r"\bnever\b[^.;]{0,40}\btwice\b|\bnot (?:be )?[a-z]+ (?:twice|more than once)\b|\bexactly once\b|\bat most once\b", "no duplicates: {noun} is {verb} at most once"),
    (r"\bnever (?:be )?(?:modified|edited|changed|altered|updated|deleted|removed)\b|\bimmutable\b|\bappend[- ]only\b|\bmust not be (?:modified|edited|changed|deleted)\b|\bread[- ]only after\b", "immutable {when}: {noun}"),
    (r"\bexactly one\b|\bone and only one\b|\bat most one\b|\bunique\b|\bmust not be double[- ]booked\b|\bdouble[- ]booking\b|\bnever (?:be )?(?:double|duplicate)", "uniqueness: {noun}"),
    (r"\bin the same transaction\b|\batomically\b|\ball or nothing\b|\bmust remain balanced\b|\bbalanced at all times\b", "atomicity: {noun} written in one transaction"),
    (r"\bnever (?:lost|discarded|dropped)\b|\bmust not (?:be )?(?:lost|discarded|dropped)\b|\bnot discard\b|\bno [a-z]+ (?:is|are) lost\b", "durability: no {noun} lost"),
    (r"\bconcealed\b|\bnobody .{0,30} can see\b|\bmust never see\b|\bnot visible to\b|\bhidden from\b", "visibility: {noun} concealed from some roles"),
    (r"\bidempotent\b|\bmust never double[- ]pay\b|\bnever (?:paid|charged|delivered) twice\b|\bde-?duplicated\b", "idempotency: {noun}"),
    (r"\bretained for\b|\bkept for\b|\bretention\b|\bfor \d+ years?\b", "retention: {noun}"),
]


@dataclass
class DEntity:
    name: str                                   # singular, lower-case: "order"
    fields: list[tuple[str, str, str]] = field(default_factory=list)      # (name, type, evidence)
    relations: list[tuple[str, str, str]] = field(default_factory=list)   # (kind, target, evidence): belongs_to / has_many
    states: list[str] = field(default_factory=list)
    transitions: list[tuple[str, str, str]] = field(default_factory=list) # (verb, state, evidence): a verb that puts the thing in a state
    edges: list[tuple[str, str, str]] = field(default_factory=list)       # (from_state, to_state, evidence): a transition the text states
    invariants: list[tuple[str, str]] = field(default_factory=list)       # (text, evidence)
    evidence: list[str] = field(default_factory=list)                     # requirement ids (any mention that scored)
    strong: list[str] = field(default_factory=list)                       # requirement ids where the thing is created/changed/constrained
    score: int = 0
    created: bool = False                                                 # object of a create/register/submit/book-type verb

    @property
    def kept(self) -> bool:
        """A record the system keeps (as opposed to a thing it merely controls or reads): created by a verb, or described
        with fields, a state machine or an invariant."""
        return self.created or bool(self.fields) or len(self.states) >= 2 or bool(self.invariants)

    @property
    def display(self) -> str:
        return "".join(p.capitalize() for p in self.name.replace("-", "_").split("_"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOT_PLURAL = {"redis", "status", "previous", "analysis", "basis", "kubernetes", "postgres", "series", "news", "aws", "gcs", "sms", "https",
               "process", "access", "address", "business", "progress", "success", "bus", "iris", "canvas", "atlas"}


def singular(n: str) -> str:
    n = n.lower()
    if n in _NOT_PLURAL or n.endswith(("ss", "us", "is", "ous", "ess", "ness")) or len(n) < 4:
        return n
    if n.endswith("ies") and len(n) > 4:
        return n[:-3] + "y"
    if n.endswith(("ches", "shes", "xes", "sses")):
        return n[:-2]
    if n.endswith("s"):
        return n[:-1]
    return n


def field_type(name: str) -> str:
    low = name.lower().replace(" ", "_")
    for rx, t in _TYPES:
        if re.search(rx, low):
            return t
    return "str"


#: words that are verbs in the lexicon but nouns when they name an attribute
_ATTRIBUTE_NOUNS = {"hash", "start", "end", "limit", "order", "record", "estimate", "total", "count", "rate", "score", "grade", "match",
                    "request", "offer", "charge", "claim", "share", "measure", "filter", "flag", "lock", "release", "return", "issue", "note",
                    "notes", "name", "label", "tag", "link", "file", "form", "report", "export", "import", "plan", "test", "run", "check",
                    "balance", "deposit", "transfer", "quote", "bill", "vote", "review", "comment", "reply", "status", "type", "value", "amount",
                    "strike", "notional", "price", "date", "time", "time_zone", "term", "expiry", "address", "email", "phone", "reason", "state"}


def _field_ok(f: str) -> bool:
    """A field name is a noun phrase; a lexicon verb is fine when it is the usual name of an attribute (hash, start_time, limit_price)."""
    words = f.split("_")
    if all(T.verb_of(w) and w not in _ATTRIBUTE_NOUNS and not w.endswith(("ed", "ing")) for w in words):
        return False
    if words[0].endswith("ing") or (T.verb_of(words[0]) and words[0] not in _ATTRIBUTE_NOUNS and len(words) == 1):
        return False
    return True


def _clean_field(f: str) -> str:
    f = re.sub(r"\b(?:e\.g\.|i\.e\.|etc\.?|such as)\b.*$", "", f.strip().lower()).strip(" .,;:-")
    f = re.sub(r"^(?:the|a|an|its|their|per|each|every|optional|current|new|existing)\s+", "", f)
    f = re.sub(r"^[a-z]+'s\s+", "", f)          # "buyer's email" -> email
    f = re.sub(r"\s+", " ", f)
    if not f or f in _FIELD_STOP or len(f) > 32 or len(f.split()) > 3 or re.search(r"\d{3,}|[()]", f):
        return ""
    if any(w in _FIELD_STOP for w in f.split()) and len(f.split()) > 1:
        return ""
    return f.replace(" ", "_")


def _noun_ok(n: str, an: Analysis, allow_actor: bool = False, allow_verb: bool = False) -> bool:
    _ENTITY_STOP = T.ENTITY_STOP - _ACTORISH
    base = singular(n)
    if len(base) < 3 or base in _ENTITY_STOP or n in _ENTITY_STOP or base in T.STOPWORDS or base in T.NON_OBJECTS or base in _REL_STOP:
        return False
    if base in T.ACTORS or n in T.ACTORS or base + "s" in T.ACTORS or any(base == a.split()[-1] for a in an.actors) or base in _ACTORISH:
        return allow_actor
    if T.verb_of(base) and base not in _NOUN_VERBS and not allow_verb:
        return False
    if base.endswith("ing") and base not in _NOUN_VERBS:
        return False
    if base.endswith("ly") or (base.endswith("ed") and T.verb_of(base) and base not in _NOUN_VERBS) or base in _UNITS or base in _TECH_WORDS:
        return False
    return bool(re.fullmatch(r"[a-z][a-z_-]{2,}", base))


_PREPS = {"to", "from", "with", "for", "in", "on", "at", "by", "into", "onto", "over", "under", "after", "before", "within", "through",
          "via", "per", "of", "as", "so", "that", "which", "when", "if", "up", "until", "than", "about", "against", "across", "between",
          "takes", "take", "makes", "make", "gives", "give", "becomes", "become", "remains", "remain", "is", "are", "was", "were", "has", "have",
          "uses", "use", "needs", "need", "goes", "go", "allows", "allow", "lets", "let", "must", "shall", "should", "can", "may", "will", "would",
          "does", "do", "did", "gets", "get", "puts", "put", "means", "mean", "leaves", "leave", "stays", "stay", "seems", "looks", "works", "fails", "fail"}


def _head_after(verb: str, s: T.Sentence) -> str:
    """The head noun of the phrase after the verb: 'upload PDF and Markdown documents' -> documents (the last noun before a
    preposition, verb or punctuation), where _object_after would stop at the first noun."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*|[(),;:.]", s.text.lower())
    for i, w in enumerate(words):
        if T.verb_of(w) == verb and not (i > 0 and words[i - 1] in T._DETERMINERS):
            head = ""
            prev = w
            for w2 in words[i + 1: i + 8]:
                after_det = prev in T._DETERMINERS or prev in ("one", "two", "new", "existing", "own")
                prev = w2
                noun_verb = w2.endswith("s") and singular(w2) in _NOUN_VERBS
                if w2 in ("(", ")", ",", ";", ":", ".") or w2 in _PREPS or (T.verb_of(w2) and (head or not w2.endswith("s")) and not after_det and not noun_verb and w2 not in ("order", "request", "offer")):
                    if w2 in ("and", "or") and not head:
                        continue
                    break
                if w2 in ("and", "or"):
                    continue
                if w2 in T.STOPWORDS or w2 in T._DETERMINERS:
                    continue
                if re.fullmatch(r"[a-z][a-z-]{2,}", w2) and w2 not in T.NON_OBJECTS:
                    head = w2
            return head
    return ""


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract(an: Analysis, functional_units: list[ReqUnit] | None = None, limit: int = 8) -> list[DEntity]:
    units = [u for u in (functional_units if functional_units is not None else an.requirements) if not u.sentence.assumed]
    ents: dict[str, DEntity] = {}
    alltext = " ".join(u.sentence.text for u in units)
    lowall = alltext.lower()

    def thing_like(noun: str) -> bool:
        base = singular(noun)
        return bool(re.search(r"\b(?:a|an|the|each|every|its|their|one|any|per|this|that|new|existing|\d+)\s+(?:[a-z-]+\s+){0,2}" + re.escape(base) + r"s?\b", lowall)
                    or re.search(r"\b(?:all|the|these|those|of|per|for|with|from|to|into|between|\d[\d,]*|[a-z]+(?:ed|ing|ate|ant|ive))\s+(?:[a-z-]+\s+)?" + re.escape(base) + r"(?:s|es)\b", lowall)
                    or len(re.findall(r"\b" + re.escape(base) + r"(?:s|es)\b", lowall)) >= 2)
    caps = {}
    for w in re.findall(r"\b([A-Z][a-z]{2,})\b", alltext):
        caps[w.lower()] = caps.get(w.lower(), 0) + 1
    lower = {w for w in re.findall(r"\b([a-z]{3,})\b", alltext)}
    # a word that is always capitalised (twice or more, or once mid-sentence) and never lower-case is a name, not a thing
    mid = {w.lower() for w in re.findall(r"(?<![.!?:]\s)(?<!^)(?<!\n)(?<!- )\b([A-Z][a-z]{2,})\b", alltext)}
    proper = {w for w, n in caps.items() if w not in lower and singular(w) not in lower and (n >= 2 or w in mid)}

    def determined(noun: str) -> bool:
        base = singular(noun)
        if base.endswith("ed"):          # "the customer used": a participle after a subject is not a determined noun
            return bool(re.search(r"\b(?:a|an|the|each|every|one|its|their|per|this|that)\s+" + re.escape(base) + r"s?\b", lowall))
        return bool(re.search(r"\b(?:a|an|the|each|every|one|its|their|per|this|that)\s+(?:[a-z-]+\s+)?" + re.escape(base) + r"s?\b", lowall))

    def ent(noun: str, rid: str, pts: int = 1, allow_actor: bool = False, strong: bool = False) -> DEntity | None:
        base = singular(noun)
        if base.endswith("ed") and (base[:-2] in lower or base[:-1] in lower or base[:-3] + base[-3] in lower or not determined(noun)):
            return None                                           # "used", "flagged": a participle, not a thing
        if not _noun_ok(noun, an, allow_actor, allow_verb=determined(noun)) or noun.lower() in proper or base in proper or not thing_like(noun):
            return None
        base = singular(noun)
        e = ents.setdefault(base, DEntity(base))
        e.score += pts
        if rid not in e.evidence:
            e.evidence.append(rid)
        if (strong or pts >= 2) and rid not in e.strong:
            e.strong.append(rid)
        return e

    for u in units:
        s = u.sentence
        text = s.text
        low = s.lower
        rid = u.id
        # objects of transactional verbs
        for v in s.verbs:
            if v in TRANSACTIONAL or v in STATE_VERBS or v in KEEPING:
                o = _head_after(v, s)
                if not o:
                    continue
                if v in KEEPING and v not in TRANSACTIONAL and v not in STATE_VERBS:
                    ent(o, rid, 1)
                    continue
                # "a batch of sensor readings": the thing is what follows "of"
                om = re.search(r"\b(?:batch|set|list|copy|number|series|stream) of (?:[a-z]+ )?([a-z][a-z-]{2,})\b", low)
                if o and singular(o) in ("batch", "set", "list", "copy", "number", "series", "stream") and om:
                    o = om.group(1)
                if o:
                    e = ent(o, rid, 2, allow_actor=v in ("randomise", "randomize", "enrol", "enroll", "unblind", "invite", "register", "onboard", "suspend", "provision", "assign", "book", "admit", "discharge"))
                    if e and v in TRANSACTIONAL:
                        e.created = True
                    if e and v in STATE_VERBS and v not in TRANSACTIONAL - set(STATE_VERBS):
                        st = STATE_VERBS[v]
                        if st not in e.states:
                            e.states.append(st)
                        e.transitions.append((v, st, rid))
        # passive state statements: "Fills are booked", "an alarm that is not acknowledged"
        for m in re.finditer(r"\b(?:an?|the|each|every|all|its|their)\s+([a-z][a-z-]{2,})s?\s+(?:that\s+)?(?:is|are|was|were|being|be)\s+(?:not\s+)?([a-z]+(?:ed|en))\b|\b([a-z][a-z-]{3,})s\s+(?:that\s+)?(?:are|were)\s+(?:not\s+)?([a-z]+(?:ed|en))\b", low):
            noun, part = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            before = low[max(0, m.start() - 12): m.start()].split()
            if before and before[-1] in ("from", "to", "of", "in", "on", "at", "by", "for", "with", "into", "via", "per"):
                continue                                  # "Fills received from a venue are booked": the subject is fills
            v = T.verb_of(part)
            if v in STATE_VERBS and _noun_ok(noun, an, allow_verb=True):
                e = ent(noun, rid, 1)
                if e:
                    st = STATE_VERBS[v]
                    if st not in e.states:
                        e.states.append(st)
                    e.transitions.append((v, st, rid))
        # adjective states: "a working order", "an open ticket", "pending claims"
        for m in re.finditer(r"\b(working|open|pending|draft|active|closed|expired|live|suspended|queued|scheduled)\s+([a-z][a-z-]{2,})s?\b", low):
            if _noun_ok(m.group(2), an):
                e = ent(m.group(2), rid, 1)
                if e and m.group(1) not in e.states:
                    e.states.insert(0, m.group(1))
        # parenthesised attribute lists: "stock items (SKU, quantity, warehouse, bin)"
        for m in _PAREN.finditer(text):
            noun, inside = m.group(1), m.group(2)
            if re.search(r"\b(?:e\.g|i\.e|see|such as|assumed|must|shall|can)\b|\d{2,}\s*(?:ms|s|%)", inside, re.I) and "," not in inside:
                continue
            if _ALT_PAREN.match(inside) or re.search(r"\b(?:or|vs|versus)\b", inside):
                continue                      # "(vanilla and barrier)", "(WPA2/WPA3)": kinds of the thing, not its fields
            fields = [_clean_field(f) for f in re.split(r",|\s+and\s+|/|;", inside)]
            fields = [f for f in fields if f and _field_ok(f)]
            is_obj = any(_head_after(v, s) and singular(_head_after(v, s)) == singular(noun) for v in s.verbs if v in TRANSACTIONAL)
            if (len(fields) >= 3 or (len(fields) >= 2 and is_obj)) and _noun_ok(noun, an):
                e = ent(noun, rid, 2)
                if e:
                    for f in fields:
                        if f not in [x[0] for x in e.fields]:
                            e.fields.append((f, field_type(f), rid))
        # "with instrument, notional, strike, expiry, direction and limit price" after a transactional verb + object
        for v in s.verbs:
            if v in TRANSACTIONAL or v in ("amend", "update", "edit", "change"):
                o = _head_after(v, s)
                if not o:
                    continue
                i = low.find(v)
                j = low.find(singular(o), i) if i >= 0 else -1
                wm = _WITH_LIST.match(text[j:].split(".")[0].lstrip()[len(o):].lstrip()) if j >= 0 else None
                if wm is None and j >= 0:
                    seg = text[j + len(o): j + len(o) + 40]
                    wm = _WITH_LIST.match(seg.lstrip()) if seg.lstrip().lower().startswith(("with ", "including ", "carrying ")) else None
                if wm:
                    fields = [_clean_field(f) for f in re.split(r",|\s+and\s+|/", wm.group(1))]
                    fields = [f for f in fields if f and _field_ok(f)]
                    if len(fields) >= 2:
                        e = ent(o, rid, 1)
                        if e:
                            for f in fields:
                                if f not in [x[0] for x in e.fields]:
                                    e.fields.append((f, field_type(f), rid))
        # "Every order has a delivery address and a chosen delivery slot", "A member has a display name, an email address …"
        for m in _HAS_LIST.finditer(text):
            noun, inside = m.group(1), m.group(2)
            if T.verb_of(noun) and noun not in ("order", "request", "offer", "claim", "match", "ticket", "record"):
                continue
            inside = re.sub(r"\s+and\s+(?:carries|carry|has|have|holds?|records?|stores?|includes?|contains?|keeps?|tracks?)\s+(?:a |an |the |its )?", ", ", inside)
            fields = [_clean_field(f) for f in re.split(r",|\s+and\s+|/", inside)]
            fields = [f for f in fields if f and _field_ok(f) and len(f) > 2]
            if len(fields) >= 2 and _noun_ok(noun, an, allow_actor=True):
                e = ent(noun, rid, 2, allow_actor=True)
                if e:
                    for f in fields:
                        f = re.sub(r"^(?:chosen|current|default|primary|main|weekly|daily|total)_", "", f) or f
                        if f not in [x[0] for x in e.fields]:
                            e.fields.append((f, field_type(f), rid))
        for m in re.finditer(r"\b(?:set|update|edit|change|record|enter|define)s?\s+(?:its|their|the)\s+((?:[a-z][a-z' -]{1,30}?(?:,\s*|\s+and\s+|\s*/\s*)){1,8}[a-z][a-z' -]{1,30})(?=[.;:)]|\s+(?:so that|before|after|which|that|for)\b|$)", text, re.I):
            subj = _subject_entity(low[: m.start()], ents)
            if subj is not None:
                for f in re.split(r",|\s+and\s+|/", m.group(1)):
                    f = _clean_field(re.sub(r"\s+in\s+[a-z]+$", "", f.strip()))
                    if f and f not in [x[0] for x in subj.fields] and not any(T.verb_of(w) and w not in ("estimate", "record", "order") for w in f.split("_")):
                        subj.fields.append((f, field_type(f), rid))
        # "amend the limit price or notional of a working order" → fields on order
        for m in _ATTR_OF.finditer(text):
            attr, noun = m.group(1).lower(), m.group(2)
            if _noun_ok(noun, an):
                e = ent(noun, rid, 1)
                if e:
                    for f in re.split(r"\s+or\s+|\s+and\s+|,\s*", attr):
                        f = _clean_field(f)
                        if f and f not in [x[0] for x in e.fields] and not T.verb_of(f):
                            e.fields.append((f, field_type(f), rid))
        # possessives: "the order's limit price", "the match's rights territory"
        for m in _POSSESSIVE.finditer(text):
            noun, attr = m.group(1), m.group(2).lower()
            if _noun_ok(noun, an) and singular(noun) not in T.ACTORS and not any(a == singular(noun) or a == noun for a in an.actors):
                e = ent(noun, rid, 1)
                f = _clean_field(attr)
                if e and f and f not in [x[0] for x in e.fields] and not T.verb_of(f.split("_")[0]):
                    e.fields.append((f, field_type(f), rid))
        # relations
        for m in _BELONGS.finditer(text):
            a, b = singular(m.group(1)), singular(m.group(2))
            if _noun_ok(a, an) and _noun_ok(b, an):
                ea, eb = ent(a, rid, 1), ent(b, rid, 1)
                if ea and eb:
                    ea.relations.append(("belongs_to", b, rid))
                    eb.relations.append(("has_many", a, rid))
        for m in _HAS_MANY.finditer(text):
            a, b = singular(m.group(1)), singular(m.group(2))
            if _noun_ok(a, an) and _noun_ok(b, an) and a != b:
                ea, eb = ent(a, rid, 1), ent(b, rid, 1)
                if ea and eb:
                    ea.relations.append(("has_many", b, rid))
                    eb.relations.append(("belongs_to", a, rid))
        for m in _PER.finditer(text):
            a, b = singular(m.group(1)), singular(m.group(2))
            if a in ents and _noun_ok(b, an) and b not in _REL_STOP and b != a:
                eb = ent(b, rid, 0)
                if eb:
                    ents[a].relations.append(("belongs_to", b, rid))
        # "is placed, then confirmed by the merchant, then shipped"
        for m in _THEN_SEQ.finditer(text):
            seq = [m.group(1).lower()] + [x.lower() for x in _THEN_ITEM.findall(m.group(2))]
            subj = _subject_entity(low[: m.start()], ents) or _first_entity_in(low, ents)
            if subj is None:
                head = re.search(r"\b(?:an?|the|each|every)\s+([a-z][a-z-]{2,})\s+(?:is|are|gets|becomes)\s+" + re.escape(seq[0]), low)
                subj = ent(head.group(1), rid, 1) if head else None
            if subj is not None:
                for st in seq:
                    if st not in subj.states:
                        subj.states.append(st)
                for a, b in zip(seq, seq[1:]):
                    subj.edges.append((a, b, rid))
        # transition sentences and table rows: "From Draft, an author can submit …", "from: draft; trigger: submit; to: review"
        for m in re.finditer(r"\bfrom\s*[:：]?\s*([a-z][a-z -]{1,20}?)\s*(?:,|;|\s)\s*(?:[^.;]{0,60}?)\b(?:to|→|->|becomes|moves to|goes to|reaches|enters)\s*[:：]?\s*([a-z][a-z -]{1,20}?)(?=[.;,)]|\s+(?:when|on|if|after|and|or|by)\b|$)", low):
            a, b = m.group(1).strip(), m.group(2).strip()
            if a in ("the", "a", "an") or b in ("the", "a", "an") or len(a.split()) > 2 or len(b.split()) > 2 or a == b or T.verb_of(a) or T.verb_of(b):
                continue
            subj = _first_entity_in(low, ents) or _last_entity_before(units, u, ents)
            if subj is None:
                continue
            for st in (a, b):
                if st not in subj.states:
                    subj.states.append(st)
            subj.edges.append((a, b, rid))
            verb_m = re.search(r"\bcan\s+([a-z]+)\b|\btrigger\s*[:：]\s*([a-z]+)|\baction\s*[:：]\s*([a-z]+)", low)
            if verb_m:
                v = next(g for g in verb_m.groups() if g)
                v = T.verb_of(v) or v
                subj.transitions.append((v, b, rid))
        # "may cancel it until it is shipped": cancel allowed from every state before shipped
        for m in _UNTIL.finditer(text):
            verb, until = T.verb_of(m.group(1).lower()) or m.group(1).lower(), m.group(2).lower()
            subj = _first_entity_in(low, ents)
            if subj is not None and verb in STATE_VERBS:
                st = STATE_VERBS[verb]
                for s0 in subj.states:
                    if s0 == until:
                        break
                    if s0 != st:
                        subj.edges.append((s0, st, rid))
                if st not in subj.states:
                    subj.states.append(st)
                if until not in subj.states:
                    subj.states.append(until)
                subj.invariants.append((f"{verb} is not allowed once {until}", rid))
        # "must confirm or decline an order within 2 hours, otherwise the order expires"
        for m in _OTHERWISE.finditer(text):
            subj = _first_entity_in(low, ents)
            if subj is not None:
                verbs_ = [T.verb_of(v.lower()) or v.lower() for v in (m.group(1), m.group(2)) if v]
                tail = T.verb_of(m.group(3).lower()) or m.group(3).lower().rstrip("s")
                src = subj.states[0] if subj.states else "new"
                for v in verbs_:
                    if v in STATE_VERBS:
                        st = STATE_VERBS[v]
                        if st not in subj.states:
                            subj.states.append(st)
                        subj.edges.append((src, st, rid))
                if tail in STATE_VERBS:
                    st = STATE_VERBS[tail]
                    if st not in subj.states:
                        subj.states.append(st)
                    subj.edges.append((src, st, rid))
                    subj.invariants.append((f"{st} when not {' or '.join(STATE_VERBS.get(v, v) for v in verbs_)} within the stated time", rid))
        # arrow lists: dev → staging → prod; submitted → adjudicating → approved/held/rejected → paid
        for m in _ARROW_LIST.finditer(text):
            parts = [p.strip().lower() for p in re.split(r"→|->|=>|⟶", m.group(1))]
            if len(parts) >= 2 and all(re.fullmatch(r"[a-z][a-z_-]{1,20}(?:\s*/\s*[a-z][a-z_-]{1,20})*", p) for p in parts):
                # attach to the entity named nearest before the list, else the most-scored entity in the sentence
                before = low[: low.find(parts[0])]
                cands = [n for n in ents if re.search(r"\b" + re.escape(n) + r"s?\b", before)]
                target = ents[cands[-1]] if cands else None
                if target is None:
                    target = next((ent(o, rid, 1) for v in s.verbs for o in [_head_after(v, s)] if o and _noun_ok(o, an)), None)
                if target is None:
                    target = _last_entity_before(units, u, ents)      # a "Lifecycle:" line under the entity's sentence
                if target is not None:
                    groups = [[q.strip() for q in p.split("/")] for p in parts]
                    for g in groups:
                        for p in g:
                            if p not in target.states:
                                target.states.append(p)
                    for ga, gb in zip(groups, groups[1:]):
                        # "approved/held/rejected → paid": only the alternatives that plausibly continue lead on; rejected/declined/
                        # cancelled/expired/failed are terminal, so paid follows approved (and held, marked as read-with-doubt)
                        cont = [x for x in ga if x not in _TERMINAL] or ga
                        for x in cont:
                            for y in gb:
                                target.edges.append((x, y, rid))
                        for x in ga:
                            if x in _TERMINAL and x not in target.states:
                                target.states.append(x)
        # negated actions on a state: "once shipped it must not be cancelled", "declined … cannot be confirmed later",
        # "cannot be marked done while …", "not refundable once …"
        for m in re.finditer(r"\b(?:must not|cannot|can't|may not|must never|shall not|never)\s+(?:be\s+|be able to\s+)?([a-z]+(?:ed|en)?)\b(\s+(?:later|again|twice|once|while|when|unless|without|for|until)\b)?", low):
            verb = T.verb_of(m.group(1)) or m.group(1)
            if m.group(2) and m.group(2).strip() in ("twice", "again"):
                continue                 # "never randomised twice" is the no-duplicates invariant below, not a ban on randomising
            subj = _subject_entity(low[: m.start()], ents) or _first_entity_in(low, ents)
            if subj is not None and (verb in STATE_VERBS or verb in KEEPING or verb in ("modify", "edit", "change", "delete", "refund", "issue")):
                cm = re.search(r"\b(once|while|when|unless|until|after|before|that (?:has been|is|was)|without)\b\s+(?:it\s+|the\s+[a-z]+\s+|an?\s+[a-z]+\s+)?(?:is\s+|has been\s+|was\s+|not\s+)?([a-z]+(?:ed|en))\b", low)
                if cm:
                    cond = f" {cm.group(1).split()[0]} {'not ' if 'not' in low[cm.start():cm.end()] else ''}{cm.group(2)}"
                else:
                    cm2 = re.search(r"\b(once|while|when|unless|until|after|before|without)\b\s+([^,.;]{3,40})", low)
                    cond = f" {cm2.group(1)} {' '.join(cm2.group(2).split()[:6])}" if cm2 else ""
                txt = f"{verb} is not allowed{cond}"
                if txt not in [x[0] for x in subj.invariants]:
                    subj.invariants.append((txt, rid))
        # invariants: the entity the sentence is about carries them
        for rx, tmpl in _INVARIANT:
            im = re.search(rx, low)
            if im and "uniqueness" in tmpl and re.search(r"\bbelongs to\b|\bis owned by\b|\bper\b", low):
                continue                               # "belongs to exactly one project" is a relation, not a uniqueness rule
            if im:
                subject = None
                se = _subject_entity(low[: im.start()], ents) or _first_entity_in(low, ents)
                if se is not None:
                    subject = se.name
                if subject is None:
                    o = next((o for v in s.verbs for o in [_head_after(v, s)] if o and _noun_ok(o, an)), None)
                    if o and ent(o, rid, 1) is not None:
                        subject = singular(o)
                if subject and subject in ents:
                    verb = next((v for v in s.verbs if v in STATE_VERBS or v in TRANSACTIONAL), "record")
                    wm = re.search(r"\b(?:once|after|when)\s+(?:it\s+|an?\s+[a-z]+\s+|the\s+[a-z]+\s+)?(?:is\s+|has been\s+)?([a-z]+(?:ed|en))\b", low)
                    when = f"once {wm.group(1)}" if wm else "after creation"
                    txt = tmpl.format(noun=subject, when=when, verb=STATE_VERBS.get(verb, verb + ("d" if verb.endswith("e") else "ed")))
                    if txt not in [x[0] for x in ents[subject].invariants]:
                        ents[subject].invariants.append((txt, rid))
                break
    # keep entities with evidence of being a thing: score ≥ 2, or stated fields/states/invariants/relations
    # frequent plural nouns and "each/every/a <noun>" count too (a thing the text keeps talking about)
    for u in units:
        words = u.sentence.words
        for w in u.sentence.nouns:
            if w.endswith("s") and len(w) > 4 and singular(w) in ents:
                ents[singular(w)].score += 1
        for i, w in enumerate(words[:-1]):
            if w in ("a", "an", "each", "every", "per") and singular(words[i + 1]) in ents:
                ents[singular(words[i + 1])].score += 1
    for e in ents.values():
        for rid in [f[2] for f in e.fields] + [i[1] for i in e.invariants] + [x[2] for x in e.edges] + [t[2] for t in e.transitions] + [r[2] for r in e.relations]:
            if rid not in e.strong:
                e.strong.append(rid)
    out = [e for e in ents.values() if e.score >= 2 or len(e.fields) >= 2 or len(e.states) >= 2 or e.invariants or e.relations]
    out.sort(key=lambda e: (-(e.score + 2 * len(e.fields) + len(e.states) + len(e.invariants)), e.name))
    out = out[:limit]
    keep = {e.name for e in out}
    for e in out:
        e.relations = [(k, t, r) for k, t, r in dict.fromkeys(e.relations) if t in keep and t != e.name]
        e.transitions = list(dict.fromkeys(e.transitions))
        e.edges = list(dict.fromkeys(e.edges))
        e.invariants = list(dict.fromkeys(e.invariants))
    return out


def _last_entity_before(units, u, ents: dict) -> "DEntity | None":
    """The entity named most recently in the two preceding requirement units (a state list on its own line belongs to it)."""
    idx = next((i for i, x in enumerate(units) if x is u), -1)
    for prev in reversed(units[max(0, idx - 2): idx]):
        e = _first_entity_in(prev.sentence.lower, ents)
        if e is not None:
            return e
    return None


def _first_entity_in(low: str, ents: dict) -> DEntity | None:
    """The entity mentioned earliest in the sentence (its grammatical subject, usually)."""
    best, pos = None, len(low) + 1
    for n, e in ents.items():
        m = re.search(r"\b" + re.escape(n) + r"s?\b", low)
        if m and m.start() < pos:
            best, pos = e, m.start()
    return best


def _subject_entity(before: str, ents: dict) -> DEntity | None:
    """The entity named last in the text before a phrase ("once an order is shipped it must never be …" → order)."""
    best, pos = None, -1
    for n, e in ents.items():
        for m in re.finditer(r"\b" + re.escape(n) + r"s?\b", before):
            if m.start() > pos:
                best, pos = e, m.start()
    return best


def aggregates(ents: list[DEntity]) -> list[list[DEntity]]:
    """Group entities by their belongs_to/has_many relations; each group is a domain aggregate (a candidate component)."""
    names = {e.name: e for e in ents}
    parent: dict[str, str] = {e.name: e.name for e in ents}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in ents:
        for _, t, _ in e.relations:
            if t in names:
                parent[find(e.name)] = find(t)
    groups: dict[str, list[DEntity]] = {}
    for e in ents:
        groups.setdefault(find(e.name), []).append(e)
    out = sorted(groups.values(), key=lambda g: (-sum(x.score for x in g), g[0].name))
    for g in out:
        g.sort(key=lambda x: (-x.score, x.name))
    return out


def to_markdown(ents: list[DEntity]) -> str:
    if not ents:
        return "No domain entity could be read from the text (no object of a create/submit/book-type verb, no attribute list).\n"
    s = ["| entity | fields (type) | relations | states | invariants | from |", "|---|---|---|---|---|---|"]
    for e in ents:
        s.append("| " + e.display + " | " + (", ".join(f"{n} ({t})" for n, t, _ in e.fields) or "—")
                 + " | " + (", ".join(f"{k} {t}" for k, t, _ in e.relations) or "—")
                 + " | " + ((", ".join(e.states) + ("; transitions: " + ", ".join(f"{a}→{b}" for a, b, _ in dict.fromkeys(e.edges)) if e.edges else "; transitions not stated")) if e.states else "—")
                 + " | " + ("; ".join(t for t, _ in e.invariants) or "—")
                 + " | " + ", ".join(e.evidence[:6]) + " |")
    return "\n".join(s) + "\n"
