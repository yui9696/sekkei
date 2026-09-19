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
    ("Functional", ("functional", "features", "capabilities", "user stories", "stories", "use cases", "scope", "goals", "機能要件", "機能", "ユースケース", "ユーザーストーリー", "やりたいこと", "できること")),
    ("Requirements", ("requirements", "要件", "要求", "要求事項", "仕様")),
    ("Alternatives", ("alternatives", "alternatives considered", "options considered", "rejected alternatives", "代替案", "検討した代替案", "不採用案")),
    ("Background", ("motivation", "background", "context", "overview", "summary", "introduction", "problem", "why", "概要", "背景", "目的", "現状", "課題")),
    ("Aside", ("appendix", "references", "open questions", "questions", "risks", "glossary", "changelog", "history", "参考", "付録", "用語", "更新履歴", "備考", "検討事項")),
]
_SECTION_KEYS = {k: canon for canon, keys in SECTIONS for k in keys}

# a heading-like line: "2. 機能要件", "3.1 性能:", "II. Goals", "Requirements:" (short, no sentence punctuation)
_NUMBERED = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[IVX]+[.)]|[①-⑳])\s+(?P<title>[^。.!?]{1,40}?)\s*[:：]?\s*$")
_LABELLED = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?\s+)?(?P<label>[^:：。.]{1,24})\s*[:：]\s*(?P<body>\S.*)$")
_HEADING = re.compile(r"^\s*(#{1,6})\s*(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^(?P<indent>\s*)(?:[-*+•・●○■□▪◦]|\d+[.)．]|[①-⑳])\s+(?P<body>.*)$")
_CHECKBOX = re.compile(r"^\[( |x|X|✓)\]\s*")
_META_KEY = re.compile(r"^\s*\**(?:author|authors|status|owner|owners|reviewers?|date|created|updated|version|labels?|story points|epic|priority|tags?|present|attendees|作成|作成者|作成日|更新日|更新|版|ステータス|担当|承認|レビュー|出席|参加者)\**\s*[:：]", re.I)
_META_INLINE = re.compile(r"(?:\*\*[^*]{1,20}:\*\*|[A-Za-z ]{1,20}:)\s*[^·|]{1,40}(?:\s*[·|]\s*|$)")
_STORY = re.compile(r"^\s*(?:[A-Z]+-\d+\s*[—–-]\s*)?as an? (?P<actor>[a-z][a-z /-]{1,40}?),\s*i (?:want|need|would like)(?: to)?\s+(?P<want>.+?)(?:,?\s+so that\s+(?P<why>.+))?[.]?\s*$", re.I)
_TICKET = re.compile(r"^\s*(?P<key>[A-Z][A-Z0-9]+-\d+)\s*[—–:-]\s*(?P<rest>.+)$")
_TODO = re.compile(r"^\s*(?:todo|fixme|question|q|open question|要確認|未定|要検討|宿題)\b\s*[:：]?\s*", re.I)
_TENTATIVE = re.compile(r"\b(?:maybe|later maybe|perhaps|not sure|tbd|tbc|to be decided|to be confirmed)\b|\?\s*$|未定|検討中|かも", re.I)
_OUT_INLINE = re.compile(r"^\s*(?:out of scope|non-goal|non-goals|not in scope|対象外|スコープ外|やらないこと)\s*[:：]\s*(?P<body>.+)$", re.I)
_DECIDED = re.compile(r"^\s*(?:decided|decision|agreed|決定|確定)\s*[:：]\s*(?P<body>.+)$", re.I)
_SPEAKER = re.compile(r"^\s*(?P<name>[A-Z][a-z]{1,15})\s*:\s+(?P<body>[a-z].+)$")
_SEPARATOR_ROW = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_DEADLINE = re.compile(r"(?:\bMVP\b|\brelease\b|\bship\b|\blaunch\b|\bgo[- ]live\b|\bdeadline\b|\bdue\b|リリース|納期|稼働開始|ローンチ)[^.。]{0,30}?(?:\d{4}\s*年\s*\d{1,2}\s*月|\d{4}[/-]\d{1,2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{4}|q[1-4] \d{4}|\d+ (?:weeks?|months?|days?)|\d+\s*(?:週間|ヶ月|か月|日))|\b(?:in|within) \d+ (?:weeks?|months?)\b|\d{4}\s*年\s*\d{1,2}\s*月\s*(?:リリース|稼働|ローンチ)", re.I)
_DATE_LINE = re.compile(r"^\s*[^。.]{0,30}(?:\d{4}[/.-]\d{1,2}[/.-]\d{1,2}|\d{4}年\d{1,2}月)[^。.]{0,30}$")

