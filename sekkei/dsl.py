"""A small Python DSL for authoring designs by hand.

Example::

    from sekkei.dsl import DesignBuilder, op, check

    b = DesignBuilder("todo-api", summary="A tiny HTTP to-do service")
    b.requirement("R-1", "A user can create a to-do item with a title.")
    b.component("C-1", "API", "HTTP surface", kind="service", path="app/api.py", satisfies=["R-1"])
    b.interface("I-1", "REST API", owner="C-1", kind="http",
                operations=[op("POST /todos", inputs=[("title", "str")], output="Todo")])
    b.work_package("WP-1", "Build the API", goal="Serve POST /todos backed by an in-memory list",
                   components=["C-1"], implements=["I-1"], satisfies=["R-1"],
                   files=["app/api.py", "tests/test_api.py"],
                   acceptance=[check("A-1", "tests pass", command="pytest -q")])
    design = b.build()

Save with ``b.save("design.json")`` or load a ``.py`` file directly with
``sekkei lint design.py`` (the file must define ``design`` or ``build()``).
"""
from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Union

from .model import (
    Acceptance,
    Component,
    Conventions,
    Decision,
    Design,
    Entity,
    FieldDef,
    Flow,
    Interface,
    Metric,
    Operation,
    Option,
    Param,
    Requirement,
    Risk,
    Step,
    WorkPackage,
)

_ParamLike = Union[Param, tuple[str, str], tuple[str, str, str], str]


def _param(p: _ParamLike) -> Param:
    if isinstance(p, Param):
        return p
    if isinstance(p, str):
        return Param(name=p)
    return Param(*p)


def op(
    name: str,
    inputs: Sequence[_ParamLike] = (),
    output: str = "",
    errors: Sequence[str] = (),
    pre: str = "",
    post: str = "",
    description: str = "",
) -> Operation:
    return Operation(name, [_param(p) for p in inputs], output, list(errors), pre, post, description)


def check(id_: str, description: str, kind: str = "test", command: str = "", metric: str = "") -> Acceptance:
    return Acceptance(id_, description, kind, command, metric)


def option(name: str, pros: Sequence[str] = (), cons: Sequence[str] = ()) -> Option:
    return Option(name, list(pros), list(cons))


def field_(name: str, type_: str = "", constraints: str = "", description: str = "") -> FieldDef:
    return FieldDef(name, type_, constraints, description)


def step(from_: str, to: str, via: str, description: str = "") -> Step:
    return Step(from_, to, via, description)


class DesignBuilder:
    def __init__(self, name: str, version: str = "0.1.0", summary: str = ""):
        self.design = Design(name=name, version=version, summary=summary)

    # -- top level ---------------------------------------------------------

    def goal(self, *goals: str) -> "DesignBuilder":
        self.design.goals.extend(goals)
        return self

    def non_goal(self, *goals: str) -> "DesignBuilder":
        self.design.non_goals.extend(goals)
        return self

    def conventions(
        self,
        language: str = "",
        test_command: str = "",
        lint_command: str = "",
        rules: Iterable[str] = (),
        definition_of_done: Iterable[str] = (),
    ) -> "DesignBuilder":
        self.design.conventions = Conventions(language, test_command, lint_command, list(rules), list(definition_of_done))
        return self

    # -- elements ----------------------------------------------------------

    def requirement(
        self,
        id_: str,
        statement: str,
        kind: str = "functional",
        priority: str = "must",
        metric: Optional[tuple[str, str] | tuple[str, str, str] | Metric] = None,
        rationale: str = "",
    ) -> Requirement:
        m = metric if isinstance(metric, Metric) or metric is None else Metric(*metric)
        r = Requirement(id_, statement, kind, priority, m, rationale)
        self.design.requirements.append(r)
        return r

    def component(
        self,
        id_: str,
        name: str,
        responsibility: str,
        kind: str = "module",
        path: str = "",
        requires: Iterable[str] = (),
        satisfies: Iterable[str] = (),
        tags: Iterable[str] = (),
    ) -> Component:
        c = Component(id_, name, responsibility, kind, path, list(requires), list(satisfies), list(tags))
        self.design.components.append(c)
        return c

    def interface(
        self,
        id_: str,
        name: str,
        owner: str,
        kind: str = "module",
        operations: Iterable[Operation] = (),
        stability: str = "draft",
        description: str = "",
    ) -> Interface:
        i = Interface(id_, name, owner, kind, list(operations), stability, description)
        self.design.interfaces.append(i)
        return i

    def entity(self, id_: str, name: str, owner: str, fields: Iterable[FieldDef] = (), description: str = "") -> Entity:
        e = Entity(id_, name, owner, list(fields), description)
        self.design.entities.append(e)
        return e

    def flow(self, id_: str, name: str, trigger: str = "", steps: Iterable[Step | tuple[str, str, str]] = ()) -> Flow:
        f = Flow(id_, name, trigger, [s if isinstance(s, Step) else Step(*s) for s in steps])
        self.design.flows.append(f)
        return f

    def decision(
        self,
        id_: str,
        title: str,
        context: str = "",
        options: Iterable[Option | str] = (),
        choice: str = "",
        rationale: str = "",
        consequences: str = "",
        affects: Iterable[str] = (),
        status: str = "accepted",
    ) -> Decision:
        opts = [o if isinstance(o, Option) else Option(o) for o in options]
        dec = Decision(id_, title, context, opts, choice, rationale, consequences, list(affects), status)
        self.design.decisions.append(dec)
        return dec

    def risk(
        self,
        id_: str,
        description: str,
        likelihood: str = "medium",
        impact: str = "medium",
        mitigation: str = "",
        affects: Iterable[str] = (),
    ) -> Risk:
        k = Risk(id_, description, likelihood, impact, mitigation, list(affects))
        self.design.risks.append(k)
        return k

    def work_package(
        self,
        id_: str,
        title: str,
        goal: str = "",
        components: Iterable[str] = (),
        implements: Iterable[str] = (),
        depends_on: Iterable[str] = (),
        satisfies: Iterable[str] = (),
        files: Iterable[str] = (),
        size: str = "M",
        acceptance: Iterable[Acceptance] = (),
        notes: str = "",
    ) -> WorkPackage:
        w = WorkPackage(
            id_, title, goal, list(components), list(implements), list(depends_on), list(satisfies),
            list(files), size, list(acceptance), notes,
        )
        self.design.work_packages.append(w)
        return w

    # -- output ------------------------------------------------------------

    def build(self) -> Design:
        return self.design

    def save(self, path: str | Path) -> None:
        from .model import dump

        dump(self.design, path)


def load_python(path: str | Path) -> Design:
    """Run a ``.py`` file and take its ``design`` (Design or DesignBuilder) or ``build()`` result."""
    ns: dict[str, Any] = runpy.run_path(str(path))
    obj = ns.get("design")
    if obj is None and callable(ns.get("build")):
        obj = ns["build"]()
    if isinstance(obj, DesignBuilder):
        obj = obj.build()
    if not isinstance(obj, Design):
        raise ValueError(f"{path}: define `design` (a Design or DesignBuilder) or a `build()` function")
    return obj
