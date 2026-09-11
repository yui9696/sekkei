"""Regenerates examples/self/design.json — sekkei's own design, written with the DSL.

    python examples/self/build_design.py

The JSON is the committed artefact; this script is its source. The test-suite lints the
JSON and runs the drift check against the repository, so the design cannot silently
diverge from the code.
"""
from __future__ import annotations

from pathlib import Path

from sekkei.dsl import DesignBuilder, check, field_, op, option

b = DesignBuilder(
    "sekkei", version="0.1.0",
    summary="A design-first harness for LLM coding agents: a checkable architecture graph, a deterministic "
            "linter, self-contained work-package briefs, a plan, and drift checks against the code.",
)
b.goal(
    "A design schema rich enough for real systems and small enough for an LLM to emit correctly.",
    "Every lint rule deterministic, identified, and covered by a planted-defect test.",
    "Briefs that let one agent implement one package without reading the rest of the design.",
    "A closed loop: brief, implementation, completion report, acceptance, next packages.",
)
b.non_goal("Generating application code.", "Orchestrating agents.", "Conversational requirements elicitation.")
b.conventions(
    language="python",
    test_command="python -m pytest -q",
    rules=[
        "Standard library only at runtime (the anthropic package is an optional extra used by sekkei/llm.py only).",
        "Python 3.11+; type hints everywhere; dataclasses for the model.",
        "No fuzzy matching: every diagnostic must be reproducible from the design alone.",
        "Import direction: cli -> {brief, drift, state, render, llm, rules, graph} -> model; never upward.",
    ],
    definition_of_done=[
        "The package's acceptance commands exit 0.",
        "`sekkei check -d examples/self/design.json --root .` reports no error.",
        "No file outside the package's write scope was changed.",
    ],
)

# --- requirements ---------------------------------------------------------
b.requirement("R-1", "The design file describes requirements, components, interfaces with operations, entities, "
                     "flows, decisions, risks, work packages and acceptance checks, and round-trips through JSON without loss.")
b.requirement("R-2", "Every lint rule is deterministic, has a stable id, a fixed severity and a fix hint, and is "
                     "covered by a planted-defect test that the meta-test enforces.")
b.requirement("R-3", "A brief for a work package contains its goal, the requirements it satisfies verbatim, the "
                     "contracts it implements, the contracts it consumes, its write scope, the conventions, its "
                     "acceptance checks and the completion-report template, and nothing about other packages.")
b.requirement("R-4", "The plan orders work packages into waves such that every package's dependencies lie in "
                     "earlier waves, and reports the size-weighted critical path.")
b.requirement("R-5", "For Python code the drift check reports missing component paths, missing operations, "
                     "parameter mismatches and undeclared imports between components.")
b.requirement("R-6", "A completion report is accepted only if every acceptance check of the package passed and "
                     "every touched file is inside the package's write scope; acceptance unlocks dependents.")
b.requirement("R-7", "No runtime dependency outside the Python standard library; Python 3.11 or newer.",
              kind="constraint")
b.requirement("R-8", "Linting and drift-checking this repository's own design finishes fast enough to run on "
                     "every commit.", kind="nonfunctional", priority="should",
              metric=("wall time of `sekkei lint` plus `sekkei check` on examples/self on a laptop", "<= 1", "s"))
b.requirement("R-9", "A human can author a design in a small Python DSL that yields the same model as the JSON.",
              priority="should")
b.requirement("R-10", "An optional command drafts a design from free text with Claude, lints it, and feeds the "
                      "diagnostics back until the design is clean or the round limit is reached.", priority="could")
b.requirement("R-11", "A command line exposes every operation with a default design file, JSON output where an "
                      "orchestrator would consume it, and exit code 1 on errors.")
b.requirement("R-12", "Two versions of a design can be compared, listing added, removed and changed elements and "
                      "the work packages whose briefs became stale; a completion report against a stale brief is "
                      "rejected unless forced.")

# --- components -------------------------------------------------------------
b.component("C-1", "Model", "Dataclasses for the design, tolerant JSON loading, serialisation and the JSON Schema.",
            path="sekkei/model.py", satisfies=["R-1", "R-7"])
