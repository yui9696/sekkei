"""sekkei — a design-first harness for LLM coding agents.

Public surface::

    import sekkei
    design = sekkei.load("design.json")            # or a .py DSL file
    diags  = sekkei.lint(design)                   # deterministic rules, stable ids
    text   = sekkei.render_brief(design, "WP-1")   # self-contained brief for one package
    md     = sekkei.render_markdown(design)        # DESIGN.md
    drift  = sekkei.check(design, root=".")        # design vs code
"""
from pathlib import Path

from .brief import render_brief
from .drift import check
from .graph import critical_path, ready_packages, traceability, waves
from .model import Design, DesignError, dump, dumps, from_dict, json_schema, loads, to_dict
from .model import load as load_json
from .render import render_markdown
from .rules import RULES, Diagnostic, has_errors, lint

__version__ = "0.1.0"


def load(path):
    """Load a design from a ``.json`` file or a ``.py`` DSL file (see ``sekkei.dsl``)."""
    if Path(path).suffix == ".py":
        from .dsl import load_python

        return load_python(path)
    return load_json(path)


__all__ = [
    "Design", "DesignError", "Diagnostic", "RULES", "check", "critical_path", "dump", "dumps",
    "from_dict", "has_errors", "json_schema", "lint", "load", "load_json", "loads", "ready_packages",
    "render_brief", "render_markdown", "to_dict", "traceability", "waves",
]
