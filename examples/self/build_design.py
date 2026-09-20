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
b.requirement("R-10", "sekkei designs from a requirements text: it drafts a design with a model, feeds lint "
                      "diagnostics back until clean, has the model review the design against a senior-architect "
                      "checklist, revises, and lints again; the model runs through the local Claude Code CLI "
                      "(no API key) or the anthropic SDK.", priority="should")
b.requirement("R-11", "A command line exposes every operation with a default design file, JSON output where an "
                      "orchestrator would consume it, and exit code 1 on errors.")
b.requirement("R-12", "Two versions of a design can be compared, listing added, removed and changed elements and "
                      "the work packages whose briefs became stale; a completion report against a stale brief is "
                      "rejected unless forced.")
b.requirement("R-13", "sekkei designs a system from a requirements text without any model: it segments the text into "
                      "requirement units with their numbers, recognises capability patterns and quality attributes from a "
                      "catalogue, synthesises components, interfaces with operations, entities, flows, decisions, risks and "
                      "work packages, scores every decision against the active qualities and constraints, repairs and lints "
                      "the result, and reviews its own gaps.")
b.requirement("R-14", "The design engine is deterministic: the same requirements text yields byte-identical output.",
              kind="nonfunctional", priority="must", metric=("designs from two runs on the same text that differ", "= 0", "designs"))
b.requirement("R-15", "Every element of a generated design traces to the input sentences and the catalogue rules that "
                      "produced it, and the engine states which requirements it did not recognise instead of hiding them.")
b.requirement("R-16", "Besides the design, the engine hands over an architect's notes: the questions the text leaves open "
                      "with the assumption taken meanwhile, capacity estimates with formulas and inputs, an effort and "
                      "schedule estimate, a STRIDE-lite threat model whose threats become risks in the design, and a "
                      "requirements template.")
b.requirement("R-17", "The engine answers its own open questions from evidence in the text or defensible defaults, appends "
                      "the answers to the requirements so they shape the design, and records each as a proposed decision "
                      "with the options considered and what to change if the real answer differs.")
b.requirement("R-18", "Every functional requirement no pattern recognised gets an owner: an existing specific component by "
                      "word overlap, the surface and core for a human use case, or a newly synthesised component named "
                      "from the sentence's verb class and object, wired into the design and packaged.")
b.requirement("R-19", "A human can design in dialogue: free sentences become classified requirement bullets, the engine "
                      "re-designs after every turn and asks one thing at a time in architect order (placements to confirm, "
                      "stack, load and quality, data/security/operations/cost, close decisions), each with its proposal; "
                      "answers are normalised into canonical bullets so the requirements file reproduces the design without "
                      "the dialogue; the session resumes from saved state.")

b.requirement("R-20", "Requirements may be written in Japanese: a glossary, a number grammar and a particle-driven reorder rewrite "
                      "each sentence into the engine's canonical English; every rewrite is reported next to its source and words the "
                      "glossary does not know are listed, never guessed.")
b.requirement("R-21", "The whole hand-over package is derived from the design: executive summary, ADRs, C4 diagrams, risk register, "
                      "FMEA, roadmap, RACI, SLOs, a cost model whose unit prices are never guessed, and runbooks.")
b.requirement("R-22", "The design is attacked with the requirements as the oracle: inert sentences, lost numbers, contradictions, "
                      "fragile decisions, assumption load, non-determinism and deliverable drift are reported with a severity.")

b.requirement("R-23", "Specifications as engineers write them are read: numbered headings without '#', requirement tables, user stories in "
                      "headings, Given/When/Then, checkboxes, nested bullets, speaker labels, TODO and out-of-scope lines, DECIDED lines, "
                      "front matter and 'alternatives considered'; every fold is reported in the notes.")
b.requirement("R-24", "Work packages export as tracker issues (Markdown bodies, a GitHub CLI script in dependency order, CSV) and the "
                      "HTTP interfaces export as an OpenAPI 3.0 skeleton.")

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
b.component("C-9", "Design engine", "Model backends (Claude Code CLI, anthropic SDK, fake), the architect and "
            "review prompts, and the draft/review/revise pipeline.",
            path="sekkei/llm.py", requires=["I-1", "I-2"], satisfies=["R-10"])