b.component("C-2", "Rules", "The deterministic lint rules and the diagnostic type.",
            path="sekkei/rules.py", requires=["I-1", "I-3"], satisfies=["R-2"])
b.component("C-3", "Graph", "Dependency graphs, cycle detection, waves, critical path, traceability, scope matching.",
            path="sekkei/graph.py", requires=["I-1"], satisfies=["R-4"])
b.component("C-4", "Render", "DESIGN.md, Mermaid/DOT graphs and the traceability matrix.",
            path="sekkei/render.py", requires=["I-1", "I-3"], satisfies=["R-1"])
b.component("C-5", "Brief", "Self-contained work-package briefs, their fingerprint, and the report template.",
            path="sekkei/brief.py", requires=["I-1", "I-4", "I-7"], satisfies=["R-3", "R-12"])
b.component("C-6", "Drift", "Design-versus-code checks over Python sources using ast.",
            path="sekkei/drift.py", requires=["I-1", "I-3"], satisfies=["R-5"])
b.component("C-7", "State", "Progress state in .sekkei/state.json, brief fingerprints, and completion-report acceptance.",
            path="sekkei/state.py", requires=["I-1", "I-3"], satisfies=["R-6", "R-12"])
b.component("C-8", "DSL", "Python builder for authoring designs by hand.",
            path="sekkei/dsl.py", requires=["I-1"], satisfies=["R-9"])
b.component("C-9", "LLM", "Optional Claude drafting loop and the architect prompt.",
            path="sekkei/llm.py", requires=["I-1", "I-2"], satisfies=["R-10"])
b.component("C-10", "CLI", "argparse front end over every module.", kind="cli",
            path="sekkei/cli.py", requires=["I-1", "I-2", "I-3", "I-4", "I-5", "I-6", "I-7", "I-9", "I-11", "I-12"],
            satisfies=["R-11", "R-8"])
b.component("C-11", "Starter", "The example design written by `sekkei init`.",
            path="sekkei/examples.py", requires=["I-1", "I-8"], satisfies=["R-11"])
b.component("C-12", "Diff", "Element-level comparison of two design versions and the packages they affect.",
            path="sekkei/diff.py", requires=["I-1"], satisfies=["R-12"])

