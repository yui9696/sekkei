"""Command-line front end. Every command reads a design file (default ``design.json``)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import brief as B
from . import diff as DF
from . import drift as D
from . import graph as G
from . import model as M
from . import render as RD
from . import rules as R
from . import state as S


def _load(path: str) -> M.Design:
    from . import load  # dispatches .json / .py

    try:
        return load(path)
    except FileNotFoundError:
        sys.exit(f"error: {path} not found (run `sekkei init` to create one)")
    except M.DesignError as exc:
        sys.exit(f"error: {path}: {exc}")


def _gate(design: M.Design, args: argparse.Namespace) -> None:
    """Refuse to derive artefacts from a design with errors, unless --force."""
    diags = R.lint(design, disable=_disabled(args))
    if R.has_errors(diags) and not getattr(args, "force", False):
        sys.stderr.write(R.format_text(diags, hints=False))
        sys.exit("error: the design has errors; fix them or pass --force")


def _disabled(args: argparse.Namespace) -> set[str]:
    raw = getattr(args, "disable", None) or []
    return {x.strip() for item in raw for x in item.split(",") if x.strip()}


def _root(args: argparse.Namespace) -> Path:
    if getattr(args, "root", None):
        return Path(args.root)
    return Path(args.design).resolve().parent


def _out(text: str, path: Optional[str]) -> None:
    if path:
        _write(path, text)
        print(f"wrote {path}")
    else:
        sys.stdout.write(text)


def _read(path: str) -> str:
    """Read a text file or exit with a one-line error (no traceback for a missing or non-UTF-8 file)."""
    p = Path(path)
    if not p.exists():
        sys.exit(f"error: {path} not found")
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        sys.exit(f"error: {path} is not UTF-8 text ({exc.reason} at byte {exc.start})")
    except OSError as exc:
        sys.exit(f"error: cannot read {path}: {exc}")


def _write(path: str, text: str) -> None:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    except OSError as exc:
        sys.exit(f"error: cannot write {path}: {exc}")


# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    from .examples import starter_design

    target = Path(args.dir) / "design.json"
    if target.exists() and not args.force:
        sys.exit(f"error: {target} exists (use --force to overwrite)")
    target.parent.mkdir(parents=True, exist_ok=True)
    M.dump(starter_design(args.name or target.parent.resolve().name), target)
    print(f"wrote {target}\nnext: edit it, then `sekkei lint {target}`")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    design = _load(args.design)
    diags = R.lint(design, disable=_disabled(args), strict=args.strict)
    if args.json:
        print(json.dumps([d.__dict__ for d in diags], indent=2))
    else:
        sys.stdout.write(R.format_text(diags, hints=not args.no_hints))
    return 1 if R.has_errors(diags) else 0


def cmd_render(args: argparse.Namespace) -> int:
    design = _load(args.design)
    _out(RD.render_markdown(design), args.output)
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    design = _load(args.design)
    _gate(design, args)
    state = S.State.load(_root(args))
    try:
        text = B.render_brief(design, args.package, state)
    except KeyError as exc:
        sys.exit(f"error: {exc.args[0]}")
    if not args.no_record:
        state.record_brief(args.package, B.brief_fingerprint(design, args.package))
        state.save()
    _out(text, args.output)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    old = _load(args.old)
    new = _load(args.design)
    changes = DF.diff(old, new)
    affected = DF.affected_packages(new, changes)
    if args.json:
        print(json.dumps({"changes": [c.__dict__ for c in changes], "affected": affected}, indent=2))
    else:
        sys.stdout.write(DF.format_diff(changes, affected))
    return 1 if changes else 0


def cmd_plan(args: argparse.Namespace) -> int:
    design = _load(args.design)
    _gate(design, args)
    state = S.State.load(_root(args))
    g = G.package_graph(design)
    ws = G.waves(g)
    weight, path = G.critical_path(design)
    ready = G.ready_packages(design, state.done())
    implied = G.implied_package_edges(design)
    if args.json:
        print(json.dumps({
            "waves": ws,
            "critical_path": {"weight": weight, "packages": path},
            "ready": ready,
            "implied_dependencies": [{"from": a, "to": b, "via": i} for a, b, i in implied],
            "packages": {
                w.id: {
                    "title": w.title, "size": w.size, "status": state.status(w.id),
                    "depends_on": w.depends_on, "files": w.files, "components": w.components,
                } for w in design.work_packages
            },
        }, indent=2))
        return 0
    print("Waves (packages in one wave may run in parallel):")
    for n, wave in enumerate(ws, 1):
        print(f"  {n}. " + ", ".join(f"{w}[{state.status(w)}]" for w in wave))
    print(f"Critical path (weight {weight}): " + " -> ".join(path))
    print("Ready now: " + (", ".join(ready) or "(nothing; all done or blocked)"))
    for a, b, i in implied:
        print(f"  note: {a} uses {i} from {b} without depends_on (C007)")
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    design = _load(args.design)
    which = "packages" if args.packages else "components"
    text = RD.dot(design, which) if args.dot else RD.mermaid(design, which)
    _out(text, args.output)
    return 0


def cmd_matrix(args: argparse.Namespace) -> int:
    design = _load(args.design)
    if args.json:
        print(json.dumps(G.traceability(design), indent=2))
    else:
        sys.stdout.write(RD.traceability_markdown(design))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    design = _load(args.design)
    findings = D.check(design, _root(args))
    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        sys.stdout.write(D.format_findings(findings))
    return 1 if D.has_errors(findings) else 0


def cmd_scope(args: argparse.Namespace) -> int:
    design = _load(args.design)
    files = list(args.files)
    if not files and not sys.stdin.isatty():
        files = [ln.strip() for ln in sys.stdin if ln.strip()]
    try:
        bad = D.scope_violations(design, args.package, files)
    except KeyError as exc:
        sys.exit(f"error: {exc.args[0]}")
    if bad:
        print("out of scope for " + args.package + ":")
        for f in bad:
            print("  " + f)
        return 1
    print(f"OK: {len(files)} file(s) within the scope of {args.package}")
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    design = _load(args.design)
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"error: cannot read report: {exc}")
    state = S.State.load(_root(args))
    wp_id = report.get("work_package") if isinstance(report, dict) else None
    fingerprint = B.brief_fingerprint(design, wp_id) if design.work_package(wp_id or "") else None
    problems = S.accept(design, state, report, fingerprint=fingerprint, force=args.force)
    if problems:
        print("rejected:")
        for p in problems:
            print("  " + p)
        return 1
    wp = report["work_package"]
    print(f"accepted {wp}; now ready: " + (", ".join(S.next_packages(design, state)) or "(none)"))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    design = _load(args.design)
    state = S.State.load(_root(args))
    fingerprints = {w.id: B.brief_fingerprint(design, w.id) for w in design.work_packages}
    sys.stdout.write(S.status_table(design, state, fingerprints))
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    design = _load(args.design)
    state = S.State.load(_root(args))
    for w in S.next_packages(design, state):
        print(w)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    design = _load(args.design)
    if design.work_package(args.package) is None:
        sys.exit(f"error: unknown work package {args.package!r}")
    state = S.State.load(_root(args))
    state.set_status(args.package, args.status)
    state.save()
    print(f"{args.package}: {args.status}")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    _out(json.dumps(M.json_schema(), indent=2) + "\n", args.output)
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    sys.stdout.write(R.rule_table())
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    from .llm import architect_prompt

    _out(architect_prompt(include_schema=not args.no_schema) + "\n", args.output)
    return 0


def _progress(kind: str, data: dict) -> None:
    if kind == "round":
        c = R.summary(data["diagnostics"])
        sys.stderr.write(f"{data['phase']} round {data['round']}: {c['error']} error(s), {c['warning']} warning(s)\n")
    elif kind == "review":
        sys.stderr.write(f"review pass {data['pass_']}: {data['findings']} finding(s)\n")
    elif kind == "revise_failed":
        sys.stderr.write("revision did not lint clean; keeping the previous design\n")


def _backend(args: argparse.Namespace):
    from .llm import get_backend

    try:
        return get_backend(args.backend, args.model)
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")


def cmd_design(args: argparse.Namespace) -> int:
    """requirements text -> complete, lint-clean design, with no model: the engine."""
    from .engine import design as run_engine

    text = _read(args.input)
    result = run_engine(text, assume=not args.no_assume)
    if not result.ok and not result.design.requirements:
        sys.stdout.write(R.format_text(result.diagnostics))
        return 1
    _write(args.output, M.dumps(result.design))
    if args.augmented:
        _write(args.augmented, result.augmented_text)
        print(f"wrote {args.augmented}")
    print(f"wrote {args.output}: {len(result.design.requirements)} requirements, {len(result.design.components)} components, "
          f"{len(result.design.interfaces)} interfaces, {len(result.design.decisions)} decisions, "
          f"{len(result.design.work_packages)} work packages")
    if args.render:
        _write(args.render, RD.render_markdown(result.design))
        print(f"wrote {args.render}")
    if args.review:
        _write(args.review, result.notes.to_markdown())
        print(f"wrote {args.review}")
    if args.trace:
        _write(args.trace, json.dumps(result.trace_json(), indent=2, ensure_ascii=False))
        print(f"wrote {args.trace}")
    for line in result.log:
        print("  repair: " + line)
    sys.stdout.write(R.format_text(result.diagnostics, hints=False))
    an = result.analysis
    print("recognised patterns: " + (", ".join(an.patterns) or "(none; layered fallback)"))
    print("active qualities: " + (", ".join(f"{q}={w}" for q, w in an.qualities.items()) or "(none)"))
    for x in result.design.decisions:
        print(f"  {x.id} {x.title}: {x.choice}")
    if result.answers:
        print(f"questions answered by the engine: {len(result.answers)} (proposed decisions; see --review)")
    if result.placements:
        print(f"requirements placed without a pattern: {len(result.placements)} (see --review)")
    open_qs = [q for q in result.notes.questions if q.id not in {a.question_id for a in result.answers}]
    if open_qs:
        print(f"open questions: {len(open_qs)} (see --review)")
    if result.review.needs_human:
        print("needs a human: " + "; ".join(
            [f"{len(result.review.unrecognised)} unrecognised requirement(s)"] * bool(result.review.unrecognised)
            + [f"{len(result.review.unaddressed)} unaddressed quality(ies)"] * bool(result.review.unaddressed)
            + [f"{len(result.review.generic)} generic component(s)"] * bool(result.review.generic)))
    return 0 if result.ok else 1


def cmd_interview(args: argparse.Namespace) -> int:
    """Design in dialogue: the engine asks one thing at a time; answers become requirements."""
    from .engine.interview import run_cli

    root = Path(args.root) if args.root else Path.cwd()
    if args.script and not Path(args.script).exists():
        sys.exit(f"error: {args.script} not found")
    if args.input and not Path(args.input).exists():
        sys.exit(f"error: {args.input} not found")
    inp = open(args.script, encoding="utf-8") if args.script else sys.stdin
    try:
        return run_cli(inp, sys.stdout, root, Path(args.input) if args.input else None,
                       Path(args.out_dir) if args.out_dir else None)
    finally:
        if args.script:
            inp.close()


def cmd_ask(args: argparse.Namespace) -> int:
    """Only the questions an architect would ask about a requirements text."""
    from .engine import ask
    from .engine.gaps import questions_markdown

    qs = ask(_read(args.input))
    if args.json:
        print(json.dumps([q.__dict__ for q in qs], indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(questions_markdown(qs))
    return 0


def cmd_deliver(args: argparse.Namespace) -> int:
    """requirements text -> the whole hand-over package: design, notes, ADRs, C4, risks, FMEA, roadmap, RACI, SLOs, cost model, runbooks."""
    from pathlib import Path

    from . import deliverables as DV
    from .engine import design as run_engine

    text = _read(args.input)
    prices = None
    if args.prices:
        try:
            prices = {k: float(v) for k, v in json.loads(_read(args.prices)).items()}
        except (ValueError, AttributeError) as exc:
            print(f"error: --prices must be a JSON object of unit prices: {exc}", file=sys.stderr)
            return 2
    result = run_engine(text, assume=not args.no_assume)
    if not result.ok and not result.design.requirements:
        sys.stdout.write(R.format_text(result.diagnostics))
        return 1
    pk = DV.package(result, prices)
    out = Path(args.output)
    written = pk.write(out)
    print(f"wrote {len(written)} files to {out}/ ({len(result.design.components)} components, {len(result.design.decisions)} decisions, "
          f"{sum(1 for n in pk.files if n.startswith('adr/'))} ADRs, {len(result.design.risks)} risks)")
    if not result.ok:
        sys.stdout.write(R.format_text(result.diagnostics, hints=False))
    if result.review.needs_human:
        print("needs a human: see NOTES.md §5")
    return 0 if result.ok else 1


def cmd_template(args: argparse.Namespace) -> int:
    from .engine import REQUIREMENTS_TEMPLATE

    _out(REQUIREMENTS_TEMPLATE, args.output)
    return 0


def cmd_draft_model(args: argparse.Namespace) -> int:
    """Model-based drafting (optional): draft, lint loop, and with --review the architect review + revise."""
    from .llm import design as llm_design
    from .llm import draft

    text = _read(args.input)
    backend = _backend(args)
    sys.stderr.write(f"backend: {backend.name}\n")
    try:
        if args.review:
            result = llm_design(text, backend=backend, rounds=args.rounds, review_rounds=1, on_event=_progress)
            for f in result.findings:
                print(f"  review [{f.severity}/{f.area}] {f.finding}")
        else:
            result = draft(text, backend=backend, rounds=args.rounds, on_event=_progress)
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")
    if result.design is None:
        sys.exit("error: the model never returned a parseable design")
    M.dump(result.design, args.output)
    print(f"wrote {args.output}")
    sys.stdout.write(R.format_text(result.diagnostics, hints=False))
    return 0 if result.ok else 1


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sekkei", description="Design-first harness for LLM coding agents.")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, fn, help_: str, design: bool = True):
        sp = sub.add_parser(name, help=help_, description=help_)
        if design:
            sp.add_argument("-d", "--design", default="design.json", help="design file (.json or .py); default design.json")
        sp.set_defaults(fn=fn)
        return sp

    sp = add("init", cmd_init, "write a starter design.json", design=False)
    sp.add_argument("dir", nargs="?", default=".")
    sp.add_argument("--name")
    sp.add_argument("--force", action="store_true")

    sp = add("lint", cmd_lint, "check the design; exit 1 on errors")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--strict", action="store_true", help="treat warnings as errors")
    sp.add_argument("--disable", action="append", metavar="RULE|GROUP", help="e.g. Q or S003,C007")
    sp.add_argument("--no-hints", action="store_true")

    sp = add("render", cmd_render, "render DESIGN.md")
    sp.add_argument("-o", "--output")

    sp = add("brief", cmd_brief, "print a self-contained brief for one work package")
    sp.add_argument("package", help="work package id, e.g. WP-1")
    sp.add_argument("-o", "--output")
    sp.add_argument("--root", help="repository root holding .sekkei/ (default: design file's directory)")
    sp.add_argument("--force", action="store_true", help="proceed even if the design has errors")
    sp.add_argument("--disable", action="append")
    sp.add_argument("--no-record", action="store_true", help="do not record the brief fingerprint in the state")

    sp = add("diff", cmd_diff, "compare an older design file with the current one; exit 1 if they differ")
    sp.add_argument("old", help="the older design file")
    sp.add_argument("--json", action="store_true")

    sp = add("plan", cmd_plan, "waves, critical path, ready packages")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--root")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--disable", action="append")

    sp = add("graph", cmd_graph, "Mermaid (default) or DOT graph")
    sp.add_argument("--packages", action="store_true", help="work-package graph instead of components")
    sp.add_argument("--dot", action="store_true")
    sp.add_argument("-o", "--output")

    sp = add("matrix", cmd_matrix, "traceability matrix")
    sp.add_argument("--json", action="store_true")

    sp = add("check", cmd_check, "drift check against the code; exit 1 on errors")
    sp.add_argument("--root", help="repository root (default: design file's directory)")
    sp.add_argument("--json", action="store_true")

    sp = add("scope", cmd_scope, "report files outside a package's write scope (args or stdin)")
    sp.add_argument("package")
    sp.add_argument("files", nargs="*")

    sp = add("accept", cmd_accept, "validate a completion report and mark the package done")
    sp.add_argument("report")
    sp.add_argument("--root")
    sp.add_argument("--force", action="store_true", help="accept even if the brief is stale")

    sp = add("status", cmd_status, "package status table")
    sp.add_argument("--root")

    sp = add("next", cmd_next, "packages whose dependencies are done")
    sp.add_argument("--root")

    sp = add("start", cmd_start, "set a package's status (default in_progress)")
    sp.add_argument("package")
    sp.add_argument("--status", default="in_progress", choices=M.PACKAGE_STATUSES)
    sp.add_argument("--root")

    sp = add("schema", cmd_schema, "print the JSON Schema of the design file", design=False)
    sp.add_argument("-o", "--output")

    add("rules", cmd_rules, "list the lint rules", design=False)

    sp = add("prompt", cmd_prompt, "print the architect system prompt for use with any model", design=False)
    sp.add_argument("--no-schema", action="store_true")
    sp.add_argument("-o", "--output")

    def model_args(sp):
        sp.add_argument("--backend", choices=["auto", "claude-code", "anthropic"], default="auto",
                        help="claude-code = local `claude -p` (default when on PATH); anthropic = the SDK")
        sp.add_argument("--model", help="model id; default: the backend's default")
        sp.add_argument("--rounds", type=int, default=3, help="lint feedback rounds per phase")

    sp = add("design", cmd_design, "design a system from a requirements text (no model needed)", design=False)
    sp.add_argument("input", help="requirements text file (Markdown or plain text)")
    sp.add_argument("-o", "--output", default="design.json")
    sp.add_argument("--render", metavar="DESIGN.md", help="also write the Markdown design document")
    sp.add_argument("--review", metavar="NOTES.md", help="also write the architect's notes: questions, capacity, effort, threats, self-review")
    sp.add_argument("--trace", metavar="TRACE.json", help="also write the element-to-sentence/rule trace")
    sp.add_argument("--augmented", metavar="REQ.md", help="also write the requirements with the engine's assumed answers appended")
    sp.add_argument("--no-assume", action="store_true", help="do not answer open questions; leave them in the notes")

    sp = add("interview", cmd_interview, "design in dialogue: describe the system, answer one question at a time", design=False)
    sp.add_argument("input", nargs="?", help="optional requirements file to start from")
    sp.add_argument("--root", help="where .sekkei/interview.json lives (default: cwd)")
    sp.add_argument("--out-dir", help="where /design writes design.json, DESIGN.md, NOTES.md, requirements.md (default: root)")
    sp.add_argument("--script", help="read replies from a file instead of the terminal")

    sp = add("ask", cmd_ask, "print the questions an architect would ask about a requirements text", design=False)
    sp.add_argument("input", help="requirements text file")
    sp.add_argument("--json", action="store_true")

    sp = add("deliver", cmd_deliver, "write the whole hand-over package (design, notes, ADRs, C4, risk register, FMEA, roadmap, RACI, SLOs, cost model, runbooks)", design=False)
    sp.add_argument("input", help="requirements text file (Markdown or plain text; English or Japanese)")
    sp.add_argument("-o", "--output", default="deliverables", help="output directory (default: deliverables/)")
    sp.add_argument("--prices", metavar="PRICES.json", help="unit prices for the cost model (keys listed in COST_MODEL.md); never guessed")
    sp.add_argument("--no-assume", action="store_true", help="do not answer open questions; leave them in the notes")

    sp = add("template", cmd_template, "print a requirements template that makes the engine's job easiest", design=False)
    sp.add_argument("-o", "--output", help="write to a file, e.g. requirements.md")

    sp = add("draft", cmd_draft_model, "optional: draft a design with a model, lint with feedback; --review adds the architect review", design=False)
    sp.add_argument("input", help="requirements text file")
    sp.add_argument("-o", "--output", default="design.json")
    sp.add_argument("--review", action="store_true", help="add the senior-architect review and revision pass")
    sp.add_argument("--backend", choices=["auto", "claude-code", "anthropic"], default="auto")
    sp.add_argument("--model", help="model id; default: the backend's default")
    sp.add_argument("--rounds", type=int, default=3, help="lint feedback rounds per phase")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