b.component("C-10", "CLI", "argparse front end over every module.", kind="cli",
            path="sekkei/cli.py", requires=["I-1", "I-2", "I-3", "I-4", "I-5", "I-6", "I-7", "I-9", "I-11", "I-12", "I-19", "I-20", "I-26", "I-28", "I-29", "I-31"],
            satisfies=["R-11", "R-8"])
b.component("C-11", "Starter", "The example design written by `sekkei init`.",
            path="sekkei/examples.py", requires=["I-1", "I-8"], satisfies=["R-11"])
b.component("C-12", "Diff", "Element-level comparison of two design versions and the packages they affect.",
            path="sekkei/diff.py", requires=["I-1"], satisfies=["R-12"])
b.component("C-13", "Text analysis", "Sentence segmentation, sections, modality, the quantity grammar, actors, verbs and nouns.",
            path="sekkei/engine/text.py", satisfies=["R-13"])
b.component("C-14", "Catalogue", "The knowledge base: archetypes, entity and flow templates, decision points with scored options, "
            "risks, capability patterns with signals, quality tactics, constraint tokens and language layouts.",
            path="sekkei/engine/catalog.py", satisfies=["R-13"])
b.component("C-15", "Requirements analysis", "Turns sentences into requirement units (kind, priority, metric), matches patterns and "
            "qualities, extracts constraints, and lists what was not recognised.",
            path="sekkei/engine/analysis.py", requires=["I-27", "I-30", "I-13", "I-14"], satisfies=["R-13", "R-15"])
b.component("C-16", "Synthesis", "Instantiates and merges archetypes into components and interfaces, derives operations from "
            "verbs and objects, maps requirements to components, builds entities, flows, decisions, risks, conventions and "
            "work packages; records the trace.", path="sekkei/engine/synthesis.py",
            requires=["I-1", "I-3", "I-13", "I-14", "I-15", "I-17", "I-25", "I-32"], satisfies=["R-13", "R-15", "R-18"])
b.component("C-17", "Evaluation", "Scores decision options against the active qualities and constraints (utility with "
            "availability rules and stated-technology bonus) and writes the engine's review of its own gaps.",
            path="sekkei/engine/evaluate.py", requires=["I-1", "I-14", "I-15"], satisfies=["R-13", "R-15"])
b.component("C-18", "Repair", "Runs the linter over the synthesised design and applies the few repairs synthesis may make.",
            path="sekkei/engine/repair.py", requires=["I-1", "I-2"], satisfies=["R-13"])
b.component("C-19", "Engine facade", "design(text, assume): analyse, answer open questions and re-analyse, synthesise, record assumed decisions, inject threats, repair, review, notes; ask(text): questions only.",
            path="sekkei/engine/__init__.py", requires=["I-1", "I-2", "I-15", "I-27", "I-30", "I-16", "I-17", "I-18", "I-20", "I-22", "I-23", "I-24", "I-25"],
            satisfies=["R-13", "R-14", "R-15", "R-16", "R-17"])
b.component("C-24", "Answers", "Answer rules for every gap question: evidence from the text first, defensible defaults second; appends the answers to the requirements.",
            path="sekkei/engine/answers.py", requires=["I-15", "I-20", "I-21"], satisfies=["R-17"])
b.component("C-26", "Interview", "The dialogue: prompts in architect order with proposals, canonical bullets from answers, owner and decision overrides, undo, saved state, and the read-eval loop.",
            path="sekkei/engine/interview.py", requires=["I-1", "I-4", "I-13", "I-15", "I-19", "I-20", "I-24"], satisfies=["R-19"])
b.component("C-25", "Owners", "Owner placement for requirements no pattern recognised: word overlap with specific components, surface+core for human use cases, or a synthesised component.",
            path="sekkei/engine/owners.py", requires=["I-1", "I-13", "I-14", "I-15"], satisfies=["R-18"])
b.component("C-20", "Gap questions", "The questions an architect asks before committing, derived from what the text does not say, each with the assumption used meanwhile.",
            path="sekkei/engine/gaps.py", requires=["I-15"], satisfies=["R-16"])
