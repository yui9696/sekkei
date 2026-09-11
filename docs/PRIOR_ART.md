# Prior art: spec-driven development tooling, 2026-09-11

Checked before writing sekkei, so that it fills a gap instead of duplicating a tool.
Tags: **[confirmed]** — the primary artefact (README or command template) was fetched
and read; **[reported]** — a secondary source says so.

## What exists

| Tool | Form | Where consistency is checked |
|---|---|---|
| GitHub **Spec Kit** [confirmed] | Markdown spec / plan / tasks in `.specify/`, slash commands `/speckit.specify`, `.plan`, `.tasks`, `.analyze`, `.converge` | `/speckit.analyze` is a prompt: it asks the model to "create internal representations", map tasks to requirements "by keyword / explicit reference patterns", and report coverage computed from those inferred mappings. No dependency-cycle or build-order computation. `/speckit.converge` asks the model to assess the codebase against the spec. |
| **OpenSpec** [confirmed README] | Markdown specs with requirements and scenarios; proposal-first workflow with delta markers | The README does not describe what `openspec validate` checks; nothing about cross-references, coverage or code comparison is documented there. |
| **BMAD-METHOD** [confirmed README] | Multi-agent personas (analyst, PM, architect, …), file-based context passing | Process and templates; no deterministic validation of architecture documents is described. |
| AWS **Kiro** [reported] | requirements.md / design.md / tasks.md generated in the IDE | Model-generated documents; validation is the model's. |
| Requirements-traceability suites (Parasoft, DOORS-style) [reported] | Enterprise, safety-critical | Deterministic traceability matrices exist, but they are not designed around LLM agents, work-package briefs or agent write scopes. |
| Architecture-erosion checkers (e.g. the "Drift" GitHub Action, AST-based doc/code sync tools) [reported] | Code-side analysis | Detect duplicate code or stale docstrings; they do not take a design graph as input. |

## The gap

None of the LLM-oriented tools above has:

1. a **machine-checkable design graph** (requirements ↔ components ↔ interfaces ↔ work
   packages ↔ acceptance) with a deterministic linter whose rules are individually
   tested;
2. a **write scope per work package** with a parallel-conflict check;
3. **generated, self-contained briefs** derived from the graph rather than written by hand
   or by the model;
4. a **drift check from the design to the code** (declared operations exist, no undeclared
   inter-component imports).

sekkei does those four things and nothing that the tools above already do well
(personas, IDE integration, conversational elicitation).

## What sekkei does not claim

- It is not "the first" anything in requirements traceability; that field is decades
  old. The claim is narrower: a dependency-free, agent-oriented, tested implementation.
- Its wording rules (group Q) are heuristics, labelled as such.
- Its drift checker covers Python only.

Sources consulted: github.com/github/spec-kit (README and
`templates/commands/analyze.md`), github.com/Fission-AI/OpenSpec (README),
github.com/bmad-code-org/BMAD-METHOD (README), plus vendor comparison articles for the
landscape (not used as evidence of behaviour).
