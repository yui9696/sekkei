"""Document structure as engineers actually write it -> the Markdown shape the engine reads.

Real specifications are not the template: they carry front matter (author, date, status),
numbered headings without ``#`` (``2. 機能要件``, ``3.1 Performance:``), requirement tables
(``| No | 機能 | 内容 | 優先度 |``), checkboxes, nested bullets, user stories in headings
(``### RET-101 — As a customer, I want …``), inline labels (``TODO``, ``DECIDED:``,
``out of scope:``, ``Ana:``) and an "Alternatives considered" section. This pass rewrites
those into headings, bullets and prose; it is language-agnostic where it can be and knows
the Japanese and English section words. Everything it does is reported as *notes* so a
reader can see what was folded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# section words: canonical heading -> cues (lowercase, JA and EN)
SECTIONS = [
    ("Out of scope", ("out of scope", "non-goals", "non goals", "nongoals", "not in scope", "exclusions", "対象外", "スコープ外", "非目標", "範囲外", "やらないこと", "除外", "対象としない")),
    ("Non-functional", ("non-functional", "nonfunctional", "non functional", "quality", "qualities", "nfr", "nfrs", "operational requirements", "非機能", "品質要件", "性能要件", "運用要件", "数字")),
    ("Constraints", ("constraint", "constraints", "environment", "assumptions", "tech stack", "stack", "tech notes", "technology", "technical notes", "制約", "前提", "環境", "技術", "技術スタック", "開発体制", "体制", "条件")),
    ("Functional", ("functional", "features", "capabilities", "user stories", "stories", "use cases", "scope", "goals", "機能要件", "機能", "ユースケース", "ユーザーストーリー", "やりたいこと", "できること",
                    "action items", "actions items", "remediation", "remediations", "follow-ups", "follow ups", "corrective actions", "是正措置", "対応事項", "requested change", "requested changes", "the change")),
    ("Must", ("must have", "must-have", "must haves", "p0", "priority 0", "mvp", "必須要件")),
    ("Should", ("should have", "should-have", "should haves", "p1", "priority 1", "推奨要件")),
    ("Could", ("could have", "could-have", "nice to have", "nice-to-have", "p2", "p3", "priority 2", "priority 3", "later", "任意要件", "あれば良い")),
    ("Requirements", ("requirements", "要件", "要求", "要求事項", "仕様")),
    ("Alternatives", ("alternatives", "alternatives considered", "options considered", "rejected alternatives", "代替案", "検討した代替案", "不採用案")),
    ("Background", ("motivation", "background", "context", "overview", "summary", "introduction", "problem", "why", "概要", "背景", "目的", "現状", "課題",
                    "timeline", "root cause", "root causes", "what went well", "what went wrong", "impact", "detection", "what happened", "lessons", "lessons learned",
                    "what we are building", "user segments", "users", "personas", "kpis", "goals and kpis", "metrics", "経緯", "原因", "影響", "タイムライン")),
    ("Aside", ("appendix", "references", "open questions", "questions", "risks", "glossary", "changelog", "history", "actions", "next steps", "open items", "reference information", "参考", "付録", "用語", "更新履歴", "備考", "検討事項", "宿題", "アクション", "次のステップ", "未決事項", "提出物", "deliverables", "submission")),
]
_SECTION_KEYS = {k: canon for canon, keys in SECTIONS for k in keys}

# a heading-like line: "2. 機能要件", "3.1 性能:", "II. Goals", "Requirements:" (short, no sentence punctuation)
_NUMBERED = re.compile(r"^\s*(?:[A-Z]?\d+(?:\.\d+)*[.)]?|[A-Z]\.\d+(?:\.\d+)*|[IVX]+[.)]|[①-⑳]|第\s*\d+\s*[章節条項]|\d+[章節条項]|[A-Z][.)])\s+(?P<title>[^。.!?]{1,40}?)\s*[:：]?\s*$")
_CLAUSE_NUM = re.compile(r"^\s*(?:[A-Z]\.\d+(?:\.\d+)+|\d+(?:\.\d+)+|第\s*\d+\s*[条項]|\(\d+\)|\d+\))\s+(?=\S)")
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D▶◀◆◇■□●○★☆]+")
_HTML_TAG = re.compile(r"</?(?:details|summary|div|span|p|br|b|i|u|em|strong|code|pre|table|tr|td|th|ul|ol|li|a|img)\b[^>]*>", re.I)
_EXCLUDED_INLINE = re.compile(r"\b(?:is|are) excluded\b(?! from (?!(?:this |the )?(?:contract|project|scope|release|work|phase|mvp|engagement|delivery|this|tender|proposal|statement of work)))|\b(?:is|are) (?:out of scope|not in scope|not part of this)\b|\bfor information only\b|\bnot a requirement\b|\bnot (?:in|within) (?:the )?scope\b|は?対象外|はスコープ外|含まない", re.I)
_LABELLED = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?\s+)?(?P<label>[^:：。.]{1,24})\s*[:：]\s*(?P<body>\S.*)$")
_ID_PRIORITY = re.compile(r"^\s*(?P<id>[A-Za-z]{1,4}-?\d{1,4})\s*\((?P<prio>must|should|could|may|p0|p1|p2|p3)\)\s*[:：]?\s*", re.I)
_OWNER_DUE = re.compile(r"\s*(?:Owner|Due|Assignee|担当|期限)\s*[:：]\s*[^.。]*[.。]?", re.I)
_HEADING = re.compile(r"^\s*(#{1,6})\s*(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^(?P<indent>\s*)(?:[-*+•・●○■□▪◦]|\d+[.)．]|[①-⑳])\s+(?P<body>.*)$")
_CHECKBOX = re.compile(r"^\[( |x|X|✓)\]\s*")
_META_KEY = re.compile(r"^\s*\**(?:author|authors|status|owner|owners|epic owner|reviewers?|date|created|updated|version|labels?|story points|epic|sprint(?: target)?|priority|tags?|present|attendees|requested by|requester|channel|approvers?|作成|作成者|作成日|更新日|更新|版|ステータス|担当|承認|レビュー|出席|参加者|依頼者)\**\s*[:：]", re.I)
_TITLE_LINE = re.compile(r"^\s*(?:epic|change request|cr|rfc|ticket|story|issue|design doc|spec|proposal|要件定義書|仕様書)\s*[:：]?\s*(?:[A-Z]+-\d+|\d+)?\s*[—–:-]?\s*(?P<rest>[^\n]{3,})$", re.I)
_META_INLINE = re.compile(r"(?:\*\*[^*]{1,20}:\*\*|[A-Za-z ]{1,20}:)\s*[^·|]{1,40}(?:\s*[·|]\s*|$)")
_STORY = re.compile(r"^\s*(?:[A-Z][A-Z0-9]+-\d+\s*[—–:-]?\s*)?as an? (?P<actor>[a-z][a-z /-]{1,40}?),\s*i (?:want|need|would like)(?: to)?\s+(?P<want>.+?)(?:,?\s+so that\s+(?P<why>.+))?[.]?\s*$", re.I)
_TICKET = re.compile(r"^\s*(?P<key>[A-Z][A-Z0-9]+-\d+)\s*[—–:-]\s*(?P<rest>.+)$")
_TODO = re.compile(r"^\s*(?:todo|fixme|question|q|open question|要確認|未定|要検討|宿題)\b\s*[:：]?\s*", re.I)
_TENTATIVE = re.compile(r"\b(?:maybe|later maybe|perhaps|not sure|tbd|tbc|to be decided|to be confirmed)\b|\?\s*$|未定|検討中|かも", re.I)
_OUT_INLINE = re.compile(r"^\s*(?:out of scope|non-goal|non-goals|not in scope|対象外|スコープ外|やらないこと)[^:：]{0,20}[:：]\s*(?P<body>.+)$", re.I)
_DECIDED = re.compile(r"^\s*(?:decided|decision|agreed|決定|確定)\s*[:：]\s*(?P<body>.+)$", re.I)
_SPEAKER = re.compile(r"^\s*(?P<name>[A-Z][a-z]{1,15})\s*:\s+(?P<body>.+)$")
_SEPARATOR_ROW = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_DEADLINE = re.compile(r"(?:\bMVP\b|\brelease\b|\bship\b|\blaunch\b|\bgo[- ]live\b|\bdeadline\b|\bdue\b|リリース|納期|稼働開始|ローンチ)[^.。]{0,30}?(?:\d{4}\s*年\s*\d{1,2}\s*月|\d{4}[/-]\d{1,2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{4}|q[1-4] \d{4}|\d+ (?:weeks?|months?|days?)|\d+\s*(?:週間|ヶ月|か月|日))|\b(?:in|within) \d+ (?:weeks?|months?)\b|\d{4}\s*年\s*\d{1,2}\s*月\s*(?:リリース|稼働|ローンチ)", re.I)
_DATE_LINE = re.compile(r"^\s*[^。.]{0,30}(?:\d{4}[/.-]\d{1,2}[/.-]\d{1,2}|\d{4}年\d{1,2}月)[^。.]{0,30}$")

PRIORITY_WORDS = {
    "must": ("must", "必須", "high", "m", "mandatory", "required", "p0", "p1", "高"),
    "should": ("should", "推奨", "medium", "s", "important", "p2", "中", "重要"),
    "could": ("could", "任意", "low", "c", "optional", "nice to have", "nice-to-have", "p3", "低", "あれば"),
}
_CONTENT_HEADERS = ("内容", "要件", "説明", "詳細", "requirement", "description", "content", "detail", "details", "story", "criteria", "acceptance", "text", "statement", "機能要件", "要求",
                    "answer", "response", "回答", "change", "changes", "変更内容", "capability", "feature description", "clause text")
_PRIORITY_HEADERS = ("優先度", "優先", "priority", "moscow", "importance", "重要度", "必須")
_STATUS_HEADERS = ("status", "state", "ステータス", "状態", "区分", "type", "種別", "kind")
_NOT_WORK = {"current", "existing", "done", "delivered", "n/a", "na", "not applicable", "out of scope", "std", "standard", "config", "configuration",
             "既存", "対応済", "済", "現状", "対象外", "任意"}
_ID_HEADERS = ("no", "no.", "#", "id", "番号", "項番", "key", "req", "req id", "識別子", "ref", "clause", "row")
_TITLE_HEADERS = ("機能", "項目", "名称", "feature", "title", "name", "function", "分類", "カテゴリ", "category")


@dataclass
class Canonical:
    text: str
    notes: list[str] = field(default_factory=list)
    tentative: list[str] = field(default_factory=list)   # sentences marked TBD/maybe (kept, priority could)
    todos: list[str] = field(default_factory=list)       # TODO/questions lifted out of the requirements
    alternatives: list[str] = field(default_factory=list)  # "Alternatives considered" items
    deadline: str = ""                                    # a stated release date / horizon, verbatim
    rationales: dict[str, str] = field(default_factory=dict)  # sentence -> "so that …" from a user story


def _section_of(title: str) -> str | None:
    t = re.sub(r"[（(].*?[)）]", "", title).strip().strip(":：").lower()
    t = re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", t)
    if not t:
        return None
    if t in _SECTION_KEYS:
        return _SECTION_KEYS[t]
    for k, canon in _SECTION_KEYS.items():
        if (len(k) >= 3 or not k.isascii()) and (t.startswith(k + " ") or t.endswith(" " + k) or (not k.isascii() and k in t and len(t) <= len(k) + 6)):
            return canon
    return None


def _priority_of(cell: str) -> str:
    c = cell.strip().lower().strip("*")
    for p, words in PRIORITY_WORDS.items():
        if c in words or any(c.startswith(w) for w in words if len(w) > 2):
            return p
    return ""


def _table_to_bullets(rows: list[list[str]], notes: list[str]) -> list[str]:
    """A requirements table -> one bullet per row: '- <content> (<priority>)' with the row id kept as a prefix."""
    header = [c.strip().lower().strip("*") for c in rows[0]]
    body = rows[1:]
    if not body:
        return []

    def col(names: tuple[str, ...]) -> int | None:
        for i, h in enumerate(header):
            if h in names or any(h.startswith(n) for n in names if len(n) > 2):
                return i
        return None

    ci = col(_CONTENT_HEADERS)
    if ci is None:
        # not a requirements table (KPI | Today | Target, Metric | Value …): every cell is kept, labelled by its header
        out = []
        si0 = col(_STATUS_HEADERS)
        for r in body:
            if si0 is not None and si0 < len(r) and r[si0].strip().lower().strip("*") in _NOT_WORK:
                notes.append(f"table row with status '{r[si0].strip()}' is not work: {r[0][:40]}")
                continue
            cells = [(rows[0][k].strip() if k < len(rows[0]) else "", c.strip()) for k, c in enumerate(r) if c.strip()]
            if not cells:
                continue
            if len(r) < len(rows[0]):
                notes.append(f"table row with fewer cells than the header kept as text: {' | '.join(c for _, c in cells)[:50]}")
            out.append("- " + "; ".join(f"{h}: {c}" if h and h.lower() != c.lower() and h != "#" else c for h, c in cells).lstrip("#").strip())
        notes.append(f"table with columns {', '.join(rows[0])}: {len(out)} rows kept with every cell")
        return out
    pi = col(_PRIORITY_HEADERS)
    ii = col(_ID_HEADERS)
    ti = col(_TITLE_HEADERS)
    si = col(_STATUS_HEADERS)
    if pi is None and si is not None and any(_priority_of(r[si]) for r in body if si < len(r)):
        pi = si                                     # 区分 = 必須/任意 is a priority column
    skipped = 0
    out = []
    for r in body:
        if ci >= len(r) or not r[ci].strip():
            text = "; ".join(c.strip() for c in r if c.strip())
            if text:
                out.append("- " + text)
                notes.append(f"table row without a content cell kept as text: {text[:50]}")
            continue
        content = r[ci].strip()
        if si is not None and si < len(r) and si != ci:
            status = r[si].strip().lower().strip("*")
            if status in _NOT_WORK or any(status.startswith(w) for w in ("current", "existing", "n/a", "done", "既存", "対応済")):
                skipped += 1
                notes.append(f"table row with status '{r[si].strip()}' is not work: {content[:50]}")
                continue
        rid = r[ii].strip() if ii is not None and ii < len(r) and ii != ci else ""
        prio = _priority_of(r[pi]) if pi is not None and pi < len(r) and pi != ci else ""
        title = r[ti].strip() if ti is not None and ti < len(r) and ti not in (ci, ii) else ""
        if title and title.lower() not in content.lower() and len(title) <= 20:
            content = f"{title}: {content}" if content[:1].isascii() else f"{title}: {content}"
        tail = ""
        if prio:
            tail = {"must": " (must)", "should": " (should)", "could": " (could)"}[prio]
        prefix = (f"N-{rid} " if rid.isdigit() else f"{rid} ") if rid and re.fullmatch(r"[A-Za-z]{0,4}-?\d{1,4}", rid) else ""
        out.append(f"- {prefix}{content}{tail}")
    notes.append(f"table with columns {', '.join(rows[0])}: {len(out)} rows became requirements"
                 + (f" (priority from column '{rows[0][pi]}')" if pi is not None else "") + (f"; {skipped} rows skipped by their status column" if skipped else ""))
    return out


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.replace("\\¦", "|") for c in re.split(r"(?<!\\)\|", s.replace("\\|", "\\¦"))]


_GWT = re.compile(r"^\s*(given|when|then|and|but)\b\s*(.*)$", re.I)
_STORY_PROSE = re.compile(r"^\s*(?:[A-Z][A-Z0-9]+-\d+\s*[—–:-]?\s*)?as an? [a-z][a-z /-]{1,40}?,\s*i (?:want|need|would like)\b", re.I)
_SECTION_NUM = re.compile(r"^\s*\d+(?:\.\d+)+\s+(?=[A-Za-z぀-ヿ㐀-䶿一-鿿])")
_PAGE_LINE = re.compile(r"^\s*(?:page\s+\d+(?:\s+of\s+\d+)?|\d+\s*/\s*\d+|-\s*\d+\s*-|\d+)\s*$", re.I)
_META_TABLE_HEADERS = {"field", "value", "key", "item", "property", "attribute", "項目", "値", "term", "definition", "glossary", "用語", "定義", "意味"}
_TEAM_COUNT = re.compile(r"\(?(\d+)\)?\s*(?:x\s*)?(?:engineers?|devs?|developers?|sres?|people|persons?|members?|backend|frontend|mobile|platform|full[- ]stack|qa|designers?|ops|contractors?|leads?|architects?|testers?|analysts?|scientists?|validation lead|data scientists?|名|人)", re.I)
_SYSTEMS_AFFECTED = re.compile(r"^\s*(?:systems? affected|affected systems?|services? affected|existing services?|touches|impacted services?|対象システム|影響システム)\s*[:：]\s*(?P<body>.+)$", re.I)
_ACTION_SECTION = ("actions", "next steps", "todo", "todos", "open questions", "questions", "open items", "宿題", "アクション", "次のステップ", "検討事項", "未決事項")


def _is_meta_table(rows: list[list[str]]) -> bool:
    """A two-column key/value table (Owner | Priya …, Status | DRAFT) is front matter, not requirements."""
    if not rows or len(rows[0]) != 2:
        return False
    header = [c.strip().lower().strip("*") for c in rows[0]]
    if any(h in _META_TABLE_HEADERS for h in header):
        return True
    body = rows[1:]
    if not body:
        return False
    keys = [r[0].strip().lower() for r in body if len(r) == 2]
    if all(_META_KEY.match(k + ":") for k in keys):
        return True
    return all(len(r[1].strip()) <= 60 and not re.search(r"\b(?:must|should|can|shall|within|every)\b|[。]", r[1]) for r in body if len(r) == 2) and len(body) <= 8


def _merge_two_line_header(rows: list[list[str]]) -> list[list[str]]:
    """'| ID | Requirement | Prio- |' + '|    |             | rity |' -> one header row."""
    if len(rows) >= 3 and len(rows[0]) == len(rows[1]) and all(len(c.strip()) <= 6 or not c.strip() for c in rows[1]) \
            and any(c.strip() for c in rows[1]) and not any(re.search(r"\b(?:must|should|can)\b|[。.]", c) for c in rows[1]):
        merged = [(a.strip().rstrip("-") + b.strip()) if a.strip().endswith("-") else (a.strip() + (" " + b.strip() if b.strip() else "")) for a, b in zip(rows[0], rows[1])]
        return [merged] + rows[2:]
    return rows


_PAGE_MARK = re.compile(r"\bpage\s+\d+\s+of\s+\d+\b|^\s*[-–]\s*\d+\s*[-–]\s*$", re.I)


def _unwrap_pasted(lines: list[str], notes: list[str]) -> list[str]:
    """Text pasted from a PDF: repeated page headers/footers are dropped and hard-wrapped lines are re-joined
    (a line without end punctuation followed by a line starting in lower case; 'auto-' + 'approved' stays one word)."""
    if not any(_PAGE_MARK.search(l) for l in lines):
        return lines
    counts: dict[str, int] = {}
    for l in lines:
        k = re.sub(r"\s+", " ", _PAGE_MARK.sub("", l)).strip()
        if k:
            counts[k] = counts.get(k, 0) + 1
    repeated = {k for k, n in counts.items() if n >= 2 and len(k) >= 8}
    kept: list[str] = []
    dropped = 0
    seen: set[str] = set()
    for n, l in enumerate(lines):
        k = re.sub(r"\s+", " ", _PAGE_MARK.sub("", l)).strip()
        if k in repeated and not _BULLET.match(l):
            if n <= 1 and k not in seen:
                seen.add(k)
                kept.append(_PAGE_MARK.sub("", l).rstrip())     # the document title, kept once
                continue
            dropped += 1
            continue
        if _PAGE_MARK.search(l):
            dropped += 1
            continue
        kept.append(l)
    out: list[str] = []
    for l in kept:
        s = l.rstrip()
        if len(out) > 1 and out[-1] and s and not _BULLET.match(s) and not _HEADING.match(s) and not s.startswith("|"):
            prev = out[-1]
            if prev.endswith("-") and s[:1].islower():
                out[-1] = prev + s.lstrip()
                continue
            if not prev.rstrip().endswith((".", "!", "?", ":", ";", "。", "|")) and not prev.strip().startswith("|") and len(prev.strip()) > 40 \
                    and not _SECTION_NUM.match(s) and not _NUMBERED.match(s) and not _NUMBERED.match(prev) and not _HEADING.match(prev) \
                    and not _META_KEY.match(s):
                out[-1] = prev.rstrip() + " " + s.lstrip()
                continue
        out.append(l)
    notes.append(f"pasted-document cleanup: {dropped} header/footer/page lines dropped, {len(kept) - len(out)} wrapped lines re-joined")
    return out


def canonicalise(text: str) -> Canonical:
    can = Canonical("")
    out: list[str] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ").split("\n")
    if lines and lines[0].startswith("\ufeff"):
        lines[0] = lines[0][1:]
    lines = _unwrap_pasted(lines, can.notes)
    seen_content = False
    section = ""
    i = 0
    table: list[list[str]] = []
    parent_stack: list[tuple[int, str]] = []   # (indent, bullet text) for nested bullets
    title_written = False
    story_actor_now = ""
    gwt: list[str] = []                        # Given/When/Then lines being collected
    in_actions = False

    def emit_section(canon: str) -> None:
        nonlocal section, in_actions
        section = canon
        in_actions = False
        out.append("")
        out.append("## " + canon)

    def flush_gwt() -> None:
        nonlocal gwt
        if gwt:
            parts = [g[0].upper() + g[1:] if n == 0 else g for n, g in enumerate(gwt)]
            sent = ", ".join(parts)
            out.append("- " + _resolve_i(sent, story_actor_now).rstrip(".") + ".")
            can.notes.append(f"Given/When/Then folded into one acceptance requirement: {sent[:50]}…")
            gwt = []

    def flush_table() -> None:
        nonlocal table
        rows = _merge_two_line_header(table)
        if _is_meta_table(rows):
            can.notes.append("front matter skipped: key/value table (" + ", ".join(r[0].strip() for r in rows[1:6] if r) + ")")
        elif len(rows) >= 2:
            out.extend(_table_to_bullets(rows, can.notes))
        elif rows:
            out.append("- " + "; ".join(c.strip() for c in rows[0] if c.strip()))
        table = []

    section_prio = ""
    while i < len(lines):
        raw = lines[i]
        line = _HTML_TAG.sub(" ", raw).rstrip()
        if _EMOJI.search(line):
            line = _EMOJI.sub("", line).rstrip()
        if re.match(r"^\s*>\s?", line):
            line = re.sub(r"^\s*>\s?", "", line)          # a callout/blockquote is prose
        line = re.sub(r"^(\s*(?:[-*+•]\s+)?)\*\*([^*]{1,30}[:：])\*\*\s*", r"\1\2 ", line)
        line = re.sub(r"^\s*(?:callout|note|tip|info|warning|important|hint|注意|補足|メモ)\s*[:：]\s*", "", line, flags=re.I)
        i += 1
        stripped = line.strip()
        if not stripped:
            pass
        # ---- tables
        if stripped.startswith("|") or (table and "|" in stripped and not stripped.startswith(("-", "*", "#"))):
            flush_gwt()
            if _SEPARATOR_ROW.match(stripped):
                continue
            table.append(_split_row(stripped))
            continue
        if table:
            flush_table()
        if not stripped:
            flush_gwt()
            out.append("")
            parent_stack.clear()
            continue
        if _PAGE_LINE.match(stripped) and seen_content:
            can.notes.append(f"page marker dropped: {stripped}")
            continue
        # ---- "X is excluded from this Contract", "for information only, not a requirement"
        if _EXCLUDED_INLINE.search(stripped) and (seen_content or _BULLET.match(line)):
            bm0 = _BULLET.match(line)
            body = bm0.group("body").strip() if bm0 else stripped
            body = _CLAUSE_NUM.sub("", body)
            if re.search(r"\bfor information only\b|\bnot a requirement\b", body, re.I) and len(body.split()) <= 14:
                section, in_actions = "Aside", False       # everything under it is reference material
                can.notes.append(f"reference-only section skipped: {body[:50]}")
                continue
            head = re.sub(r"^\s*#+\s*|^\s*\d+(?:\.\d+)*[.)]?\s*", "", stripped)
            if not bm0 and len(head.split()) <= 6 and not re.search(r"[。!?:]|\.(?!\s*$)", head.rstrip(".")) and not re.search(r"[.。]\s*$", head) or (_HEADING.match(line) and _section_of(head) == "Out of scope"):
                emit_section("Out of scope")                  # "## 8. Not in scope", "Follow-ups not in scope" are headings
                continue

            clauses = [c.strip() for c in re.split(r"(?<=[;。])\s*|;\s*", body) if c.strip()] or [body]
            excluded = [c for c in clauses if _EXCLUDED_INLINE.search(c)] or [body]
            kept = [c for c in clauses if not _EXCLUDED_INLINE.search(c) and c not in excluded]
            prev = section
            emit_section("Out of scope")
            out.extend("- " + c for c in excluded)
            out.append("")
            out.append("## " + (prev or "Requirements"))
            section = prev
            if kept:
                lines.insert(i, ("- " if _BULLET.match(line) else "") + " ".join(kept))
            can.notes.append(f"exclusion clause filed under out of scope: {excluded[0][:50]}")
            continue
        # ---- Given/When/Then lines (any indentation, no bullet needed)
        gm = _GWT.match(stripped)
        if gm and (gwt or gm.group(1).lower() in ("given", "when")) and not _BULLET.match(line):
            gwt.append(stripped[0].lower() + stripped[1:] if gwt else stripped)
            continue
        flush_gwt()
        # ---- systems affected: a constraint that names the existing systems
        sm2 = _SYSTEMS_AFFECTED.match(stripped)
        if sm2:
            names = [n.strip() for n in re.split(r"[,、;]\s*", sm2.group("body")) if n.strip()]
            out.append("")
            out.append("## Constraints")
            out.append("- The existing systems " + ", ".join(names) + " are changed, not replaced; integration with each of them is required.")
            out.append("")
            out.append("## " + (section or "Requirements"))
            can.notes.append(f"'systems affected' became a constraint naming {len(names)} existing systems")
            seen_content = True
            continue
        # ---- numbered section headings without '#': "2. 機能要件", "3.1 Performance", "5. Rollout"
        nm = _NUMBERED.match(line)
        if nm and not _BULLET.match(line) or (nm and _section_of(nm.group("title"))):
            title = nm.group("title").strip()
            canon = _section_of(title)
            if canon:
                if canon == "Aside" and title.strip().lower() in _ACTION_SECTION:
                    section, in_actions = "Aside", True
                    continue
                if canon in ("Must", "Should", "Could"):
                    section_prio = canon.lower()
                    emit_section("Requirements")
                    continue
                section_prio = ""
                if canon in ("Aside", "Alternatives"):
                    section, in_actions = canon, False
                    can.notes.append(f"section skipped (not requirements): {stripped[:40]}")
                    continue
                emit_section(canon)
                can.notes.append(f"heading without '#': {stripped[:40]} → {canon}")
                continue
            if len(title) <= 30 and not re.search(r"[a-z]{3,} [a-z]{3,} [a-z]{3,}", title):
                emit_section("Requirements")            # an unknown numbered heading resets the section
                out.append("### " + title)
                can.notes.append(f"heading without '#': {stripped[:40]} → (generic)")
                continue
        if nm and _BULLET.match(line) and len(nm.group("title").split()) <= 4 and not re.search(r"[.!?。:]", nm.group("title")) \
                and not _TEAM_COUNT.search(nm.group("title")) and re.match(r"^\s*\d+[.)]\s", line):
            nxt = next((l for l in lines[i:] if l.strip()), "")
            if not re.match(r"^\s*\d+[.)]\s", nxt) and not _section_of(nm.group("title")):
                emit_section("Requirements")
                out.append("### " + nm.group("title").strip())
                can.notes.append(f"heading without '#': {stripped[:40]} → (generic)")
                continue
        # ---- markdown headings
        hm = _HEADING.match(line)
        if hm:
            hashes, title = hm.groups()
            title = title.strip()
            st = _STORY.match(title)
            if st:
                out.append("")
                out.append(_story_sentence(st))
                story_actor_now = st.group("actor").strip()
                can.notes.append(f"user story in heading folded into a requirement: {title[:60]}")
                seen_content = True
                continue
            tk = _TICKET.match(title)
            if len(hashes) == 1 and tk and not title_written:
                out.append("# " + tk.group("rest").strip())
                title_written = True
                continue
            if tk and len(hashes) >= 2 and len(tk.group("rest").split()) >= 5 and not _section_of(tk.group("rest")):
                out.append("")
                out.append(f"- {tk.group('rest').strip()}")
                can.notes.append(f"ticket heading {tk.group('key')} folded into a requirement")
                seen_content = True
                continue
            canon = _section_of(title)
            if len(hashes) == 1 and not title_written:
                out.append("# " + title)
                title_written = True
                continue
            if canon == "Aside" and re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", title.lower().strip(":：")) in _ACTION_SECTION:
                section, in_actions = "Aside", True
                continue
            if canon in ("Alternatives", "Aside"):
                section, in_actions = canon, False
                continue
            if canon in ("Must", "Should", "Could"):
                section_prio = canon.lower()
                emit_section("Requirements")
            elif canon:
                section_prio = ""
                emit_section(canon)
            else:
                section_prio = ""
                emit_section("Requirements")
                if len(hashes) == 1 and title_written:
                    can.notes.append(f"second top-level heading read as a section: {title[:40]}")
                else:
                    out[-1] = f"{hashes} {title}"
                section = ""
            continue
        # ---- bare title line before any content; list-intro lines ("Acceptance criteria:")
        if not title_written and not seen_content and re.fullmatch(r"(?:提案依頼書|要件定義書|仕様書|設計書|基本設計書|詳細設計書|RFP|PRD|SOW|Spec|Specification|Design Doc(?:ument)?|Post-?mortem|Runbook)\s*(?:\(.*?\))?", stripped, re.I):
            can.notes.append(f"document-type line skipped as a title: {stripped}")
            continue
        tl = _TITLE_LINE.match(stripped) if not title_written and not seen_content else None
        if tl or (not seen_content and not title_written and len(stripped) <= 80 and not stripped.endswith(("。", ".", "!", "?"))
                  and not _META_KEY.match(stripped) and not _BULLET.match(line)):
            title = (tl.group("rest") if tl else stripped).strip()
            canon = _section_of(title)
            if canon:
                emit_section(canon)
                continue
            out.append("# " + re.sub(r"\s*(?:v\d+(?:\.\d+)*|\(案\)|\(draft\)|draft)\s*$", "", title, flags=re.I).strip())
            title_written = True
            continue
        if re.fullmatch(r"[^。.!?]{2,40}[:：]", stripped) and not _BULLET.match(line):
            canon = _section_of(stripped)
            if canon == "Aside" and stripped.lower().strip(":：") in _ACTION_SECTION:
                section, in_actions = "Aside", True
            elif canon in ("Alternatives", "Aside"):
                section, in_actions = canon, False
            elif canon:
                emit_section(canon)
            else:
                can.notes.append(f"list intro dropped: {stripped}")
            continue
        # a bare word/short line that is a section name ("Summary", "Stories", "Technical notes (from grooming)")
        if not _BULLET.match(line) and len(stripped) <= 90 and _section_of(stripped) and not stripped.endswith(("。", ".")):
            canon = _section_of(stripped)
            if canon == "Aside" and stripped.lower() in _ACTION_SECTION:
                section, in_actions = "Aside", True
            elif canon in ("Alternatives", "Aside"):
                section, in_actions = canon, False
            else:
                emit_section(canon)
            continue
        # ---- front matter / metadata
        if not seen_content and (_META_KEY.match(stripped) or _DATE_LINE.match(stripped) or stripped.startswith(("※", "Status:", "Labels:", "**Labels"))):
            can.notes.append(f"front matter skipped: {stripped[:50]}")
            continue
        if _META_KEY.match(stripped) and len(stripped) <= 80:
            can.notes.append(f"metadata line skipped: {stripped[:50]}")
            continue
        if re.fullmatch(r"(?:\*\*[^*]+:\*\*\s*[^*]+\s*){2,}", stripped) or (stripped.count("·") >= 1 and _META_INLINE.match(stripped) and len(stripped) < 120):
            can.notes.append(f"metadata line skipped: {stripped[:50]}")
            continue
        # ---- alternatives / actions / aside sections are not requirements
        if section == "Alternatives":
            bm = _BULLET.match(line)
            if bm:
                can.alternatives.append(bm.group("body").strip())
            continue
        if section == "Aside":
            if in_actions:
                bm = _BULLET.match(line)
                body = (bm.group("body") if bm else stripped).strip()
                if body and (re.match(r"^[A-Z][a-z]+\s*[:：]", body) or len(body.split()) <= 8 or "?" in body or "？" in body
                             or re.match(r"^(?:do|does|is|are|should|can|who|what|which|when|how|why)\b", body, re.I)):
                    can.todos.append(body)
                elif body:
                    out.append("- " + body)       # a full sentence in an action list is a requirement
            continue
        seen_content = True
        # ---- bullets
        bm = _BULLET.match(line)
        if bm:
            indent = len(bm.group("indent").expandtabs(4))
            body = bm.group("body").strip()
            hm2 = re.match(r"^#\s*(\d{1,6})\b\s*:?\s*", body)
            if hm2:
                body = f"N-{hm2.group(1)} " + body[hm2.end():].strip()       # "#101 Users can …": a ticket number, not a heading
            elif body.startswith("#"):
                body = body.lstrip("#").strip()
            cb = _CHECKBOX.match(body)
            if cb:
                body = body[cb.end():].strip()
                if cb.group(1) in ("x", "X", "✓"):
                    can.notes.append(f"checked item kept as a requirement (already done?): {body[:50]}")
            ip = _ID_PRIORITY.match(body)
            forced_prio = ""
            if ip:
                forced_prio = {"may": "could", "p0": "must", "p1": "must", "p2": "should", "p3": "could"}.get(ip.group("prio").lower(), ip.group("prio").lower())
                body = ip.group("id") + " " + body[ip.end():].strip()
            body = _OWNER_DUE.sub("", body).strip() if _OWNER_DUE.search(body) and len(_OWNER_DUE.sub("", body).strip()) > 20 else body
            forced_prio = forced_prio or section_prio
            if forced_prio and not _FORCED_TAIL.search(body):
                body = body.rstrip() + f" ({forced_prio})"
            om = _OUT_INLINE.match(body)
            if om:
                emit_section("Out of scope")
                for part in re.split(r"[、,;]\s*", om.group("body")):
                    if part.strip():
                        out.append("- " + part.strip())
                out.append("")
                out.append("## " + (section_before(out) or "Requirements"))
                section = section_before(out) or ""
                can.notes.append("inline 'out of scope:' became a section")
                continue
            dm = _DECIDED.match(body)
            if dm:
                body = dm.group("body").strip()
                prev = section
                emit_section("Constraints")
                out.append("- " + body)
                out.append("")
                out.append("## " + (prev or "Requirements"))
                section = prev
                can.notes.append(f"DECIDED: folded into constraints: {body[:50]}")
                continue
            tm = _TODO.match(body)
            if tm and (body.lower().startswith(("todo", "fixme")) or body.endswith("?")):
                can.todos.append(body[tm.end():].strip() or body)
                can.notes.append(f"TODO/question lifted out of the requirements: {body[:50]}")
                continue
            sm = _SPEAKER.match(body)
            if sm and sm.group("name").lower() not in _NOT_SPEAKERS:
                can.notes.append(f"speaker label dropped: {sm.group('name')}")
                lines.insert(i, " " * indent + "- " + sm.group("body").strip())
                continue
            st = _STORY.match(body)
            if st:
                body = _story_sentence(st).lstrip("- ").strip()
                story_actor_now = st.group("actor").strip()
            elif story_actor_now and re.search(r"\bI\b|\bmy\b", body):
                body = _resolve_i(body, story_actor_now)
            tk = _TICKET.match(body)
            if tk:
                body = tk.group("rest").strip()
            body = _team_line(body, can)
            if _TENTATIVE.search(body) and not re.search(r"\bmust\b|必須", body):
                can.tentative.append(body)
            while parent_stack and parent_stack[-1][0] >= indent:
                parent_stack.pop()
            if parent_stack and indent > parent_stack[-1][0]:
                can.notes.append(f"nested bullet under '{parent_stack[-1][1][:30]}…': {body[:40]}")
            parent_stack.append((indent, body))
            dl = _DEADLINE.search(body)
            if dl and not can.deadline:
                can.deadline = dl.group(0).strip()
            out.append(" " * indent + "- " + body)
            continue
        if _ID_PRIORITY.match(stripped) and not _BULLET.match(line):
            lines.insert(i, "- " + stripped)
            continue
        bold = re.fullmatch(r"\s*\*\*([^*]{2,60})\*\*\s*:?\s*", line)
        if bold and not _BULLET.match(line):
            emit_section("Requirements") if _section_of(bold.group(1)) is None and section in ("", "Background") else None
            out.append("### " + bold.group(1).strip())
            continue
        if not _BULLET.match(line) and len(stripped.split()) <= 5 and not re.search(r"[.。!?:：,]$", stripped) and not _META_KEY.match(stripped):
            nxt = next((l for l in lines[i:] if l.strip()), "")
            if _BULLET.match(nxt) and not _NUMBERED.match(stripped):
                canon = _section_of(stripped)
                if canon and canon not in ("Aside", "Alternatives", "Must", "Should", "Could"):
                    emit_section(canon)
                else:
                    out.append("### " + stripped)
                can.notes.append(f"short line before a list read as a sub-heading: {stripped}")
                continue
        # ---- user stories written as prose ("VOD-2211 As a viewer, I want …")
        if _STORY_PROSE.match(stripped):
            st = _STORY.match(re.sub(r"^\s*([A-Z][A-Z0-9]+-\d+)\s*[—–:-]?\s*", "", stripped))
            if st:
                out.append("")
                out.append(_story_sentence(st))
                story_actor_now = st.group("actor").strip()
                can.notes.append(f"user story folded into a requirement: {stripped[:60]}")
                continue
        # ---- section-numbered requirement lines: "2.1 checkout-api must accept …", "B.2.4 The Platform shall …"
        cm = _CLAUSE_NUM.match(stripped)
        if cm and not _NUMBERED.match(stripped):
            rid = cm.group(0).strip().rstrip(")")
            stripped = stripped[cm.end():]
            line = "- " + (f"{rid.replace('.', '-')} " if re.fullmatch(r"[A-Z]?\d+(?:\.\d+)+", rid) else "") + stripped
            can.notes.append(f"clause {rid} read as a requirement")
            lines.insert(i, line)
            continue
        if _SECTION_NUM.match(stripped):
            stripped = _SECTION_NUM.sub("", stripped, count=1)
            line = stripped
            can.notes.append(f"section number dropped from: {stripped[:40]}")
        # ---- labelled prose lines: "3.1 性能: 一覧検索は…" / "auth: Google SSO" / "Raj: feature store first. …"
        lm = _LABELLED.match(line)
        if lm and not stripped.startswith(("http", "www")):
            label, body = lm.group("label").strip(), lm.group("body").strip()
            dl = _DEADLINE.search(stripped)
            if dl and not can.deadline:
                can.deadline = dl.group(0).strip()
            om = _OUT_INLINE.match(stripped)
            if om:
                prev = section
                emit_section("Out of scope")
                for part in re.split(r"[、,;]\s*", om.group("body")):
                    if part.strip():
                        out.append("- " + part.strip())
                out.append("")
                out.append("## " + (prev or "Requirements"))
                section = prev
                continue
            dm = _DECIDED.match(stripped)
            if dm:
                prev = section
                emit_section("Constraints")
                out.append("- " + dm.group("body").strip())
                out.append("")
                out.append("## " + (prev or "Requirements"))
                section = prev
                continue
            if _TODO.match(stripped):
                can.todos.append(body)
                continue
            canon = _section_of(label)
            if canon and canon not in ("Background", "Aside"):
                emit_section(canon)
                out.append("- " + _team_line(body, can))
                continue
            bad_label = re.fullmatch(r"[\d\s.:：]+", label) or re.search(r"\d$", label) and re.match(r"\d", body) or re.match(r"\d{1,2}$", label)
            if len(label.split()) <= 3 and not bad_label:
                speaker = re.fullmatch(r"[A-Z][a-z]{1,15}", label) and label.lower() not in _NOT_SPEAKERS
                can.notes.append(f"{'speaker' if speaker else 'label'} '{label}' dropped from: {body[:40]}")
                lines.insert(i, body)       # the body goes through every branch again (out of scope:, DECIDED:, TODO …)
                continue
        if section == "Background":
            out.append(line)       # prose: summary, not a requirement (reported in the notes as read-not-designed)
            continue
        out.append(_team_line(stripped, can) if _TEAM_COUNT.search(line) and re.search(r"\bteam\b|チーム|体制", line, re.I) else line)   # indentation kept: a wrapped bullet continues on an indented line
    flush_gwt()
    if table:
        flush_table()
    can.text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    can.rationales = {k: v for k, v in _WHY.items() if k in can.text}
    _WHY.clear()
    return can


_FORCED_TAIL = re.compile(r"\((?:must|should|could)\)\s*$")
_NOT_SPEAKERS = {"auth", "team", "note", "goal", "cost", "todo", "api", "deploy", "data", "load", "scale", "target", "volume", "security",
                 "stack", "infra", "deadline", "owner", "status", "summary", "context", "scope", "risk", "risks", "actions", "decision", "decided",
                 "peak", "peaks", "latency", "throughput", "retention", "availability", "budget", "timeline", "impact", "severity", "date", "constraints",
                 "example", "examples", "input", "output", "inputs", "outputs", "reminder", "recap", "question", "answer", "result", "results", "rollout",
                 "migration", "monitoring", "alerting", "testing", "backup", "region", "regions", "phase", "step", "goal", "goals", "kpi", "kpis"}


def section_before(out: list[str]) -> str:
    """The section heading in force before the last emitted one (for returning after an inline fold)."""
    heads = [l[3:] for l in out[:-2] if l.startswith("## ")]
    for h in reversed(heads):
        if h not in ("Out of scope", "Constraints"):
            return h
    return heads[-1] if heads else ""


def _resolve_i(body: str, actor: str) -> str:
    if not actor:
        return body
    body = re.sub(r"\bI am\b", f"the {actor} is", body)
    body = re.sub(r"\bI ([a-z]+(?:-[a-z]+)*)\b", lambda m: f"the {actor} " + (m.group(1) if m.group(1) in _NO_S else _third_person(m.group(1))), body)
    body = re.sub(r"\bI\b", "the " + actor, body)
    body = re.sub(r"\bmy\b", "their", body)
    return body


def _team_line(body: str, can: Canonical) -> str:
    """'Team: 5 engineers, 1 SRE' / 'Team of 4 backend + 2 mobile' / 'team: Bo + Chen' -> a 'Team of N' the engine reads."""
    if re.search(r"\bteam of \d+\.", body, re.I):
        return body
    m = re.match(r"^(?:team|チーム|体制|members?|staffing)\s*(?:is|are|=|:|：)?\s*(?P<rest>.+)$", body, re.I) or re.search(r"\bteam of (?P<rest>\d+[^.。]*?\+[^.。]*)", body, re.I) \
        or re.search(r"\bteam\s*(?:is|=|:|：)\s*(?P<rest>\d[^.。]*)", body, re.I)
    if not m:
        return body
    rest = re.split(r"[.。;]", m.group("rest"))[0]
    rest = re.sub(r"\([^)]*\)", "", rest)
    # every "<n> <word>" pair is people, unless the word is a unit of time/size ("2 days a week", "40 %")
    pairs = re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:x\s*)?(?!(?:days?|weeks?|months?|years?|hours?|h|%|percent|fte|tb|gb|mb|k)\b)([A-Za-z][A-Za-z-]*)", rest)
    counts = [float(n) for n, w in pairs if w.lower() not in ("x", "of", "and", "plus", "or")] or [float(x) for x in _TEAM_COUNT.findall(rest)]
    if counts:
        n = int(-(-sum(counts) // 1))
        can.notes.append(f"team size {n} read from '{rest.strip()[:40]}'")
        return f"Team of {n}. " + body
    head = re.sub(r"\b(?:half|full|part)[- ]time\b|\(.*?\)", "", rest)
    names = [x.strip() for x in re.split(r"\s*(?:\+|,|、|/| and | & )\s*", head) if x.strip() and len(x.strip().split()) <= 2 and re.match(r"[A-Z][a-z]+", x.strip())]
    if len(names) >= 1 and all(re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+)?", x) for x in names):
        can.notes.append(f"team size {len(names)} read from the names")
        return f"Team of {len(names)} ({', '.join(names)}). " + body
    return body


_NO_S = {"can", "may", "must", "should", "will", "would", "could", "am", "have", "had", "was", "did", "do", "cannot", "need", "want", "get", "see"} - {"want", "get", "see", "need"}


def _third_person(v: str) -> str:
    if "-" in v:
        head, _, tail = v.rpartition("-")
        return head + "-" + _third_person(tail)
    if v.endswith(("s", "sh", "ch", "x", "z")):
        return v + "es"
    if v.endswith("y") and v[-2:-1] not in "aeiou":
        return v[:-1] + "ies"
    return v + "s"


#: requirement sentence -> the "so that …" of its user story (kept as rationale, not as text the engine reads)
_WHY: dict[str, str] = {}


_WANT_VERBS = {"be", "have", "get", "see", "know", "receive", "find", "use", "access", "understand", "share", "make", "keep", "avoid", "stop", "start", "mark", "track", "manage", "give", "let", "take", "put", "add", "remove"}


def _story_sentence(m: re.Match) -> str:
    from . import text as T
    actor = m.group("actor").strip()
    want = re.sub(r"\bmy\b", "their", re.sub(r"\bI\b", "they", m.group("want").strip().rstrip(".")))
    why = re.sub(r"\bmy\b", "their", re.sub(r"\bI\b", "they", (m.group("why") or "").strip().rstrip(".")))
    first = want.split()[0].lower() if want.split() else ""
    # "I want playback to adapt …", "I want clips to be geo-blocked …": the wish is about a thing, not an action
    if first and not T.verb_of(first) and first not in _WANT_VERBS and first not in ("to", "an", "a", "the"):
        om = re.match(r"^(?P<obj>[A-Za-z][\w' -]{0,50}?) to (?P<rest>.+)$", want)
        if om:
            actor_pl = actor if actor.endswith("s") else actor + "s"
            obj = om.group("obj").strip()
            s = f"- {obj[0].upper() + obj[1:]} must {om.group('rest').strip()} (for {actor_pl})"
            if why:
                _WHY[s[2:] + "."] = why
            return s + "."
    if first == "to":
        want = want[3:]
    actor_pl = actor if actor.endswith("s") else actor + "s"
    s = f"- {actor_pl.capitalize()} can {want}"
    if why:
        _WHY[f"{actor_pl.capitalize()} can {want}."] = why
    return s + "."


def story_actor(text: str) -> str:
    """The actor of the first user story in a text, for resolving 'I' in acceptance criteria."""
    m = _STORY.search(text)
    return m.group("actor").strip() if m else ""
