"""Text analysis for requirements: segmentation, modality, quantities, actors, nouns, verbs.

No natural-language understanding is claimed. This is a sentence segmenter, a modality
lexicon, a quantity grammar and a verb lexicon — enough to turn a requirements document
into requirement units with their numbers and their subjects, deterministically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------

MODALITY = {
    "must": ("must", "shall", "required", "always", "never", "at least once", "exactly once", "mandatory"),
    "should": ("should", "expected", "normally", "ought"),
    "could": ("could", "may", "optionally", "nice to have", "ideally", "optional"),
}

SECTION_HEADINGS = {
    "nongoal": ("out of scope", "non-goals", "non goals", "nongoals", "not in scope", "exclusions"),
    "nonfunctional": ("non-functional", "nonfunctional", "non functional", "quality", "qualities", "performance", "nfr", "nfrs", "operational", "ops"),
    "constraint": ("constraint", "constraints", "environment", "assumptions", "context", "given", "tech stack", "stack"),
    "functional": ("functional", "features", "capabilities", "user stories", "scope"),
    "generic": ("requirements", "goals", "background", "alternatives"),
}

ACTORS = (
    "staff", "manager", "managers", "grower", "owner", "owners", "member", "members", "employee", "employees",
    "editor", "editors", "author", "authors", "reader", "readers", "reviewer", "reviewers", "buyer", "buyers",
    "seller", "sellers", "merchant", "merchants", "driver", "drivers", "patient", "patients", "doctor", "doctors",
    "student", "students", "teacher", "teachers", "player", "players", "guest", "guests", "anyone", "people",
    "tool", "command", "program", "script", "application", "app", "controller", "device", "bot", "job",
    "rider", "riders", "passenger", "passengers", "fleet manager", "fleet managers", "team lead", "team leads",
    "lead", "leads", "supervisor", "supervisors", "clerk", "clerks", "nurse", "nurses", "tenant", "citizen", "citizens",
    "shopper", "shoppers", "learner", "learners", "trainer", "trainers", "host", "hosts", "truck", "trucks", "vehicle", "vehicles",
    "customer", "customers", "user", "users", "admin", "admins", "administrator", "operator", "operators",
    "ops", "developer", "developers", "internal service", "internal services", "service", "services",
    "client", "clients", "team", "system", "subscriber", "subscribers", "tenant", "tenants",
    "engineer", "engineers", "analyst", "analysts", "agent", "agents", "visitor", "visitors", "we",
    "applicant", "applicants", "borrower", "borrowers", "underwriter", "underwriters", "senior underwriter", "auditor", "auditors",
    "regulator", "regulators", "accountant", "accountants", "recruiter", "recruiters", "candidate", "candidates", "contractor", "contractors",
    "supplier", "suppliers", "vendor", "vendors", "partner", "partners", "physician", "physicians", "pharmacist", "pharmacists",
    "parent", "parents", "coach", "coaches", "instructor", "instructors", "attendee", "attendees", "organiser", "organisers", "organizer", "organizers",
    "participant", "participants", "volunteer", "volunteers", "donor", "donors", "resident", "residents", "landlord", "landlords",
    "technician", "technicians", "inspector", "inspectors", "dispatcher", "dispatchers", "courier", "couriers", "farmer", "farmers",
    "retailer", "retailers", "wholesaler", "wholesalers", "broker", "brokers", "advisor", "advisors", "adviser", "advisers", "trader", "traders",
    "finance staff", "sales staff", "support staff", "support agent", "support agents", "moderator", "moderators", "publisher", "publishers",
)

#: actors that are people (a person's use case needs a surface: an API, a UI or a CLI)
HUMAN_ACTORS = frozenset(a for a in ACTORS if a not in (
    "tool", "command", "program", "script", "application", "app", "controller", "device", "bot", "job", "truck", "trucks",
    "vehicle", "vehicles", "internal service", "internal services", "service", "services", "system", "we", "team",
))

# verb -> (http method, interface verb)
VERBS = {
    "create": ("POST", "create"), "register": ("POST", "register"), "add": ("POST", "add"),
    "publish": ("POST", "publish"), "submit": ("POST", "submit"), "upload": ("POST", "upload"),
    "send": ("POST", "send"), "deliver": ("POST", "deliver"), "redeliver": ("POST", "redeliver"),
    "retry": ("POST", "retry"), "rotate": ("POST", "rotate"), "enable": ("POST", "enable"),
    "disable": ("POST", "disable"), "cancel": ("POST", "cancel"), "run": ("POST", "run"),
    "trigger": ("POST", "trigger"), "import": ("POST", "import"), "export": ("GET", "export"),
    "list": ("GET", "list"), "see": ("GET", "get"), "view": ("GET", "get"), "get": ("GET", "get"),
    "show": ("GET", "get"), "read": ("GET", "get"), "query": ("GET", "query"), "search": ("GET", "search"),
    "download": ("GET", "download"), "inspect": ("GET", "get"), "check": ("GET", "check"),
    "update": ("PUT", "update"), "edit": ("PUT", "update"), "change": ("PUT", "update"),
    "set": ("PUT", "set"), "choose": ("", "set"), "configure": ("PUT", "configure"),
    "save": ("POST", "save"), "load": ("GET", "load"), "open": ("", "open"), "close": ("", "close"),
    "switch": ("", "switch"), "adjust": ("PUT", "adjust"), "move": ("POST", "move"), "filter": ("GET", "filter"),
    "trim": ("", "trim"), "count": ("GET", "count"), "sync": ("POST", "sync"), "share": ("POST", "share"),
    "invite": ("POST", "invite"), "assign": ("POST", "assign"), "approve": ("POST", "approve"),
    "reject": ("POST", "reject"), "book": ("POST", "book"), "reserve": ("POST", "reserve"),
    "order": ("POST", "order"), "pay": ("POST", "pay"), "refund": ("POST", "refund"), "ship": ("POST", "ship"),
    "receive": ("", "receive"), "scan": ("POST", "scan"), "reuse": ("", "reuse"), "keep": ("", "keep"),
    "request": ("POST", "request"), "drop": ("", "drop"), "discard": ("", "discard"), "accept": ("POST", "accept"),
    "decline": ("POST", "decline"), "offer": ("", "offer"), "match": ("", "match"), "charge": ("", "charge"),
    "tag": ("PUT", "tag"), "extract": ("", "extract"), "split": ("", "split"), "index": ("", "index"),
    "summarize": ("", "summarize"), "summarise": ("", "summarise"), "view": ("GET", "get"), "rate": ("POST", "rate"),
    "delete": ("DELETE", "delete"), "remove": ("DELETE", "delete"), "revoke": ("DELETE", "revoke"),
    "manage": ("", "manage"), "notify": ("", "notify"), "notified": ("", "notify"), "store": ("", "store"),
    "persist": ("", "persist"), "validate": ("", "validate"), "verify": ("", "verify"), "sign": ("", "sign"),
    "compute": ("", "compute"), "calculate": ("", "compute"), "generate": ("", "generate"),
    "render": ("", "render"), "convert": ("", "convert"), "parse": ("", "parse"), "schedule": ("", "schedule"),
    "expose": ("GET", "expose"), "record": ("", "record"), "track": ("", "track"), "measure": ("", "measure"),
    "aggregate": ("", "aggregate"), "archive": ("", "archive"), "purge": ("DELETE", "purge"),
    "authenticate": ("", "authenticate"), "authorize": ("", "authorize"), "log": ("", "log"),
    "print": ("", "print"), "write": ("", "write"), "process": ("", "process"), "transform": ("", "transform"),
}

STOPWORDS = set("""
a an the and or but if then else of to in on at by for with from as is are was were be been being
this that these those it its their there here which who whom whose what when where why how all any
each every some no not into onto over under per via than also both either neither so such very can
will would could should must may might shall do does did done have has had having own same other
one two three four five six seven eight nine ten first second third new old more most less least up
down out off again further once before after above below between through during without within
about against among until while because whether we our us you your they them he she his her i me my
manually automatically continuously directly only also then later again currently immediately already
""".split())

#: tokens that are never the object of an operation (formats, adjectives, participles)
NON_OBJECTS = {"json", "csv", "xml", "http", "https", "signed", "valid", "matching", "current", "new", "old", "same",
               "existing", "named", "large", "small", "whole", "own", "each", "every", "other", "day", "days", "hour",
               "hours", "minute", "minutes", "second", "seconds", "week", "weeks", "month", "months", "year", "years",
               "ms", "time", "times", "way", "ways", "thing", "things", "code", "codes", "twice", "ever", "once", "again", "given", "then",
               "original", "partial", "clear", "background", "older", "less", "more", "most", "first", "last", "next", "later", "sometimes",
               "always", "never", "still", "already", "also", "only", "just", "even", "here", "there", "now", "today", "tomorrow", "yesterday",
               "business", "working", "monthly", "daily", "weekly", "hourly", "nightly", "system", "web", "online", "offline"}

_PASSIVE_AUX = {"is", "are", "be", "been", "was", "were", "get", "gets", "got", "being"}

_HTTP_CODES = {200, 201, 202, 204, 301, 302, 304, 400, 401, 403, 404, 405, 409, 410, 412, 415, 422, 429, 500, 501, 502, 503, 504}

_UNIT_KIND = {
    "/s": "rate", "per second": "rate", "per sec": "rate", "/sec": "rate", "rps": "rate", "qps": "rate",
    "/min": "rate", "per minute": "rate", "/h": "rate", "per hour": "rate", "/day": "rate", "per day": "rate",
    "ms": "latency", "millisecond": "latency", "milliseconds": "latency",
    "s": "duration", "sec": "duration", "secs": "duration", "second": "duration", "seconds": "duration",
    "min": "duration", "mins": "duration", "minute": "duration", "minutes": "duration",
    "h": "duration", "hr": "duration", "hrs": "duration", "hour": "duration", "hours": "duration",
    "d": "duration", "day": "duration", "days": "duration", "business day": "duration", "business days": "duration", "working day": "duration", "working days": "duration", "week": "duration", "weeks": "duration",
    "month": "duration", "months": "duration", "year": "duration", "years": "duration",
    "%": "percent", "percent": "percent",
    "kb": "size", "mb": "size", "gb": "size", "tb": "size", "bytes": "size", "byte": "size",
    "x": "factor",
}

_NUM = r"(?<![\w.:-])(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?P<mult>[kKmMbB])?(?![:\d])(?=[\s%/a-zA-Z)]|$)"
_UNIT = r"(?P<unit>%|/s|/sec|/min|/h|/day|per second|per sec|per minute|per hour|per day|rps|qps|ms|milliseconds?|secs?|seconds?|mins?|minutes?|hrs?|hours?|business days?|working days?|days?|weeks?|months?|years?|[kmgt]b|bytes?|x|s|h|d|m)?"
_QUANT_RE = re.compile(_NUM + r"\s?" + _UNIT + r"(?![a-zA-Z])", re.I)
_PERCENTILE_RE = re.compile(r"\bp(50|90|95|99|999)\b", re.I)
_INTERVAL_RE = re.compile(r"\bevery (\d+|ten|five|two|three|thirty|sixty) ?(seconds?|s|minutes?|min|hours?|h)\b", re.I)
_WORD_NUM = {"two": 2, "three": 3, "five": 5, "ten": 10, "thirty": 30, "sixty": 60}


def interval_seconds(text: str) -> float | None:
    """'every 5 seconds' / 'every ten seconds' / 'every 30 minutes' -> seconds, or None."""
    m = _INTERVAL_RE.search(text)
    if not m:
        return None
    n = _WORD_NUM.get(m.group(1).lower()) or float(m.group(1))
    unit = m.group(2).lower()
    return n * (60 if unit.startswith("min") else 3600 if unit.startswith("h") else 1)
_COMPARATOR_RE = re.compile(r"\b(not (?:add |take |exceed )?more than|not exceed|no more than|under|below|less than|at most|within|up to|<=|<|at least|more than|over|>=|>|exactly|sustained)\b", re.I)


@dataclass
class Quantity:
    value: float
    unit: str
    kind: str          # rate | latency | duration | count | size | percent | factor | number
    raw: str
    comparator: str = ""
    percentile: str = ""
    noun: str = ""     # the counted thing for kind=count, e.g. "endpoints"

    def target(self) -> str:
        """A metric target string like '<= 5 s' or '>= 1000 /s'."""
        low = self.comparator.lower()
        if low.startswith("not ") and "more than" in low or low == "not exceed":
            return f"<= {int(self.value) if float(self.value).is_integer() else self.value} {self.unit if self.unit and self.kind != 'count' else self.noun}".strip()
        cmp = {"under": "<", "below": "<", "less than": "<", "at most": "<=", "no more than": "<=",
               "within": "<=", "up to": "<=", "<=": "<=", "<": "<", "at least": ">=", "more than": ">",
               "over": ">", ">=": ">=", ">": ">", "exactly": "=", "sustained": ">="}.get(self.comparator.lower(), "")
        num = int(self.value) if float(self.value).is_integer() else self.value
        unit = self.unit if self.unit and self.kind != "count" else self.noun
        return f"{cmp} {num} {unit}".strip()


@dataclass
class Sentence:
    index: int
    text: str
    section: str = ""          # functional | nonfunctional | constraint | ""
    modality: str = ""         # must | should | could | ""
    is_bullet: bool = False
    quantities: list[Quantity] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    verbs: list[str] = field(default_factory=list)
    nouns: list[str] = field(default_factory=list)
    words: list[str] = field(default_factory=list)
    assumed: bool = False      # came from an engine-generated "(Assumed by the engine)" section

    @property
    def lower(self) -> str:
        return self.text.lower()

    def has(self, *needles: str) -> bool:
        low = self.lower
        return any(n in low for n in needles)


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

_BULLET_RE = re.compile(r"^\s*(?:[-*•](?=\s|[A-Za-z])|\d+[.)]\s)\s*")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s*(.+?)\s*#*\s*$")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")


def _section_of(line: str) -> str:
    """If ``line`` is a section heading, return its kind; else ''."""
    m = _HEADING_RE.match(line)
    title = re.sub(r"\s*\(.*?\)\s*$", "", (m.group(1) if m else line).strip().rstrip(":")).lower()
    if len(title.split()) > 4 or not title:
        return ""
    if not m and (line.strip().endswith((".", "?", "!")) or len(title) > 40):
        return ""
    for kind, keys in SECTION_HEADINGS.items():
        if any(k == title or title.startswith(k + " ") or title.endswith(" " + k) for k in keys):
            return kind
    return ""


def _units(text: str) -> list[tuple[str, bool]]:
    """Requirement units: (text, is_bullet). Bullets are one unit each; prose is split by sentence.

    Markdown headings are emitted as ("#" + title, False) so ``segment`` can use them as section markers.
    """
    out: list[tuple[str, bool]] = []
    prose: list[str] = []

    def flush() -> None:
        if prose:
            for s in _SENT_SPLIT.split(" ".join(prose)):
                if not s.strip():
                    continue
                if out and out[-1][0] and not out[-1][1] and len(s.split()) <= 2:
                    out[-1] = (out[-1][0] + " " + s.strip(), False)     # "Ever." belongs to the sentence before
                else:
                    out.append((s.strip(), False))
            prose.clear()

    bullet: list[str] = []

    def flush_bullet() -> None:
        if bullet:
            text_ = " ".join(bullet).strip()
            text_ = re.sub(r"(?<=[.!?]) (?=[A-Z][a-z]{0,8}\.$)", " ", text_)
            out.append((text_, True))
            bullet.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush(); flush_bullet()
            out.append(("", False))  # paragraph break marker
            continue
        if _HEADING_RE.match(line):
            flush(); flush_bullet()
            out.append(("#" + _HEADING_RE.match(line).group(1).strip(), False))
            continue
        if _BULLET_RE.match(line):
            flush(); flush_bullet()
            bullet.append(_BULLET_RE.sub("", line).strip())
        elif bullet and line.startswith((" ", "\t")):
            bullet.append(line.strip())
        else:
            flush_bullet()
            prose.append(line.strip())
    flush(); flush_bullet()
    return out


def modality(text: str) -> str:
    low = text.lower()
    if re.search(r"\bmay not\b|\bmay never\b|\bmust not\b|\bshall not\b|\bno \w+(?: \w+)? (?:may|can|should) (?:be|ever)\b|\bnever\b", low):
        return "must"          # a prohibition is a hard requirement, not an option
    for kind in ("must", "should", "could"):
        for cue in MODALITY[kind]:
            if re.search(r"\b" + re.escape(cue) + r"\b", low):
                return kind
    return ""


def quantities(text: str) -> list[Quantity]:
    out: list[Quantity] = []
    for m in _QUANT_RE.finditer(text):
        raw_num = m.group("num").replace(",", "")
        value = float(raw_num)
        mult = (m.group("mult") or "").lower()
        unit = (m.group("unit") or "").lower()
        if mult == "k" and not unit:
            value *= 1000
        elif mult in ("m", "b") and not unit and m.group("mult").isupper():
            value *= 1_000_000 if mult == "m" else 1_000_000_000
        elif mult:
            # "5m" style; treat the letter as the unit if no unit followed
            unit = unit or mult
        kind = _UNIT_KIND.get(unit, "number")
        if unit == "m":
            unit, kind = "min", "duration"
        if kind == "number" and int(value) in _HTTP_CODES and not mult:
            kind = "code"  # an HTTP status code, not a quantity
        before = text[max(0, m.start() - 24): m.start()]
        after = text[m.end(): m.end() + 32]
        cmp_m = _COMPARATOR_RE.search(before)
        comparator = cmp_m.group(1) if cmp_m else ""
        pct = _PERCENTILE_RE.search(before + " " + after)
        noun = ""
        if kind == "code":
            out.append(Quantity(value, "", "code", m.group("num"), "", "", ""))
            continue
        if kind == "number":
            nm = re.match(r"\s*([a-zA-Z][a-zA-Z_-]*)(?:\s+([a-zA-Z][a-zA-Z_-]*))?\s*(/s\b|/sec\b|per second|per sec\b|/min\b|per minute|/h\b|per hour|/day\b|per day)?", after)
            if nm and nm.group(1).lower() not in STOPWORDS and nm.group(1).lower() not in VERBS and not nm.group(1).lower().startswith("xx"):
                noun = nm.group(1).lower()
                second = (nm.group(2) or "").lower()
                if nm.group(3) and second and second not in STOPWORDS:
                    noun = second                      # "return requests/day": the counted thing is requests
                if nm.group(3) and (not second or second not in STOPWORDS):
                    kind, unit = "rate", noun + " " + nm.group(3).strip()
                else:
                    kind = "count"
        out.append(Quantity(value, unit, kind, m.group(0).strip(), comparator, pct.group(0).lower() if pct else "", noun))
    return out


def per_second(q: "Quantity") -> float | None:
    """Normalise a rate quantity to per second (None if it is not a rate)."""
    unit = q.unit.lower()
    if "/s" in unit or "per second" in unit or "per sec" in unit or unit in ("rps", "qps"):
        return q.value
    if "/min" in unit or "per minute" in unit:
        return q.value / 60
    if "/h" in unit or "per hour" in unit:
        return q.value / 3600
    if "/day" in unit or "per day" in unit:
        return q.value / 86400
    return None


def tokens(text: str) -> list[str]:
    return [w.rstrip(".-") for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_.-]*", text.lower())]


def _lemma(word: str) -> str:
    for suf in ("ies", "es", "s"):
        if word.endswith(suf) and len(word) > len(suf) + 2:
            return word[: -len(suf)] + ("y" if suf == "ies" else "")
    return word


def verb_of(word: str) -> str:
    """The lexicon verb a token inflects from ('delivered' -> 'deliver', 'retried' -> 'retry'), or ''."""
    cands = [word]
    if word.endswith("ies"):
        cands.append(word[:-3] + "y")
    elif word.endswith("es"):
        cands += [word[:-2], word[:-1]]
    elif word.endswith("s"):
        cands.append(word[:-1])
    if word.endswith("ied"):
        cands.append(word[:-3] + "y")
    elif word.endswith("ed"):
        cands += [word[:-2], word[:-1]]
    if word.endswith("ing"):
        cands += [word[:-3], word[:-3] + "e"]
    for c in cands:
        if len(c) >= 3 and c in VERBS:
            return c
    return ""


_DETERMINERS = {"a", "an", "the", "each", "every", "per", "their", "own", "of", "this", "that", "these", "those", "any", "no", "one", "same",
                "original", "new", "existing", "current", "delivered", "returned", "first", "last", "next", "all", "its", "his", "her", "our", "my", "your", "another"}


def analyse_sentence(index: int, text: str, section: str, is_bullet: bool) -> Sentence:
    words = tokens(text)
    # a lexicon verb right after a determiner is a noun ("an order item", "the refund", "each return")
    verbs = [v for i, w in enumerate(words) for v in [verb_of(w)] if v and not (i > 0 and words[i - 1] in _DETERMINERS)]
    nouns = [w for w in words if w not in STOPWORDS and not verb_of(w) and len(w) > 2
             and not w.replace(".", "").isdigit()]
    low = text.lower()
    actors = sorted({a for a in ACTORS if re.search(r"\b" + re.escape(a) + r"s?\b", low)}, key=len, reverse=True)
    return Sentence(index, text, section, modality(text), is_bullet, quantities(text), actors, verbs, nouns, words)


def segment(text: str) -> list[Sentence]:
    """Split a requirements document into analysed requirement units."""
    out: list[Sentence] = []
    section = ""
    assumed = False
    n = 0
    for unit, is_bullet in _units(text):
        if not unit:
            continue
        if unit.startswith("#"):
            section = _section_of(unit[1:]) or ""
            section = "" if section == "generic" else section
            assumed = "assumed by the engine" in unit.lower()
            continue
        sec = _section_of(unit) if not is_bullet else ""
        if sec:
            section = "" if sec == "generic" else sec
            assumed = "assumed by the engine" in unit.lower()
            continue
        sent = analyse_sentence(n, unit, section, is_bullet)
        sent.assumed = assumed
        out.append(sent)
        n += 1
    return out


def title_of(text: str) -> str:
    """The first heading or the first line, cleaned, as a project name."""
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            return re.split(r"\s+[—–-]\s+", m.group(1))[0].strip()
        if line.strip():
            head = re.split(r"\s+[—–-]\s+|[.:]|\bthat\b|\bwhich\b|\bfor\b", line.strip())[0].strip()
            return " ".join(head.split()[:7])[:60]
    return "system"


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "system"