b.component("C-21", "Sizing", "Capacity estimates (Little's law, storage, backlog) and effort/schedule from package sizes and team size, with every assumption stated.",
            path="sekkei/engine/sizing.py", requires=["I-1", "I-3", "I-13", "I-15"], satisfies=["R-16"])
b.component("C-22", "Threat model", "STRIDE-lite threats per archetype, injected into the design as risks with mitigations and proofs.",
            path="sekkei/engine/threats.py", requires=["I-1"], satisfies=["R-16"])
b.component("C-23", "Architect's notes", "Assembles questions, capacity, effort, threats, the self-review and the reading of the text into one Markdown report; holds the requirements template.",
            path="sekkei/engine/report.py", requires=["I-1", "I-15", "I-17", "I-20", "I-21", "I-22", "I-24", "I-25", "I-32"], satisfies=["R-16"])

b.component("C-27", "Japanese input", "Glossary, number/unit grammar, modality lexicon and particle-driven reorder that rewrite Japanese requirements into canonical English, with an audit table of every rewrite.",
            path="sekkei/engine/ja.py", satisfies=["R-20"])
b.component("C-30", "Structure pass", "Reads real-world document structure (tables, numbered headings, stories, labels, front matter) into the canonical Markdown shape the engine reads, reporting every fold.",
            path="sekkei/engine/structure.py", requires=["I-13"], satisfies=["R-23"])
b.component("C-31", "Exports", "Tracker issues (bodies, gh script, CSV) and an OpenAPI 3.0 skeleton derived from the design.",
            path="sekkei/export.py", requires=["I-1", "I-3"], satisfies=["R-24"])
b.component("C-32", "Domain model", "Entities with typed fields, relations, state machines and invariants read from the sentences (parenthesised attribute lists, 'with A, B and C', possessives, transactional and state verbs, arrow lists); aggregates by relation.",
            path="sekkei/engine/domain.py", requires=["I-13", "I-15"], satisfies=["R-13", "R-15"])
b.component("C-28", "Deliverables", "Executive summary, ADRs, C4, risk register, FMEA, roadmap, RACI, SLOs, cost model and runbooks derived from the design and the notes.",
            path="sekkei/deliverables.py", requires=["I-1", "I-3", "I-4", "I-13"], satisfies=["R-21"])
b.component("C-29", "Red team", "Adversarial self-audit: re-runs the engine on perturbed requirements and compares design shapes; contradictions, lost numbers, assumption load, determinism.",
            path="sekkei/redteam.py", requires=["I-1", "I-13", "I-19"], satisfies=["R-22"])