# --- interfaces (operation names are the real function names; sekkei check verifies them) ---
b.interface("I-1", "Model API", owner="C-1", kind="module", stability="stable", operations=[
    op("from_dict", [("data", "dict")], "Design", ["DesignError on type mismatch"],
       post="unknown keys are recorded in Design.unknown_keys"),
    op("to_dict", [("obj", "Any")], "JSON-compatible data"),
    op("loads", [("text", "str")], "Design", ["DesignError on invalid JSON"]),
    op("load", [("path", "str | Path")], "Design", ["DesignError", "FileNotFoundError"]),
    op("dumps", [("design", "Design")], "str"),
    op("dump", [("design", "Design"), ("path", "str | Path")], "None"),
    op("json_schema", [], "dict (JSON Schema draft 2020-12)"),
])
b.interface("I-2", "Rules API", owner="C-2", kind="module", stability="stable", operations=[
    op("lint", [("design", "Design"), ("disable", "Iterable[str]"), ("strict", "bool")], "list[Diagnostic] sorted by severity, rule, where"),
    op("has_errors", [("diags", "Iterable[Diagnostic]")], "bool"),
    op("summary", [("diags", "Iterable[Diagnostic]")], "dict severity -> count"),
    op("format_text", [("diags", "list[Diagnostic]"), ("hints", "bool")], "str"),
    op("rule_table", [], "Markdown table of all rules"),
])
b.interface("I-3", "Graph API", owner="C-3", kind="module", stability="stable", operations=[
    op("component_graph", [("design", "Design")], "dict[str, set[str]]"),
    op("package_graph", [("design", "Design")], "dict[str, set[str]]"),
    op("implied_package_edges", [("design", "Design")], "list[(from, to, interface)]"),
    op("find_cycle", [("g", "Graph")], "list[str] | None"),
    op("waves", [("g", "Graph")], "list[list[str]]", ["ValueError on a cycle"]),
    op("critical_path", [("design", "Design")], "(weight, [package ids])"),
    op("ready_packages", [("design", "Design"), ("done", "Iterable[str]")], "list[str]"),
    op("traceability", [("design", "Design")], "dict requirement -> {components, packages, acceptance}"),
    op("in_scope", [("path", "str"), ("scope_entry", "str")], "bool"),
    op("transitive", [("g", "Graph"), ("start", "str")], "set[str]"),
    op("layers", [("design", "Design")], "list[list[str]]"),
])
b.interface("I-4", "Render API", owner="C-4", kind="module", operations=[
    op("render_markdown", [("design", "Design")], "str"),
    op("mermaid", [("design", "Design"), ("which", "'components' | 'packages'")], "str"),
    op("dot", [("design", "Design"), ("which", "'components' | 'packages'")], "str"),
    op("traceability_markdown", [("design", "Design")], "str"),
    op("interface_table", [("iface", "Interface")], "Markdown table"),
])
b.interface("I-5", "Brief API", owner="C-5", kind="module", operations=[
    op("render_brief", [("design", "Design"), ("wp_id", "str"), ("state", "State | None")], "str", ["KeyError for an unknown package"]),
    op("brief_fingerprint", [("design", "Design"), ("wp_id", "str")], "16-hex-digit hash of the design-derived brief content"),
])
b.interface("I-6", "Drift API", owner="C-6", kind="module", operations=[
    op("check", [("design", "Design"), ("root", "str | Path")], "list[Finding]"),
    op("scope_violations", [("design", "Design"), ("wp_id", "str"), ("files", "Iterable[str]")], "list[str]"),
    op("format_findings", [("findings", "list[Finding]")], "str"),
    op("has_errors", [("findings", "Iterable[Finding]")], "bool"),
])
b.interface("I-7", "State API", owner="C-7", kind="module", operations=[
    op("State", [], "class: load(root), save(), status(wp), done(), set_status(wp, status, report), record_brief(wp, fp), is_stale(wp, fp)"),
    op("report_template", [("design", "Design"), ("wp_id", "str")], "dict"),
    op("validate_report", [("design", "Design"), ("report", "dict")], "list[str] problems (empty = acceptable)"),
    op("accept", [("design", "Design"), ("state", "State"), ("report", "dict"), ("fingerprint", "str | None"), ("force", "bool")],
       "list[str] problems; rejects a stale brief unless force; on success marks done and saves"),
    op("next_packages", [("design", "Design"), ("state", "State")], "list[str]"),
    op("status_table", [("design", "Design"), ("state", "State")], "Markdown table"),
])
b.interface("I-8", "DSL", owner="C-8", kind="module", operations=[
    op("DesignBuilder", [], "class with requirement/component/interface/.../work_package/build/save"),
    op("op", [("name", "str"), ("inputs", "Sequence"), ("output", "str"), ("errors", "Sequence[str]")], "Operation"),
    op("check", [("id_", "str"), ("description", "str"), ("kind", "str"), ("command", "str"), ("metric", "str")], "Acceptance"),
    op("option", [("name", "str"), ("pros", "Sequence[str]"), ("cons", "Sequence[str]")], "Option"),
    op("load_python", [("path", "str | Path")], "Design", ["ValueError if the file defines neither `design` nor `build()`"]),
])
b.interface("I-9", "LLM API", owner="C-9", kind="module", operations=[
    op("architect_prompt", [("include_schema", "bool"), ("include_rules", "bool")], "str"),
    op("draft", [("requirements_text", "str"), ("client", "Any"), ("model", "str"), ("rounds", "int")], "DraftResult",
       ["RuntimeError if the anthropic package is missing or the model refuses"]),
    op("extract_json", [("text", "str")], "dict", ["DesignError if no JSON object"]),
])
b.interface("I-10", "Command line", owner="C-10", kind="cli", operations=[
    op("sekkei init [dir]", output="starter design.json"),
    op("sekkei lint [-d FILE] [--json] [--strict] [--disable RULE|GROUP]", output="diagnostics; exit 1 on errors"),
    op("sekkei render / graph / matrix", output="DESIGN.md, Mermaid/DOT, traceability"),
    op("sekkei brief WP / plan [--json]", output="brief; waves, critical path, ready packages"),
    op("sekkei check [--root DIR] / scope WP FILES", output="drift findings; out-of-scope files"),
    op("sekkei accept REPORT [--force] / status / next / start WP", output="state transitions; stale briefs are refused"),
    op("sekkei diff OLD [-d NEW]", output="element changes and the affected packages; exit 1 if any"),
    op("sekkei schema / rules / prompt / draft FILE", output="JSON Schema; rule table; architect prompt; drafted design"),
])
b.interface("I-11", "Starter", owner="C-11", kind="module", operations=[
    op("starter_design", [("name", "str")], "Design that lints clean"),
])
b.interface("I-12", "Diff API", owner="C-12", kind="module", operations=[
    op("diff", [("old", "Design"), ("new", "Design")], "list[Change] (collection, id, added|removed|changed, fields)"),
    op("affected_packages", [("new", "Design"), ("changes", "list[Change]")], "dict package id -> reasons"),
    op("format_diff", [("changes", "list[Change]"), ("affected", "dict")], "str"),
])

