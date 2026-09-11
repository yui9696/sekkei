"""Progress state and completion-report acceptance: the loop's memory.

``.sekkei/state.json`` maps work-package id -> {status, updated, report}. ``accept``
validates an agent's completion report against the design before marking a package
done, so the state can only advance on evidence.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import graph as G
from .model import PACKAGE_STATUSES, Design

STATE_DIR = ".sekkei"
STATE_FILE = "state.json"


class State:
    def __init__(self, path: Path, data: Optional[dict[str, Any]] = None):
        self.path = path
        self.data: dict[str, Any] = data or {"packages": {}}

    @classmethod
    def load(cls, root: str | Path) -> "State":
        p = Path(root) / STATE_DIR / STATE_FILE
        if p.exists():
            return cls(p, json.loads(p.read_text(encoding="utf-8")))
        return cls(p)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # -- queries ------------------------------------------------------------

    def status(self, wp_id: str) -> str:
        return self.data["packages"].get(wp_id, {}).get("status", "todo")

    def done(self) -> set[str]:
        return {w for w, e in self.data["packages"].items() if e.get("status") == "done"}

    def entry(self, wp_id: str) -> dict[str, Any]:
        return self.data["packages"].get(wp_id, {"status": "todo"})

    # -- updates ------------------------------------------------------------

    def set_status(self, wp_id: str, status: str, report: Optional[dict[str, Any]] = None) -> None:
        if status not in PACKAGE_STATUSES:
            raise ValueError(f"unknown status {status!r}; use one of {PACKAGE_STATUSES}")
        entry = self.data["packages"].setdefault(wp_id, {})
        entry["status"] = status
        entry["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if report is not None:
            entry["report"] = report

    def record_brief(self, wp_id: str, fingerprint: str) -> None:
        """Remember the fingerprint of the brief that was issued for a package."""
        entry = self.data["packages"].setdefault(wp_id, {"status": "todo"})
        entry["brief_fingerprint"] = fingerprint
        entry["briefed"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def is_stale(self, wp_id: str, current_fingerprint: Optional[str]) -> bool:
        """True if a brief was issued for the package and the design has changed since."""
        recorded = self.data["packages"].get(wp_id, {}).get("brief_fingerprint")
        return bool(recorded) and current_fingerprint is not None and recorded != current_fingerprint


REPORT_KEYS = ("work_package", "files_touched", "checks", "deviations", "proposed_decisions", "notes")


def report_template(design: Design, wp_id: str) -> dict[str, Any]:
    wp = design.work_package(wp_id)
    if wp is None:
        raise KeyError(wp_id)
    return {
        "work_package": wp.id,
        "files_touched": [],
        "checks": [{"id": a.id, "passed": False, "output": ""} for a in wp.acceptance],
        "deviations": [],
        "proposed_decisions": [],
        "notes": "",
    }


def validate_report(design: Design, report: dict[str, Any]) -> list[str]:
    """Return the list of reasons the report cannot be accepted (empty = acceptable)."""
    problems: list[str] = []
    if not isinstance(report, dict):
        return ["report must be a JSON object"]
    wp_id = report.get("work_package")
    wp = design.work_package(wp_id) if isinstance(wp_id, str) else None
    if wp is None:
        return [f"work_package {wp_id!r} is not in the design"]
    for key in REPORT_KEYS:
        if key not in report:
            problems.append(f"missing key {key!r}")
    checks = report.get("checks") or []
    if not isinstance(checks, list):
        problems.append("checks must be a list")
        checks = []
    reported = {c.get("id"): c for c in checks if isinstance(c, dict)}
    for a in wp.acceptance:
        c = reported.get(a.id)
        if c is None:
            problems.append(f"acceptance {a.id} is not reported")
        elif c.get("passed") is not True:
            problems.append(f"acceptance {a.id} did not pass")
    for cid in reported:
        if cid not in {a.id for a in wp.acceptance}:
            problems.append(f"check {cid!r} is not an acceptance check of {wp.id}")
    files = report.get("files_touched") or []
    if not isinstance(files, list):
        problems.append("files_touched must be a list")
        files = []
    for f in files:
        if not isinstance(f, str) or not any(G.in_scope(f, s) for s in wp.files):
            problems.append(f"file {f!r} is outside the package's write scope {wp.files}")
    deviations = report.get("deviations") or []
    if deviations and not isinstance(deviations, list):
        problems.append("deviations must be a list")
    return problems


def accept(
    design: Design,
    state: State,
    report: dict[str, Any],
    fingerprint: Optional[str] = None,
    force: bool = False,
) -> list[str]:
    """Validate the report; on success mark the package done and save. Returns problems.

    ``fingerprint`` is the current brief fingerprint (``sekkei.brief.brief_fingerprint``);
    if a different one was recorded when the brief was issued, the report is rejected as
    stale unless ``force``.
    """
    problems = validate_report(design, report)
    if not problems and not force and state.is_stale(report["work_package"], fingerprint):
        problems.append(
            f"brief for {report['work_package']} is stale: the design changed after the brief was issued "
            "(re-issue the brief, or accept --force)"
        )
    if problems:
        return problems
    state.set_status(report["work_package"], "done", report)
    state.save()
    return []


def next_packages(design: Design, state: State) -> list[str]:
    return G.ready_packages(design, state.done())


def status_table(design: Design, state: State, fingerprints: Optional[dict[str, str]] = None) -> str:
    """Markdown table; ``fingerprints`` (package -> current brief fingerprint) marks stale briefs."""
    done = state.done()
    ready = set(G.ready_packages(design, done))
    lines = ["| package | status | title |", "|---|---|---|"]
    for w in design.work_packages:
        st = state.status(w.id)
        if st == "todo" and w.id in ready:
            st = "ready"
        if fingerprints and state.is_stale(w.id, fingerprints.get(w.id)):
            st += " (stale brief)"
        lines.append(f"| {w.id} | {st} | {w.title} |")
    return "\n".join(lines) + "\n"
