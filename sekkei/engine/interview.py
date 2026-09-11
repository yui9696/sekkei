"""Designing in dialogue: the engine asks one thing at a time and the answers become requirements.

``Interview`` is driven by ``pending()`` / ``reply()`` so it is testable without a terminal;
``run_cli`` wraps it in a read-eval loop. The transcript is the requirements file: every
answer is normalised into a canonical bullet under an ``## … (interview)`` section, so the
design is reproducible from the text alone.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Optional

from ..model import dump
from ..render import render_markdown
from . import Overrides, design
from .analysis import analyse
from .answers import answer as answer_rule
from .gaps import Question, questions
from .text import analyse_sentence, segment

TOPIC_ORDER = ["requirements", "stack", "people", "load", "quality", "data", "security", "resilience", "operations", "compliance", "cost"]
STATE_DIR = ".sekkei"
STATE_FILE = "interview.json"


@dataclass
class Prompt:
    kind: str            # placement | question | decision
    key: str             # statement | question id | decision key
    text: str            # what to ask
    proposal: str        # the engine's proposal (Enter accepts)
    why: str = ""
    options: list[str] = field(default_factory=list)

    def render(self) -> str:
        s = [f"[{self.kind}] {self.text}"]
        if self.why:
            s.append(f"  why: {self.why}")
        for i, o in enumerate(self.options, 1):
            s.append(f"  {i}. {o}")
        s.append(f"  proposal: {self.proposal}")
        s.append("  > (Enter = accept, type an answer, 'skip', or /help)")
        return "\n".join(s)


# ---------------------------------------------------------------------------
# Canonical bullets from free-form answers
# ---------------------------------------------------------------------------

_SECTION = {"functional": "Functional", "nonfunctional": "Non-functional", "constraint": "Constraints"}


def _num(raw: str) -> str:
    m = re.search(r"\d[\d,\.]*", raw)
    return m.group(0) if m else ""


def _int(raw: str) -> str:
    m = re.search(r"\d+", raw)
    return m.group(0) if m else ""


NOOP_REPLIES = {"skip", "y", "yes", "ok", "accept", "n", "no"}


def looks_like_requirement(text: str, prompt: Optional["Prompt"]) -> bool:
    """A long sentence with a subject and a verb typed at a question prompt is a requirement, not an answer."""
    if prompt is not None and prompt.kind == "decision":
        return False
    sent = analyse_sentence(0, text, "", False)
    return len(sent.words) >= 6 and bool(sent.actors or sent.verbs)


def canonical_bullet(qid: str, raw: str) -> tuple[str, str]:
    """(section, bullet) for a human answer to question ``qid``."""
    r = raw.strip().rstrip(".")
    low = r.lower()
    if qid == "Q-lang":
        return "constraint", f"{r}."
    if qid == "Q-store":
        return "constraint", f"{r} available." if "available" not in low else f"{r}."
    if qid == "Q-deploy":
        return "constraint", f"Deployed as {r}." if not low.startswith("deploy") else f"{r}."
    if qid == "Q-team":
        n = _int(r)
        return "constraint", f"Team of {n}." if n else f"Team: {r}."
    if qid == "Q-rate":
        return "nonfunctional", f"The system sustains {r}." if not low.startswith("the system") else f"{r}."
    if qid == "Q-volume":
        return "nonfunctional", f"The system holds {r}." if not low.startswith("the system") else f"{r}."
    if qid == "Q-payload":
        return "nonfunctional", f"Records are {r} on average." if _num(r) else f"Record size: {r}."
    if qid == "Q-latency":
        return "nonfunctional", f"Operations complete within {r} p95." if "p9" not in low and "p5" not in low else f"Operations complete {r}."
    if qid == "Q-availability":
        return "nonfunctional", f"Availability of {r} monthly." if "availab" not in low else f"{r}."
    if qid == "Q-retention":
        return "functional", f"Records are retained for {r}." if "retain" not in low and "retention" not in low else f"{r}."
    if qid == "Q-backup":
        return "nonfunctional", f"Backups: {r}."
    if qid == "Q-migration":
        return "constraint", f"Migration: {r}."
    if qid == "Q-auth":
        return "constraint", f"Authentication via {r}." if "authenticat" not in low else f"{r}."
    if qid == "Q-authz":
        return "functional", f"Authorization: {r}."
    if qid == "Q-external":
        return "nonfunctional", f"External calls: {r}."
    if qid == "Q-compliance":
        return "functional", f"Compliance: {r}."
    if qid == "Q-alerting":
        return "nonfunctional", f"Alerting: {r}."
    if qid == "Q-budget":
        return "constraint", f"Budget: {r}."
    return "functional", f"{r}."


def classify_free_text(text: str) -> list[tuple[str, str]]:
    """Free sentences from the human -> (section, bullet), one requirement per sentence."""
    from .analysis import _kind, _sentence_qualities  # heuristics shared with file analysis

    out: list[tuple[str, str]] = []
    for s in segment(text):
        if s.section == "nongoal":
            continue
        sec = s.section or _kind(s, _sentence_qualities(s))
        if sec not in _SECTION:
            sec = "functional"
        out.append((sec, s.text if s.text.endswith((".", "!", "?")) else s.text + "."))
    return out


# ---------------------------------------------------------------------------
# The interview
# ---------------------------------------------------------------------------


class Interview:
    def __init__(self, base: str = ""):
        self.base = base.rstrip() + ("\n" if base.strip() else "")
        self.bullets: dict[str, list[str]] = {"functional": [], "nonfunctional": [], "constraint": []}
        self.answers: dict[str, str] = {}        # question id -> bullet text
        self.owners: dict[str, str] = {}         # statement -> component name
        self.decisions: dict[str, str] = {}      # decision key -> option name
        self.confirmed: set[str] = set()         # statements whose placement was accepted
        self.skipped: set[str] = set()           # question ids / decision keys left open
        self._history: list[str] = []

    # -- state ---------------------------------------------------------------

    def to_state(self) -> dict[str, Any]:
        return {"base": self.base, "bullets": self.bullets, "answers": self.answers, "owners": self.owners,
                "decisions": self.decisions, "confirmed": sorted(self.confirmed), "skipped": sorted(self.skipped)}

    @classmethod
    def from_state(cls, st: dict[str, Any]) -> "Interview":
        iv = cls(st.get("base", ""))
        iv.bullets = {k: list(v) for k, v in st.get("bullets", {}).items()} or iv.bullets
        for k in ("functional", "nonfunctional", "constraint"):
            iv.bullets.setdefault(k, [])
        iv.answers = dict(st.get("answers", {}))
        iv.owners = dict(st.get("owners", {}))
        iv.decisions = dict(st.get("decisions", {}))
        iv.confirmed = set(st.get("confirmed", []))
        iv.skipped = set(st.get("skipped", []))
        return iv

    def _snapshot(self) -> None:
        self._history.append(json.dumps(self.to_state(), sort_keys=True))

    def undo(self) -> bool:
        if not self._history:
            return False
        st = json.loads(self._history.pop())
        other = Interview.from_state(st)
        self.__dict__.update({k: v for k, v in other.__dict__.items() if k != "_history"})
        return True

    # -- the requirements text -------------------------------------------------

    def text(self) -> str:
        parts = [self.base.rstrip()] if self.base.strip() else ["# Interview"]
        for sec in ("functional", "nonfunctional", "constraint"):
            if self.bullets[sec]:
                parts.append(f"\n## {_SECTION[sec]} (interview)")
                parts += [f"- {b}" for b in self.bullets[sec]]
        return "\n".join(parts).rstrip() + "\n"

    def add(self, text: str) -> int:
        """Add free-form requirements; returns how many bullets were created."""
        self._snapshot()
        items = classify_free_text(text)
        for sec, bullet in items:
            if bullet not in self.bullets[sec]:
                self.bullets[sec].append(bullet)
        return len(items)

    # -- engine ---------------------------------------------------------------

    def overrides(self) -> Overrides:
        return Overrides(dict(self.owners), dict(self.decisions))

    def result(self):
        key = (self.text(), json.dumps(self.owners, sort_keys=True), json.dumps(self.decisions, sort_keys=True))
        cached = getattr(self, "_cache", None)
        if cached and cached[0] == key:
            return cached[1]
        res = design(self.text(), assume=True, overrides=self.overrides())
        self._cache = (key, res)
        return res

    def has_requirements(self) -> bool:
        return any(self.bullets.values()) or bool(analyse(self.base).requirements)

    def pending(self) -> list[Prompt]:
        """Prompts in the order an architect asks: placements, then questions by topic, then close decisions."""
        if not self.has_requirements():
            return []
        r = self.result()
        out: list[Prompt] = []
        by_id = {q.id: q for q in r.design.requirements}
        for p in r.placements:
            stmt = by_id[p.requirement].statement
            if stmt in self.confirmed or stmt in self.owners or "assumed by the engine" in stmt:
                continue
            owners = ", ".join(f"{o} {r.design.component(o).name}" for o in p.owners if r.design.component(o))
            out.append(Prompt("placement", stmt, f"{p.requirement} \"{stmt}\" matched no catalogue pattern. Who owns it?",
                              f"{owners} ({p.how}: {p.detail})", "A wrong owner misleads the brief of that component.",
                              [c.name for c in r.design.components if c.kind != "external"]))
        an = analyse(self.text())
        qs = [q for q in questions(an) if q.id not in self.answers and q.id not in self.skipped]
        qs.sort(key=lambda q: (TOPIC_ORDER.index(q.topic) if q.topic in TOPIC_ORDER else 99))
        for q in qs:
            a = answer_rule(q, an)
            proposal = (a.answer + (f" (evidence: {a.evidence})" if a and a.evidence else " (default)")) if a else q.assumption
            out.append(Prompt("question", q.id, q.question, proposal, q.why))
        for did, key, title, top in r.close_calls:
            if key in self.decisions or key in self.skipped:
                continue
            out.append(Prompt("decision", key, f"{did} {title}: the top two options score within {abs(top[0][1] - top[1][1]):.2f} of each other. Which one?",
                              f"1. {top[0][0]} ({top[0][1]:.2f})", "", [f"{o} ({s:.2f})" for o, s in top]))
        return out

    def reply(self, prompt: Prompt, text: str) -> str:
        """Apply the human's reply; returns a one-line acknowledgement."""
        self._snapshot()
        t = text.strip()
        low = t.lower()
        if prompt.kind == "placement":
            if low in ("", "y", "yes", "ok", "accept", "skip"):
                self.confirmed.add(prompt.key)
                return "owner confirmed"
            self.owners[prompt.key] = t
            return f"owner set to {t!r}"
        if prompt.kind == "question":
            if low == "skip":
                self.skipped.add(prompt.key)
                return "left open (the engine's assumption applies, marked as such)"
            an = analyse(self.text())
            q = next((q for q in questions(an) if q.id == prompt.key), None)
            if low in ("", "y", "yes", "ok", "accept") and q is not None:
                a = answer_rule(q, an)
                if a is None:
                    self.skipped.add(prompt.key)
                    return "no proposal to accept; left open"
                for sec, bullet in a.bullets:
                    b = bullet.replace(" (assumed by the engine)", " (confirmed in the interview)")
                    if b not in self.bullets[sec]:
                        self.bullets[sec].append(b)
                self.answers[prompt.key] = a.answer
                return f"accepted: {a.answer}"
            sec, bullet = canonical_bullet(prompt.key, t)
            if bullet not in self.bullets[sec]:
                self.bullets[sec].append(bullet)
            self.answers[prompt.key] = bullet
            return f"recorded under {_SECTION[sec]}: {bullet}"
        if prompt.kind == "decision":
            if low == "skip":
                self.skipped.add(prompt.key)
                return "left to the engine's scoring"
            options = [o.rsplit(" (", 1)[0] for o in prompt.options]
            if low in ("", "1", "y", "yes", "ok", "accept"):
                self.decisions[prompt.key] = options[0]
            elif low.isdigit() and 1 <= int(low) <= len(options):
                self.decisions[prompt.key] = options[int(low) - 1]
            else:
                self.decisions[prompt.key] = t
            return f"decision fixed: {self.decisions[prompt.key]}"
        return "?"

    def status(self) -> str:
        if not self.has_requirements():
            return "no requirements yet — describe the system in a few sentences"
        r = self.result()
        pend = self.pending()
        kinds = {k: sum(1 for p in pend if p.kind == k) for k in ("placement", "question", "decision")}
        return (f"{len(r.design.requirements)} requirements · {len(r.design.components)} components · "
                f"{len(r.design.decisions)} decisions · {len(r.design.work_packages)} packages · "
                f"to confirm: {kinds['placement']} placement(s), {kinds['question']} question(s), {kinds['decision']} close decision(s)"
                + (" · lint OK" if r.ok else " · LINT ERRORS"))

    def write_outputs(self, out_dir: Path, name: str = "design") -> list[Path]:
        r = self.result()
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        p = out_dir / f"{name}.json"; dump(r.design, p); paths.append(p)
        p = out_dir / "DESIGN.md"; p.write_text(render_markdown(r.design), encoding="utf-8"); paths.append(p)
        p = out_dir / "NOTES.md"; p.write_text(r.notes.to_markdown(), encoding="utf-8"); paths.append(p)
        p = out_dir / "requirements.md"; p.write_text(self.text(), encoding="utf-8"); paths.append(p)
        return paths