# --- entities -----------------------------------------------------------------
b.entity("E-1", "Design", owner="C-1", description="The root object; serialised with the top-level key `sekkei`.", fields=[
    field_("requirements", "list[Requirement]"), field_("components", "list[Component]", "ids unique across the document"),
    field_("interfaces", "list[Interface]", "owner is a component id"), field_("work_packages", "list[WorkPackage]", "depends_on forms a DAG"),
])
b.entity("E-2", "Diagnostic", owner="C-2", fields=[
    field_("rule", "str", "e.g. V001"), field_("severity", "str", "error | warning | info"),
    field_("message", "str"), field_("where", "str", "id or JSON path"), field_("hint", "str"),
])
b.entity("E-3", "Completion report", owner="C-7", description="What an agent returns; validated by accept.", fields=[
    field_("work_package", "str"), field_("files_touched", "list[str]", "each inside the package's files"),
    field_("checks", "list[{id, passed, output}]", "one per acceptance check, all passed"),
    field_("deviations", "list[str]"), field_("proposed_decisions", "list[str]"), field_("notes", "str"),
])

# --- flows ---------------------------------------------------------------------
b.flow("F-1", "Lint from the command line", trigger="sekkei lint", steps=[
    ("C-10", "C-1", "I-1", "load the design file"),
    ("C-10", "C-2", "I-2", "run every rule"),
    ("C-2", "C-3", "I-3", "rules query graphs, cycles and traceability"),
])
b.flow("F-2", "Brief a work package", trigger="sekkei brief WP-n", steps=[
    ("C-10", "C-2", "I-2", "gate: refuse if the design has errors"),
    ("C-10", "C-5", "I-5", "render the brief"),
    ("C-5", "C-4", "I-4", "interface tables"),
    ("C-5", "C-7", "I-7", "dependency statuses and the report template"),
])
b.flow("F-3", "Accept a completion report", trigger="sekkei accept report.json", steps=[
    ("C-10", "C-7", "I-7", "validate and mark done"),
    ("C-7", "C-3", "I-3", "scope matching and ready packages"),
])
b.flow("F-5", "Design changed after a brief was issued", trigger="sekkei diff old.json; sekkei accept report.json", steps=[
    ("C-10", "C-12", "I-12", "list the changes and the packages they touch"),
    ("C-10", "C-5", "I-5", "recompute the brief fingerprint"),
    ("C-10", "C-7", "I-7", "accept compares it with the recorded one and refuses a stale brief"),
])
b.flow("F-4", "Drift check", trigger="sekkei check", steps=[
    ("C-10", "C-6", "I-6", "walk component paths"),
    ("C-6", "C-3", "I-3", "prefix matching of files to components"),
])

