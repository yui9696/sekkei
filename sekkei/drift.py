"""Drift check: does the code still match the design?

Standard-library ``ast`` only, Python only. Checks:

- presence: every component ``path`` exists;
- symbols: operations of ``function``/``class``/``module`` interfaces exist as defs/classes
  in the owner's files, and parameter names match the declared inputs;
- dependencies: an import from component A's files into component B's files is allowed
  only if A requires an interface owned by B (undeclared dependency otherwise); a declared
  dependency with no import behind it is reported as info;
- scope: files changed while doing a package must be inside its write scope.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from . import graph as G
from .model import Component, Design

CHECKABLE_KINDS = ("function", "class", "module")


@dataclass
class Finding:
    kind: str
    severity: str
    message: str
    where: str = ""

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.severity.upper():7} {self.kind} [{self.where}]: {self.message}"


@dataclass
class _Symbols:
    functions: dict[str, list[str]]  # name -> parameter names (top-level defs and methods)
    classes: set[str]
    has_varargs: set[str]


def _py_files(root: Path, rel: str) -> list[Path]:
    p = root / rel
    if p.is_file():
        return [p] if p.suffix == ".py" else []
    if p.is_dir():
        return sorted(f for f in p.rglob("*.py") if "__pycache__" not in f.parts)
    return []


def _collect_symbols(files: Iterable[Path]) -> _Symbols:
    syms = _Symbols({}, set(), set())
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                syms.classes.add(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = node.args
                names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
                if names and names[0] in ("self", "cls"):
                    names = names[1:]
                syms.functions.setdefault(node.name, names)
                if a.vararg or a.kwarg:
                    syms.has_varargs.add(node.name)
    return syms


def _module_candidates(module: str, level: int, file: Path, root: Path) -> list[Path]:
    """Files an import statement may refer to (first that exists wins)."""
    if level:
        base = file.parent
        for _ in range(level - 1):
            base = base.parent
    else:
        base = root
    parts = module.split(".") if module else []
    target = base.joinpath(*parts) if parts else base
    return [target.with_suffix(".py"), target / "__init__.py"]


def _imports(file: Path, root: Path) -> list[tuple[str, Path]]:
    """(imported name, resolved file) for every import that resolves inside ``root``."""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    except SyntaxError:
        return []
    out: list[tuple[str, Path]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for cand in _module_candidates(alias.name, 0, file, root):
                    if cand.exists():
                        out.append((alias.name, cand))
                        break
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for cand in _module_candidates(mod, node.level, file, root):
                if cand.exists():
                    out.append((mod or ".", cand))
                    break
            # `from pkg import submodule` resolves per name
            for alias in node.names:
                sub = f"{mod}.{alias.name}" if mod else alias.name
                for cand in _module_candidates(sub, node.level, file, root):
                    if cand.exists():
                        out.append((sub, cand))
                        break
    return out


def _component_of(path: Path, root: Path, comps: list[Component]) -> Optional[Component]:
    """Longest-prefix match of a file against component paths."""
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return None
    best: Optional[Component] = None
    for c in comps:
        if c.path and G.in_scope(rel, c.path) and (best is None or len(c.path) > len(best.path)):
            best = c
    return best


def check(design: Design, root: str | Path) -> list[Finding]:
    root = Path(root).resolve()
    out: list[Finding] = []
    comps = [c for c in design.components if c.path]
    for c in design.components:
        if c.kind == "external":
            continue
        if not c.path:
            out.append(Finding("no_path", "info", "component has no path; nothing to check", c.id))
            continue
        if not (root / c.path).exists():
            out.append(Finding("missing_path", "error", f"path {c.path!r} does not exist", c.id))

    # symbols
    for iface in design.interfaces:
        owner = design.component(iface.owner)
        if owner is None or owner.kind == "external":
            continue
        if iface.kind not in CHECKABLE_KINDS:
            out.append(Finding("not_checkable", "info", f"interface kind {iface.kind!r} is not checked", iface.id))
            continue
        files = _py_files(root, owner.path) if owner.path else []
        if not files:
            if owner.path and (root / owner.path).exists():
                out.append(Finding("not_checkable", "info", "owner has no Python files", iface.id))
            continue
        syms = _collect_symbols(files)
        for o in iface.operations:
            name = o.name.split("(")[0].split(".")[-1].strip()
            if name in syms.functions:
                declared = [p.name for p in o.inputs]
                actual = syms.functions[name]
                if declared and name not in syms.has_varargs and set(declared) - set(actual):
                    out.append(Finding(
                        "param_mismatch", "warning",
                        f"{name}: declared inputs {declared} vs actual parameters {actual}", iface.id,
                    ))
            elif name in syms.classes:
                continue
            else:
                out.append(Finding("missing_symbol", "error", f"operation {o.name!r} not found in {owner.path}", iface.id))

    # dependencies
    owner_of = {i.id: i.owner for i in design.interfaces}
    declared: dict[str, set[str]] = {
        c.id: {owner_of[i] for i in c.requires if i in owner_of and owner_of[i] != c.id} for c in design.components
    }
    observed: dict[str, set[str]] = {c.id: set() for c in design.components}
    for c in comps:
        for f in _py_files(root, c.path):
            src = _component_of(f, root, comps)
            if src is None or src.id != c.id:
                continue  # file belongs to a more specific component
            for name, target in _imports(f, root):
                dst = _component_of(target, root, comps)
                if dst is None or dst.id == c.id:
                    continue
                observed[c.id].add(dst.id)
                if dst.id not in declared[c.id]:
                    rel = f.relative_to(root).as_posix()
                    out.append(Finding(
                        "undeclared_dependency", "error",
                        f"{rel} imports {name} ({dst.id}) but {c.id} requires no interface of {dst.id}", c.id,
                    ))
    for c in comps:
        if not _py_files(root, c.path):
            continue
        for dst in sorted(declared[c.id] - observed[c.id]):
            dc = design.component(dst)
            if dc is not None and dc.path and _py_files(root, dc.path):
                out.append(Finding("unused_dependency", "info", f"requires an interface of {dst} but never imports it", c.id))

    order = {"error": 0, "warning": 1, "info": 2}
    out.sort(key=lambda f: (order[f.severity], f.kind, f.where))
    # de-duplicate identical findings (one per import statement otherwise)
    seen: set[tuple[str, str, str]] = set()
    uniq: list[Finding] = []
    for f in out:
        key = (f.kind, f.where, f.message)
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq


def has_errors(findings: Iterable[Finding]) -> bool:
    return any(f.severity == "error" for f in findings)


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "OK: no drift\n"
    lines = [f"{f.severity.upper():7} {f.kind} [{f.where}]: {f.message}" for f in findings]
    n_err = sum(1 for f in findings if f.severity == "error")
    lines.append(f"{n_err} error(s), {len(findings) - n_err} other finding(s)")
    return "\n".join(lines) + "\n"


def scope_violations(design: Design, wp_id: str, files: Iterable[str]) -> list[str]:
    wp = design.work_package(wp_id)
    if wp is None:
        raise KeyError(f"unknown work package {wp_id!r}")
    return [f for f in files if not any(G.in_scope(f, s) for s in wp.files)]