PRIORITY_WORDS = {
    "must": ("must", "必須", "high", "m", "mandatory", "required", "p0", "p1", "高"),
    "should": ("should", "推奨", "medium", "s", "important", "p2", "中", "重要"),
    "could": ("could", "任意", "low", "c", "optional", "nice to have", "nice-to-have", "p3", "低", "あれば"),
}
_CONTENT_HEADERS = ("内容", "要件", "説明", "詳細", "requirement", "description", "content", "detail", "details", "story", "criteria", "acceptance", "text", "statement", "機能要件", "要求")
_PRIORITY_HEADERS = ("優先度", "優先", "priority", "moscow", "importance", "重要度", "必須")
_ID_HEADERS = ("no", "no.", "#", "id", "番号", "項番", "key", "req", "req id", "識別子")
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
        if len(k) >= 3 and (t.startswith(k + " ") or t.endswith(" " + k) or (not k.isascii() and k in t and len(t) <= len(k) + 6)):
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
        # the widest column is the content column
        widths = [sum(len(r[i]) for r in body if i < len(r)) for i in range(len(header))]
        ci = max(range(len(header)), key=lambda i: widths[i]) if header else 0
    pi = col(_PRIORITY_HEADERS)
    ii = col(_ID_HEADERS)
    ti = col(_TITLE_HEADERS)
    out = []
    for r in body:
        if ci >= len(r):
            continue
        content = r[ci].strip()
        if not content:
            continue
        rid = r[ii].strip() if ii is not None and ii < len(r) and ii != ci else ""
        prio = _priority_of(r[pi]) if pi is not None and pi < len(r) and pi != ci else ""
        title = r[ti].strip() if ti is not None and ti < len(r) and ti not in (ci, ii) else ""
        if title and title.lower() not in content.lower() and len(title) <= 20:
            content = f"{title}: {content}" if content[:1].isascii() else f"{title}: {content}"
        tail = ""
        if prio:
            tail = {"must": " (must)", "should": " (should)", "could": " (could)"}[prio]
        prefix = f"{rid} " if rid and re.fullmatch(r"[A-Za-z]{0,4}-?\d{1,4}", rid) else ""
        out.append(f"- {prefix}{content}{tail}")
    notes.append(f"table with columns {', '.join(rows[0])}: {len(out)} rows became requirements"
                 + (f" (priority from column '{rows[0][pi]}')" if pi is not None else ""))
    return out


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.replace("\\¦", "|") for c in re.split(r"(?<!\\)\|", s.replace("\\|", "\\¦"))]