# --- decisions -------------------------------------------------------------------
b.decision("D-1", "Single source of truth for interface ownership",
           context="A component could list what it provides, or an interface could name its owner.",
           options=[option("interface.owner only", pros=["cannot disagree with itself"], cons=["provides list must be derived"]),
                    option("component.provides and interface.owner", pros=["explicit both ways"], cons=["two lists that must agree will not"])],
           choice="interface.owner only", rationale="Redundant bookkeeping is where LLM-written designs go wrong first.",
           affects=["C-1", "C-2"])
b.decision("D-2", "JSON as the design format",
           context="The file is written mostly by models and read mostly by tools.",
           options=[option("JSON", pros=["emitted reliably by LLMs", "stdlib parser", "exact round-trip"], cons=["hard for humans to read"]),
                    option("YAML", pros=["readable"], cons=["dependency", "indentation errors from models"]),
                    option("Markdown with conventions", pros=["readable"], cons=["needs a parser that guesses"])],
           choice="JSON", rationale="Render exists for humans; the DSL exists for hand-authoring.", affects=["C-1", "C-8"])
b.decision("D-3", "Work packages carry a write scope",
           context="Parallel agents must not edit the same files.",
           options=[option("files per package", pros=["conflict check A002", "scope check after the fact"], cons=["author must list files"]),
                    option("no scope", pros=["less to write"], cons=["conflicts found at merge time"])],
           choice="files per package", rationale="It is the only way to make parallel waves safe.", affects=["C-2", "C-6", "C-7"])
b.decision("D-4", "Python-only symbol and import checks",
           context="Drift checking needs a parser per language.",
           options=[option("stdlib ast, Python only", pros=["zero dependencies", "exact"], cons=["other languages get presence checks only"]),
                    option("tree-sitter", pros=["many languages"], cons=["native dependency", "grammar drift"])],
           choice="stdlib ast, Python only", rationale="Honest partial coverage beats a dependency the user cannot install.", affects=["C-6"])
b.decision("D-5", "No orchestration",
           context="Agent runtimes change monthly.",
           options=[option("export a JSON plan", pros=["stable contract", "works with any runner"], cons=["user wires the loop"]),
                    option("built-in runner", pros=["one command"], cons=["ties sekkei to one agent API"])],
           choice="export a JSON plan", rationale="The plan and the state file are the contract.", affects=["C-10", "C-7"])

# --- risks -------------------------------------------------------------------------
b.risk("K-1", "Wording rules (group Q) produce false positives on legitimate text.", likelihood="medium", impact="low",
       mitigation="They are warnings with a fixed vocabulary and can be disabled with --disable Q.", affects=["C-2"])
b.risk("K-2", "Dynamic or aliased imports escape the drift check, hiding an undeclared dependency.", likelihood="medium", impact="medium",
       mitigation="Documented limitation; the check is ast-based and reports only what it can prove.", affects=["C-6"])
b.risk("K-3", "A model emits keys or values outside the schema.", likelihood="high", impact="low",
       mitigation="Tolerant loader records unknown keys (S006) and invalid values (S005) instead of failing to load.", affects=["C-1", "C-9"])

# --- work packages ----------------------------------------------------------------------
T = "python -m pytest -q "
b.work_package("WP-1", "Model", goal="Implement the dataclasses, tolerant loader, serialiser and JSON Schema generator with round-trip tests.",
               components=["C-1"], implements=["I-1"], satisfies=["R-1", "R-7"], size="M",
               files=["sekkei/model.py", "tests/test_model.py"],
               acceptance=[check("A-1", "model tests pass", command=T + "tests/test_model.py")])
b.work_package("WP-2", "Graph", goal="Implement dependency graphs, cycle detection, waves, critical path, traceability and scope matching.",
               components=["C-3"], implements=["I-3"], depends_on=["WP-1"], satisfies=["R-4"], size="M",
               files=["sekkei/graph.py", "tests/test_graph.py"],
               acceptance=[check("A-2", "graph tests pass", command=T + "tests/test_graph.py")])
b.work_package("WP-3", "Rules", goal="Implement every lint rule with a stable id, severity and hint, plus the planted-defect battery and its meta-test.",
               components=["C-2"], implements=["I-2"], depends_on=["WP-1", "WP-2"], satisfies=["R-2"], size="L",
               files=["sekkei/rules.py", "tests/test_rules.py"],
               acceptance=[check("A-3", "rule tests pass, including the meta-test that every rule has a planted defect", command=T + "tests/test_rules.py")])