# ---------------------------------------------------------------------------
# Read-eval loop
# ---------------------------------------------------------------------------

HELP = """\
Describe the system in sentences (English; one requirement per sentence). Press Enter on an
empty line to start the questions. Answer a prompt with Enter (accept the proposal), your own
answer, or 'skip'. A long sentence typed at a question is taken as a new requirement.
Commands: /add <text>  /status  /pending  /design  /undo  /done  /help"""

WELCOME = """\
sekkei interview — describe the system in a few sentences and I will design it, asking one
thing at a time where the text is silent. Requirements must be in English (the analyser's
vocabulary). Type /help for commands."""


def load_state(root: Path) -> Optional[dict[str, Any]]:
    p = root / STATE_DIR / STATE_FILE
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def save_state(root: Path, iv: Interview) -> None:
    p = root / STATE_DIR / STATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(iv.to_state(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_cli(inp: IO[str], out: IO[str], root: Path, base_file: Optional[Path] = None, out_dir: Optional[Path] = None) -> int:
    st = load_state(root)
    if st is not None:
        iv = Interview.from_state(st)
        out.write("resumed the previous interview\n")
    else:
        iv = Interview(base_file.read_text(encoding="utf-8") if base_file and base_file.exists() else "")
    out_dir = out_dir or root
    out.write(WELCOME + "\n")
    current: Optional[Prompt] = None
    mode = "describe"   # describe: every line is a requirement; ask: the engine asks, the human answers
    while True:
        if mode == "describe":
            out.write("status: " + iv.status() + "\n")
            out.write("describe: type sentences; press Enter on an empty line to start the questions\n")
        elif current is None:
            pend = iv.pending()
            out.write("status: " + iv.status() + "\n")
            if pend:
                current = pend[0]
                out.write(current.render() + "\n")
            else:
                out.write("nothing to confirm. Add sentences, /design to write the outputs, /done to finish.\n")
        out.write("> ")
        out.flush()
        line = inp.readline()
        if not line:
            break
        line = line.rstrip("\n")
        cmd = line.strip()
        if cmd.startswith("/"):
            name, _, arg = cmd.partition(" ")
            if name == "/help":
                out.write(HELP + "\n")
            elif name == "/status":
                out.write(iv.status() + "\n")
            elif name == "/pending":
                for p in iv.pending():
                    out.write(f"- [{p.kind}] {p.text}\n")
            elif name == "/add":
                n = iv.add(arg)
                out.write(f"added {n} requirement(s)\n")
                current = None
            elif name == "/design":
                for p in iv.write_outputs(out_dir):
                    out.write(f"wrote {p}\n")
            elif name == "/undo":
                out.write("undone\n" if iv.undo() else "nothing to undo\n")
                current = None
            elif name == "/done":
                break
            else:
                out.write("unknown command; /help\n")
            save_state(root, iv)
            continue
        if mode == "describe":
            if cmd == "":
                mode = "ask"
            elif cmd.lower() in NOOP_REPLIES:
                pass
            else:
                out.write(f"added {iv.add(cmd)} requirement(s)\n")
            save_state(root, iv)
            continue
        if current is None:
            if cmd and cmd.lower() not in NOOP_REPLIES:
                out.write(f"added {iv.add(cmd)} requirement(s)\n")
        elif looks_like_requirement(cmd, current):
            out.write(f"that reads as a requirement; added {iv.add(cmd)} and I will ask again\n")
            current = None
        else:
            out.write(iv.reply(current, line) + "\n")
            current = None
        save_state(root, iv)
    if iv.has_requirements():
        for p in iv.write_outputs(out_dir):
            out.write(f"wrote {p}\n")
        out.write("final: " + iv.status() + "\n")
    save_state(root, iv)
    return 0