# --- interfaces (operation names are the real function names; sekkei check verifies them) ---
b.interface("I-27", "Japanese input API", owner="C-27", kind="module", operations=[
    op("is_japanese", [("text", "str")], "bool"),
    op("normalise", [("text", "str")], "Normalised: text, rewrites, untranslated, title, sources"),
    op("rewrite_sentence", [("src", "str")], "Rewrite (source, english, untranslated)"),
    op("numbers", [("s", "str")], "str with Japanese quantities rewritten"),
])
b.interface("I-30", "Structure pass API", owner="C-30", kind="module", operations=[
    op("canonicalise", [("text", "str")], "Canonical: text, notes, tentative, todos, alternatives, deadline, rationales"),
    op("story_actor", [("text", "str")], "str"),
])
b.interface("I-32", "Domain model API", owner="C-32", kind="module", operations=[
    op("extract", [("an", "Analysis"), ("functional_units", "list[ReqUnit] | None"), ("limit", "int")], "list[DEntity]"),
    op("aggregates", [("ents", "list[DEntity]")], "list[list[DEntity]]"),
    op("to_markdown", [("ents", "list[DEntity]")], "Markdown"),
    op("singular", [("n", "str")], "str"),
    op("field_type", [("name", "str")], "str"),
])
b.interface("I-31", "Exports API", owner="C-31", kind="module", operations=[
    op("issues", [("d", "Design")], "dict: file name -> text"),
    op("issue_body", [("d", "Design"), ("wp", "WorkPackage")], "Markdown"),
    op("openapi", [("d", "Design")], "dict (OpenAPI 3.0.3 document)"),
    op("openapi_json", [("d", "Design")], "str"),
])
b.interface("I-28", "Deliverables API", owner="C-28", kind="module", operations=[
    op("package", [("result", "EngineResult"), ("prices", "dict | None")], "Package: files (name -> text); write(out) -> paths"),
    op("cost_lines", [("design", "Design"), ("notes", "Notes"), ("prices", "dict | None")], "list[CostLine]"),
    op("fmea", [("design", "Design")], "Markdown"),
    op("slos", [("design", "Design")], "Markdown"),
])
b.interface("I-29", "Red team API", owner="C-29", kind="module", operations=[
    op("run", [("text", "str"), ("base", "EngineResult | None")], "RedTeam: findings (rule, severity, subject, message, evidence), runs"),
    op("shape", [("d", "Design")], "dict: the design minus requirement ids"),
])
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
    op("sequence", [("design", "Design"), ("flow_id", "str")], "Mermaid sequenceDiagram of one flow", ["KeyError for an unknown flow"]),
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
b.interface("I-9", "Model drafting API", owner="C-9", kind="module", operations=[
    op("get_backend", [("name", "str | None"), ("model", "str | None")], "Backend (claude-code | anthropic)", ["RuntimeError if none is available"]),
    op("architect_prompt", [("include_schema", "bool"), ("include_rules", "bool")], "str"),
    op("draft", [("requirements_text", "str"), ("backend", "Backend"), ("rounds", "int")], "DraftResult", ["RuntimeError from the backend"]),
    op("review", [("design", "Design"), ("requirements_text", "str"), ("backend", "Backend")], "list[ReviewFinding]"),
    op("revise", [("design", "Design"), ("findings", "list[ReviewFinding]"), ("requirements_text", "str"), ("backend", "Backend"), ("rounds", "int")], "DraftResult"),
    op("design", [("requirements_text", "str"), ("backend", "Backend"), ("rounds", "int"), ("review_rounds", "int")], "DesignResult"),
    op("extract_json", [("text", "str")], "dict", ["DesignError if no JSON object"]),
])
b.interface("I-13", "Text analysis API", owner="C-13", kind="module", stability="stable", operations=[
    op("segment", [("text", "str")], "list[Sentence] with section, modality, quantities, actors, verbs, nouns"),
    op("quantities", [("text", "str")], "list[Quantity] (rate | latency | duration | count | size | percent | factor | code | number)"),
    op("modality", [("text", "str")], "'must' | 'should' | 'could' | ''"),
    op("tokens", [("text", "str")], "list[str]"),
    op("per_second", [("q", "Quantity")], "float | None: a rate normalised to per second"),
    op("verb_of", [("word", "str")], "lexicon verb or ''"),
    op("title_of", [("text", "str")], "str"),
    op("slug", [("text", "str")], "str"),
])
b.interface("I-14", "Catalogue", owner="C-14", kind="module", stability="stable", operations=[
    op("Archetype", [], "class: key, name, responsibility, kind, layer, needs, ops, iface_kind"),
    op("Pattern", [], "class: id, signals, archetypes, entities, flows, decisions, risks"),
    op("DecisionPoint", [], "class: options with fit per quality, needs/excludes/bonus_when constraint tokens"),
    op("Tactic", [], "class: quality signals, archetypes, decisions, acceptance template, convention"),
    op("Layout", [], "class: module/test path templates and commands per language"),
])
b.interface("I-15", "Analysis API", owner="C-15", kind="module", operations=[
    op("analyse", [("text", "str")], "Analysis: requirements (ReqUnit), patterns, qualities, constraints, languages, team size, unrecognised, assumptions"),
])
b.interface("I-16", "Synthesis API", owner="C-16", kind="module", operations=[
    op("synthesise", [("an", "Analysis"), ("forced_decisions", "dict | None"), ("owner_overrides", "dict | None")], "Synthesis: design, trace, generic component ids, log, placements, close_calls"),
])
b.interface("I-17", "Evaluation API", owner="C-17", kind="module", operations=[
    op("score_option", [("opt", "Option"), ("qualities", "dict"), ("constraints", "set")], "Scored(score, available, reason)"),
    op("decide", [("dp", "DecisionPoint"), ("qualities", "dict"), ("constraints", "set"), ("forced", "str | None")], "(best, ranked, rationale, consequences); forced names the winner"),
    op("review", [("design", "Design"), ("an", "Analysis"), ("generic_components", "list[str]")], "Review (unrecognised, unaddressed, generic, assumptions, notes)"),
])
b.interface("I-18", "Repair API", owner="C-18", kind="module", operations=[
    op("repair", [("design", "Design"), ("max_passes", "int")], "(design, remaining diagnostics, repairs applied)"),
])
b.interface("I-19", "Engine API", owner="C-19", kind="module", stability="stable", operations=[
    op("design", [("text", "str"), ("assume", "bool"), ("overrides", "Overrides | None")], "EngineResult: design, analysis, review, notes, answers, placements, close_calls, diagnostics, trace; ok when no lint error"),
    op("ask", [("text", "str")], "list[Question]"),
])
b.interface("I-24", "Answers API", owner="C-24", kind="module", operations=[
    op("answer", [("q", "Question"), ("an", "Analysis")], "Answer | None (answer text, bullets to append, options, rationale, evidence, if_wrong, patterns)"),
    op("answers", [("qs", "list[Question]"), ("an", "Analysis")], "list[Answer]"),
    op("augment", [("text", "str"), ("ans", "list[Answer]")], "requirements text with the answers appended under engine-marked sections"),
    op("answers_markdown", [("ans", "list[Answer]")], "str"),
])
b.interface("I-26", "Interview API", owner="C-26", kind="module", operations=[
    op("Interview", [], "class: add(text), pending() -> [Prompt], reply(prompt, text), result(), status(), undo(), to_state()/from_state(), write_outputs(dir)"),
    op("canonical_bullet", [("qid", "str"), ("raw", "str")], "(section, bullet) the analyser recognises"),
    op("classify_free_text", [("text", "str")], "list[(section, bullet)]"),
    op("run_cli", [("inp", "IO"), ("out", "IO"), ("root", "Path"), ("base_file", "Path | None"), ("out_dir", "Path | None")], "exit code; reads replies, saves .sekkei/interview.json after every turn"),
])
b.interface("I-25", "Owners API", owner="C-25", kind="module", operations=[
    op("place", [("u", "ReqUnit"), ("d", "Design"), ("layout", "Layout"), ("cid", "dict"), ("iid", "dict"), ("requires", "dict")], "Placement (owners, how, detail, created); may add a component and interface to the design"),
    op("placements_markdown", [("ps", "list[Placement]"), ("d", "Design")], "str"),
])
b.interface("I-20", "Gap questions API", owner="C-20", kind="module", operations=[
    op("questions", [("an", "Analysis")], "list[Question] (id, topic, question, why, assumption, affects)"),
    op("questions_markdown", [("qs", "list[Question]")], "Markdown table"),
])
b.interface("I-21", "Sizing API", owner="C-21", kind="module", operations=[
    op("capacity", [("an", "Analysis")], "Capacity: estimates with formula and inputs, assumptions, missing inputs"),
    op("effort", [("design", "Design"), ("an", "Analysis")], "Effort: person-days, critical path, calendar, waves"),
    op("capacity_markdown", [("cap", "Capacity")], "str"),
    op("effort_markdown", [("e", "Effort")], "str"),
])
b.interface("I-22", "Threat model API", owner="C-22", kind="module", operations=[
    op("threat_table", [("design", "Design")], "list[(component id, name, Threat)]"),
    op("inject_risks", [("design", "Design")], "int risks added (idempotent)"),
    op("threats_markdown", [("design", "Design")], "str"),
])
b.interface("I-23", "Notes API", owner="C-23", kind="module", operations=[
    op("notes", [("design", "Design"), ("an", "Analysis"), ("review", "Review")], "Notes with to_markdown()"),
    op("analysis_markdown", [("an", "Analysis")], "str", description="the module also exports the constant REQUIREMENTS_TEMPLATE"),
])
b.interface("I-10", "Command line", owner="C-10", kind="cli", operations=[
    op("sekkei init [dir]", output="starter design.json"),
    op("sekkei lint [-d FILE] [--json] [--strict] [--disable RULE|GROUP]", output="diagnostics; exit 1 on errors"),
    op("sekkei render / graph / matrix", output="DESIGN.md, Mermaid/DOT, traceability"),
    op("sekkei brief WP / plan [--json]", output="brief; waves, critical path, ready packages"),
    op("sekkei check [--root DIR] / scope WP FILES", output="drift findings; out-of-scope files"),
    op("sekkei accept REPORT [--force] / status / next / start WP", output="state transitions; stale briefs are refused"),
    op("sekkei diff OLD [-d NEW]", output="element changes and the affected packages; exit 1 if any"),
    op("sekkei schema / rules / prompt", output="JSON Schema; rule table; architect prompt"),
    op("sekkei design REQ.md [-o design.json] [--render DESIGN.md] [--review NOTES.md] [--trace TRACE.json] [--augmented REQ.md] [--no-assume]", output="a complete, lint-clean design without any model, plus the architect's notes; open questions answered unless --no-assume"),
    op("sekkei ask REQ.md [--json] / sekkei template [-o requirements.md]", output="the open questions; the requirements template"),
    op("sekkei interview [REQ.md] [--root DIR] [--out-dir DIR] [--script FILE]", output="design in dialogue; /design writes design.json, DESIGN.md, NOTES.md, requirements.md"),
    op("sekkei draft REQ.md [--review] [--backend claude-code|anthropic]", output="optional model-based draft"),
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
b.flow("F-6", "Design from a requirements text", trigger="sekkei design REQ.md", steps=[
    ("C-10", "C-19", "I-19", "run the engine"),
    ("C-19", "C-15", "I-15", "analyse the text"),
    ("C-15", "C-13", "I-13", "segment sentences, quantities, modality"),
    ("C-15", "C-14", "I-14", "match patterns, qualities, constraints"),
    ("C-19", "C-16", "I-16", "synthesise the design"),
    ("C-16", "C-17", "I-17", "score every decision point"),
    ("C-19", "C-18", "I-18", "lint and repair"),
    ("C-19", "C-17", "I-17", "review the gaps"),
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
b.decision("D-6", "A deterministic engine rather than a model as the design engine",
           context="The engine must produce complete designs; a model would be more fluent but not reproducible or explainable.",
           options=[option("rule-based engine over a catalogue", pros=["deterministic", "every element traced to sentences and rules", "offline, no cost", "says what it did not recognise"],
                           cons=["no understanding of prose", "finite catalogue; novel domains get a generic decomposition"]),
                    option("model-based drafting only", pros=["fluent on any domain"], cons=["not reproducible", "invents requirements", "needs credentials"]),
                    option("model drafting checked by the linter", pros=["fluent and structurally checked"], cons=["semantic errors pass the linter"])],
           choice="rule-based engine over a catalogue", rationale="The harness exists to hold a line a model cannot hold for itself; the engine keeps that property. Model drafting stays as an optional extra.",
           consequences="Domains outside the catalogue are handled by the layered fallback and flagged in the review; growing the catalogue is the improvement path.",
           affects=["C-14", "C-16", "C-19"])
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
b.risk("K-4", "The catalogue does not cover a domain, so the engine produces a generic decomposition that looks complete.", likelihood="high", impact="medium",
       mitigation="Unrecognised requirements and generic components are listed in the review and as a risk in the design; the fixtures include a novel domain to keep this honest.", affects=["C-14", "C-17"])
b.risk("K-5", "The verb/object heuristics derive a wrong operation name from an unusual sentence.", likelihood="medium", impact="low",
       mitigation="Operations carry the sentence they came from in their description; the fixtures assert the expected operations.", affects=["C-16"])

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
b.work_package("WP-9", "Design engine", goal="Implement the model backends, the architect and review prompts, and the draft/review/revise pipeline with lint feedback, testable offline through a fake backend.",
               components=["C-9"], implements=["I-9"], depends_on=["WP-3"], satisfies=["R-10"], size="M",
               files=["sekkei/llm.py", "tests/test_llm.py"],
               acceptance=[check("A-9", "design-engine tests pass with the fake backend, including the full draft/review/revise pipeline", command=T + "tests/test_llm.py")])
b.work_package("WP-12", "Engine: text and catalogue", goal="Implement the requirements-text analysis (segmentation, quantity grammar, modality, verbs) and the knowledge base of patterns, archetypes, decisions, tactics and layouts.",
               components=["C-13", "C-14"], implements=["I-13", "I-14"], depends_on=["WP-1"], satisfies=["R-13"], size="L",
               files=["sekkei/engine/text.py", "sekkei/engine/catalog.py", "tests/test_engine.py", "tests/fixtures"],
               acceptance=[check("A-14", "text tests pass: quantities, sections, modality, verb inflection", command=T + "tests/test_engine.py -k 'quantities or segmentation'")])
b.work_package("WP-13", "Engine: analysis and evaluation", goal="Implement requirement-unit analysis with pattern/quality/constraint matching, decision scoring and the self-review.",
               components=["C-15", "C-17"], implements=["I-15", "I-17"], depends_on=["WP-12", "WP-18", "WP-20"], satisfies=["R-13", "R-15"], size="M",
               files=["sekkei/engine/analysis.py", "sekkei/engine/evaluate.py"],
               acceptance=[check("A-15", "analysis tests pass on the fixtures", command=T + "tests/test_engine.py -k analysis")])
b.work_package("WP-16", "Engine: questions, sizing, answers and owners", goal="Implement the gap questions, capacity/effort estimates, the answer rules for every question (which use the implied rate) and the owner placement for unrecognised requirements.",
               components=["C-20", "C-21", "C-24", "C-25"], implements=["I-20", "I-21", "I-24", "I-25"], depends_on=["WP-2", "WP-13"], satisfies=["R-16", "R-17", "R-18"], size="L",
               files=["sekkei/engine/gaps.py", "sekkei/engine/sizing.py", "sekkei/engine/answers.py", "sekkei/engine/owners.py", "tests/test_autonomy.py"],
               acceptance=[check("A-19", "autonomy tests pass: no open question is left on a two-line spec, evidence beats defaults, every unrecognised requirement is owned or gets a synthesised component", command=T + "tests/test_autonomy.py")])
b.work_package("WP-17", "Interview", goal="Implement the dialogue: prompt ordering with proposals, canonical bullets, overrides, undo, saved state, the read-eval loop and the CLI command.",
               components=["C-26"], implements=["I-26"], depends_on=["WP-4", "WP-14", "WP-16"], satisfies=["R-19"], size="M",
               files=["sekkei/engine/interview.py", "tests/test_interview.py"],
               acceptance=[check("A-20", "interview tests pass: architect order, Enter accepts, canonical bullets are recognised, named owners override, decisions can be forced, state round-trips, scripted session", command=T + "tests/test_interview.py")])
b.work_package("WP-15", "Engine: architect's notes", goal="Implement the STRIDE-lite threat model and the notes report with the requirements template.",
               components=["C-22", "C-23"], implements=["I-22", "I-23"], depends_on=["WP-13", "WP-16", "WP-21"], satisfies=["R-16"], size="M",
               files=["sekkei/engine/threats.py", "sekkei/engine/report.py", "tests/test_notes.py"],
               acceptance=[check("A-18", "notes tests pass: a minimal input yields the architect's questions, a complete spec leaves few, answering a question changes only its target, threats become risks", command=T + "tests/test_notes.py")])
b.work_package("WP-14", "Engine: synthesis, repair and facade", goal="Implement the synthesis of a full design from an analysis, the lint-driven repair loop and the engine facade; prove determinism, fidelity and lint-cleanliness on every fixture.",
               components=["C-16", "C-18", "C-19"], implements=["I-16", "I-18", "I-19"], depends_on=["WP-3", "WP-13", "WP-15", "WP-16", "WP-20", "WP-21"], satisfies=["R-13", "R-14", "R-15", "R-16", "R-17", "R-18"], size="L",
               files=["sekkei/engine/synthesis.py", "sekkei/engine/repair.py", "sekkei/engine/__init__.py"],
               acceptance=[check("A-16", "engine tests pass: every fixture lint-clean, deterministic, faithful; the webhook design has the expected architecture", command=T + "tests/test_engine.py"),
                           check("A-17", "R-14: two runs on the same text produce identical JSON", kind="metric", metric="R-14")])
b.work_package("WP-21", "Engine: domain model", goal="Read entities with typed fields, relations, state machines and invariants from the sentences; group them into aggregates.",
               components=["C-32"], implements=["I-32"], depends_on=["WP-13", "WP-16"], satisfies=["R-13", "R-15"], size="M",
               files=["sekkei/engine/domain.py", "tests/test_domain.py"],
               acceptance=[check("A-32", "domain tests pass: typed fields, states and invariants from the trading spec; no proper nouns, verbs or adjectives as entities; aggregates as components", command=T + "tests/test_domain.py")])
b.work_package("WP-11", "Diff", goal="Compare two design versions element by element and map the changes to the work packages whose briefs are stale.",
               components=["C-12"], implements=["I-12"], depends_on=["WP-1"], satisfies=["R-12"], size="S",
               files=["sekkei/diff.py", "tests/test_diff.py"],
               acceptance=[check("A-13", "diff tests pass, including that a stale brief blocks acceptance", command=T + "tests/test_diff.py")])
b.work_package("WP-18", "Japanese input", goal="Rewrite Japanese requirements into canonical English deterministically with an audit table; design a Japanese spec lint-clean.",
               components=["C-27"], implements=["I-27"], satisfies=["R-20"], size="M",
               files=["sekkei/engine/ja.py", "tests/test_ja.py", "examples/ja/zaiko.md"],
               acceptance=[check("A-27", "Japanese tests pass (sentences, numbers, document, design, determinism)", command=T + "tests/test_ja.py")])
b.work_package("WP-20", "Structure pass and exports", goal="Read specifications as engineers write them; export packages to trackers and interfaces to OpenAPI.",
               components=["C-30", "C-31"], implements=["I-30", "I-31"], depends_on=["WP-1", "WP-2", "WP-12"], satisfies=["R-23", "R-24"], size="M",
               files=["sekkei/engine/structure.py", "sekkei/export.py", "tests/test_structure.py", "tests/test_export.py", "examples/real/"],
               acceptance=[check("A-30", "structure tests pass (tables, stories, labels, real specs lint-clean and deterministic, fuzz)", command=T + "tests/test_structure.py"),
                           check("A-31", "export tests pass (issues in dependency order, OpenAPI shape)", command=T + "tests/test_export.py")])
b.work_package("WP-19", "Deliverables and red team", goal="Derive the hand-over package from the design and attack the design with the requirements as oracle.",
               components=["C-28", "C-29"], implements=["I-28", "I-29"], depends_on=["WP-14", "WP-17"], satisfies=["R-21", "R-22"], size="M",
               files=["sekkei/deliverables.py", "sekkei/redteam.py", "tests/test_deliverables.py", "tests/test_redteam.py"],
               acceptance=[check("A-28", "deliverables tests pass (every document, determinism, no guessed prices, one calendar formula)", command=T + "tests/test_deliverables.py"),
                           check("A-29", "red-team tests pass (inert sentence found on the document-search spec, contradiction, lost number)", command=T + "tests/test_redteam.py")])
b.work_package("WP-10", "CLI", goal="Expose every operation on the command line with exit codes and JSON output, and prove the whole loop end to end.",
               components=["C-10"], implements=["I-10"], depends_on=["WP-6", "WP-7", "WP-8", "WP-9", "WP-11", "WP-14", "WP-17", "WP-19", "WP-20"], satisfies=["R-11", "R-8", "R-12"], size="M",
               files=["sekkei/cli.py", "sekkei/__main__.py", "tests/test_cli.py", "tests/test_self.py"],
               acceptance=[check("A-10", "CLI round-trip test passes: init, lint, render, plan, brief, accept, next", command=T + "tests/test_cli.py"),
                           check("A-11", "self design lints clean and drift check on the repository reports no error", command=T + "tests/test_self.py"),
                           check("A-12", "lint + check on examples/self run within the target", kind="metric", metric="R-8")])

if __name__ == "__main__":
    out = Path(__file__).with_name("design.json")
    b.save(out)
    print(f"wrote {out}")