def canonicalise(text: str) -> Canonical:
    can = Canonical("")
    out: list[str] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[0].startswith("﻿"):
        lines[0] = lines[0][1:]
    seen_heading = False
    seen_content = False
    section = ""
    i = 0
    table: list[list[str]] = []
    parent_stack: list[tuple[int, str]] = []   # (indent, bullet text) for nested bullets
    title_written = False
    story_actor_now = ""

    def flush_table() -> None:
        nonlocal table
        if len(table) >= 2:
            out.extend(_table_to_bullets(table, can.notes))
        elif table:
            out.append("- " + "; ".join(c.strip() for c in table[0] if c.strip()))
        table = []

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        i += 1
        stripped = line.strip()
        # ---- tables
        if stripped.startswith("|") or (table and "|" in stripped and not stripped.startswith(("-", "*", "#"))):
            if _SEPARATOR_ROW.match(stripped):
                continue
            table.append(_split_row(stripped))
            continue
        if table:
            flush_table()
        if not stripped:
            out.append("")
            parent_stack.clear()
            continue
        # ---- numbered section headings without '#': "2. 機能要件", "3.1 Performance"
        nm = _NUMBERED.match(line)
        if nm and _section_of(nm.group("title")):
            canon = _section_of(nm.group("title"))
            section = canon
            out.append("")
            out.append("## " + canon)
            can.notes.append(f"heading without '#': {stripped[:40]} → {canon}")
            seen_heading = True
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
                seen_heading = seen_content = True
                continue
            tk = _TICKET.match(title)
            if len(hashes) == 1 and tk and not title_written:
                out.append("# " + tk.group("rest").strip())
                title_written = seen_heading = True
                continue
            if tk and len(hashes) >= 2 and len(tk.group("rest").split()) >= 5 and not _section_of(tk.group("rest")):
                out.append("")
                out.append(f"- {tk.group('rest').strip()}")
                can.notes.append(f"ticket heading {tk.group('key')} folded into a requirement")
                seen_heading = seen_content = True
                continue
            canon = _section_of(title)
            if len(hashes) == 1 and not title_written:
                out.append("# " + title)
                title_written = True
                seen_heading = True
                continue
            section = canon or ""
            if canon in ("Alternatives", "Aside"):
                seen_heading = True
                continue
            out.append(("## " + canon) if canon else f"{hashes} {title}")
            seen_heading = True
            continue
        # ---- bare title line before any content; list-intro lines ("Acceptance criteria:")
        if not seen_content and not title_written and len(stripped) <= 60 and not stripped.endswith(("。", ".", "!", "?")) \
                and not _META_KEY.match(stripped) and not _BULLET.match(line):
            title = stripped
            canon = _section_of(title)
            if canon:
                section = canon
                out.append("")
                out.append("## " + canon)
                seen_heading = True
                continue
            out.append("# " + re.sub(r"\s*(?:v\d+(?:\.\d+)*|\(案\)|\(draft\)|draft)\s*$", "", title, flags=re.I).strip())
            title_written = True
            seen_heading = True
            continue
        if re.fullmatch(r"[^。.!?]{2,40}[:：]", stripped) and not _BULLET.match(line):
            canon = _section_of(stripped)
            if canon:
                section = canon
                out.append("")
                out.append("## " + canon)
            else:
                can.notes.append(f"list intro dropped: {stripped}")
            continue
        if nm and not _BULLET.match(line) and len(nm.group("title")) <= 30 and not re.search(r"[a-z]{3,} [a-z]{3,} [a-z]{3,}", nm.group("title")):
            out.append("")
            out.append("### " + nm.group("title").strip())
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
        # ---- alternatives / aside sections are not requirements
        if section == "Alternatives":
            bm = _BULLET.match(line)
            if bm:
                can.alternatives.append(bm.group("body").strip())
            continue
        if section == "Aside":
            continue
        seen_content = True
        # ---- bullets
        bm = _BULLET.match(line)
        if bm:
            indent = len(bm.group("indent").expandtabs(4))
            body = bm.group("body").strip()
            cb = _CHECKBOX.match(body)
            if cb:
                body = body[cb.end():].strip()
                if cb.group(1) in ("x", "X", "✓"):
                    can.notes.append(f"checked item kept as a requirement (already done?): {body[:50]}")
            om = _OUT_INLINE.match(body)
            if om:
                out.append("")
                out.append("## Out of scope")
                for part in re.split(r"[、,;]\s*", om.group("body")):
                    if part.strip():
                        out.append("- " + part.strip())
                out.append("")
                out.append("## " + (section or "Requirements"))
                can.notes.append("inline 'out of scope:' became a section")
                continue
            dm = _DECIDED.match(body)
            if dm:
                body = dm.group("body").strip()
                out.append("")
                out.append("## Constraints")
                out.append("- " + body)
                out.append("")
                out.append("## " + (section or "Requirements"))
                can.notes.append(f"DECIDED: folded into constraints: {body[:50]}")
                continue
            tm = _TODO.match(body)
            if tm and (body.lower().startswith(("todo", "fixme")) or body.endswith("?")):
                can.todos.append(body[tm.end():].strip() or body)
                can.notes.append(f"TODO/question lifted out of the requirements: {body[:50]}")
                continue
            sm = _SPEAKER.match(body)
            if sm and sm.group("name").lower() not in ("auth", "team", "note", "goal", "cost", "todo", "api", "deploy", "data"):
                body = sm.group("body").strip()
                can.notes.append(f"speaker label dropped: {sm.group('name')}")
            st = _STORY.match(body)
            if st:
                body = _story_sentence(st).lstrip("- ").strip()
                story_actor_now = st.group("actor").strip()
            elif story_actor_now and re.search(r"\bI\b|\bmy\b", body):
                body = re.sub(r"\bI ([a-z]+(?:-[a-z]+)*)\b", lambda m: f"the {story_actor_now} " + (m.group(1) if m.group(1) in _NO_S else _third_person(m.group(1))), body)
                body = re.sub(r"\bI\b", "the " + story_actor_now, body)
                body = re.sub(r"\bmy\b", "their", body)
            tk = _TICKET.match(body)
            if tk:
                body = tk.group("rest").strip()
            tm2 = re.match(r"^(?:team|チーム|体制|members?)\s*[:：]\s*(?P<names>.+)$", body, re.I)
            if tm2 and not re.search(r"\bteam of \d|\d\s*(?:名|人)", body):
                head = re.sub(r"\b(?:half|full|part)[- ]time\b|\(.*?\)", "", re.split(r"[.。;]", tm2.group("names"))[0])
                names = [n.strip() for n in re.split(r"\s*(?:\+|,|、|/| and | & )\s*", head) if n.strip() and len(n.strip().split()) <= 2]
                if names:
                    body = f"Team of {len(names)} ({', '.join(n.strip() for n in names)}). " + body
                    can.notes.append(f"team size {len(names)} read from the names")
            if _TENTATIVE.search(body) and not re.search(r"\bmust\b|必須", body):
                can.tentative.append(body)
            # nested bullets: keep them as their own requirement but remember the parent for the notes
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
        # ---- labelled prose lines: "3.1 性能: 一覧検索は…" / "auth: Google SSO"
        lm = _LABELLED.match(line)
        if lm and not stripped.startswith(("http", "www")):
            label, body = lm.group("label").strip(), lm.group("body").strip()
            dl = _DEADLINE.search(stripped)
            if dl and not can.deadline:
                can.deadline = dl.group(0).strip()
            om = _OUT_INLINE.match(stripped)
            if om:
                out.append("")
                out.append("## Out of scope")
                for part in re.split(r"[、,;]\s*", om.group("body")):
                    if part.strip():
                        out.append("- " + part.strip())
                out.append("")
                out.append("## " + (section or "Requirements"))
                continue
            dm = _DECIDED.match(stripped)
            if dm:
                out.append("- " + dm.group("body").strip())
                continue
            if _TODO.match(stripped):
                can.todos.append(body)
                continue
            canon = _section_of(label)
            if canon and canon not in ("Background", "Aside"):
                section = canon
                out.append("")
                out.append("## " + canon)
                out.append("- " + body)
                continue
            if len(label.split()) <= 3 and not re.fullmatch(r"[\d\s.:：]+", label) and not re.match(r"\d{1,2}$", label):
                out.append("- " + body)
                can.notes.append(f"label '{label}' dropped from: {body[:40]}")
                continue
        if section == "Background":
            out.append(line)       # prose: summary, not a requirement
            continue
        out.append(line)           # indentation kept: a wrapped bullet continues on an indented line
    if table:
        flush_table()
    can.text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    can.rationales = {k: v for k, v in _WHY.items() if k in can.text}
    _WHY.clear()
    return can


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


def _story_sentence(m: re.Match) -> str:
    actor = m.group("actor").strip()
    want = re.sub(r"\bmy\b", "their", re.sub(r"\bI\b", "they", m.group("want").strip().rstrip(".")))
    why = re.sub(r"\bmy\b", "their", re.sub(r"\bI\b", "they", (m.group("why") or "").strip().rstrip(".")))
    actor_pl = actor if actor.endswith("s") else actor + "s"
    s = f"- {actor_pl.capitalize()} can {want}"
    if why:
        _WHY[f"{actor_pl.capitalize()} can {want}."] = why
    return s + "."


def story_actor(text: str) -> str:
    """The actor of the first user story in a text, for resolving 'I' in acceptance criteria."""
    m = _STORY.search(text)
    return m.group("actor").strip() if m else ""