b.work_package("WP-4", "Render", goal="Render DESIGN.md with Mermaid graphs, layers, waves and the traceability matrix.",
               components=["C-4"], implements=["I-4"], depends_on=["WP-2"], satisfies=["R-1"], size="S",
               files=["sekkei/render.py", "tests/test_render.py"],
               acceptance=[check("A-4", "render tests pass", command=T + "tests/test_render.py")])
b.work_package("WP-5", "State", goal="Implement the state file, report validation and acceptance, and the ready-package query.",
               components=["C-7"], implements=["I-7"], depends_on=["WP-2"], satisfies=["R-6"], size="S",
               files=["sekkei/state.py", "tests/test_state.py"],
               acceptance=[check("A-5", "state tests pass", command=T + "tests/test_state.py")])
b.work_package("WP-6", "Brief", goal="Generate self-contained briefs containing only what one package needs, with the report template.",
               components=["C-5"], implements=["I-5"], depends_on=["WP-4", "WP-5"], satisfies=["R-3"], size="S",
               files=["sekkei/brief.py", "tests/test_brief.py"],
               acceptance=[check("A-6", "brief tests pass, including that a brief never names another package's components", command=T + "tests/test_brief.py")])
b.work_package("WP-7", "Drift", goal="Implement presence, symbol, parameter and import checks over Python sources, and the scope check.",
               components=["C-6"], implements=["I-6"], depends_on=["WP-2"], satisfies=["R-5"], size="M",
               files=["sekkei/drift.py", "tests/test_drift.py"],
               acceptance=[check("A-7", "drift tests pass on a synthetic repository", command=T + "tests/test_drift.py")])
b.work_package("WP-8", "DSL and starter", goal="Provide the Python builder and the starter design that `sekkei init` writes; both must produce designs that lint clean.",
               components=["C-8", "C-11"], implements=["I-8", "I-11"], depends_on=["WP-3"], satisfies=["R-9", "R-11"], size="S",
               files=["sekkei/dsl.py", "sekkei/examples.py", "tests/test_dsl.py"],
               acceptance=[check("A-8", "DSL tests pass and the starter design has zero diagnostics", command=T + "tests/test_dsl.py")])
b.work_package("WP-9", "LLM drafting", goal="Implement the architect prompt and the draft-lint-feedback loop with an injectable client so it is testable offline.",
               components=["C-9"], implements=["I-9"], depends_on=["WP-3"], satisfies=["R-10"], size="S",
               files=["sekkei/llm.py", "tests/test_llm.py"],
               acceptance=[check("A-9", "llm tests pass with a fake client", command=T + "tests/test_llm.py")])
b.work_package("WP-11", "Diff", goal="Compare two design versions element by element and map the changes to the work packages whose briefs are stale.",
               components=["C-12"], implements=["I-12"], depends_on=["WP-1"], satisfies=["R-12"], size="S",
               files=["sekkei/diff.py", "tests/test_diff.py"],
               acceptance=[check("A-13", "diff tests pass, including that a stale brief blocks acceptance", command=T + "tests/test_diff.py")])
b.work_package("WP-10", "CLI", goal="Expose every operation on the command line with exit codes and JSON output, and prove the whole loop end to end.",
               components=["C-10"], implements=["I-10"], depends_on=["WP-6", "WP-7", "WP-8", "WP-9", "WP-11"], satisfies=["R-11", "R-8", "R-12"], size="M",
               files=["sekkei/cli.py", "sekkei/__main__.py", "tests/test_cli.py", "tests/test_self.py"],
               acceptance=[check("A-10", "CLI round-trip test passes: init, lint, render, plan, brief, accept, next", command=T + "tests/test_cli.py"),
                           check("A-11", "self design lints clean and drift check on the repository reports no error", command=T + "tests/test_self.py"),
                           check("A-12", "lint + check on examples/self run within the target", kind="metric", metric="R-8")])

if __name__ == "__main__":
    out = Path(__file__).with_name("design.json")
    b.save(out)
    print(f"wrote {out}")
