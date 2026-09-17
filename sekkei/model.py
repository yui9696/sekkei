"""The design model: dataclasses, tolerant loading, serialisation, JSON Schema.

The loader is deliberately *tolerant*: it records unknown keys and fills missing
strings with "" instead of raising, so that the linter (``sekkei.rules``) can report
every problem at once with a stable rule id. It raises ``DesignError`` only for
type mismatches that would make the model meaningless (e.g. a list where an object
was expected).
"""
from __future__ import annotations

import json
import types
import typing
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Optional, Union

SCHEMA_VERSION = "1"

# ---------------------------------------------------------------------------
# Vocabularies (one place; used by the loader, the rules and the JSON Schema)
# ---------------------------------------------------------------------------

REQUIREMENT_KINDS = ("functional", "nonfunctional", "constraint")
PRIORITIES = ("must", "should", "could")
COMPONENT_KINDS = ("module", "service", "library", "cli", "datastore", "external", "ui", "job")
INTERFACE_KINDS = ("function", "class", "module", "http", "cli", "event", "file", "schema")
STABILITIES = ("draft", "stable")
DECISION_STATUSES = ("proposed", "accepted", "superseded", "rejected")
LEVELS = ("low", "medium", "high")
SIZES = ("S", "M", "L")
ACCEPTANCE_KINDS = ("test", "command", "review", "metric")
PACKAGE_STATUSES = ("todo", "in_progress", "done", "blocked")

#: collection name -> conventional id prefix (enforced as a warning, rule S003)
ID_PREFIXES = {
    "requirements": "R-",
    "components": "C-",
    "interfaces": "I-",
    "entities": "E-",
    "flows": "F-",
    "decisions": "D-",
    "risks": "K-",
    "work_packages": "WP-",
    "acceptance": "A-",
}

COLLECTIONS = (
    "requirements",
    "components",
    "interfaces",
    "entities",
    "flows",
    "decisions",
    "risks",
    "work_packages",
)


class DesignError(ValueError):
    """Raised when a design file cannot be turned into a model at all."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Metric:
    name: str = ""
    target: str = ""
    unit: str = ""


def metric_text(m: "Metric") -> str:
    """'p95 latency <= 300 ms' — the unit printed once even when the target already carries it."""
    unit = (m.unit or "").strip()
    target = (m.target or "").strip()
    tail = "" if not unit or unit in target else " " + unit
    return f"{m.name} {target}{tail}".strip()


@dataclass
class Requirement:
    id: str = ""
    statement: str = ""
    kind: str = "functional"
    priority: str = "must"
    metric: Optional[Metric] = None
    rationale: str = ""


@dataclass
class FieldDef:
    name: str = ""
    type: str = ""
    constraints: str = ""
    description: str = ""


@dataclass
class Entity:
    id: str = ""
    name: str = ""
    owner: str = ""
    fields: list[FieldDef] = field(default_factory=list)
    description: str = ""


@dataclass
class Param:
    name: str = ""
    type: str = ""
    description: str = ""


@dataclass
class Operation:
    name: str = ""
    inputs: list[Param] = field(default_factory=list)
    output: str = ""
    errors: list[str] = field(default_factory=list)
    pre: str = ""
    post: str = ""
    description: str = ""


@dataclass
class Interface:
    id: str = ""
    name: str = ""
    owner: str = ""
    kind: str = "module"
    operations: list[Operation] = field(default_factory=list)
    stability: str = "draft"
    description: str = ""


@dataclass
class Component:
    id: str = ""
    name: str = ""
    responsibility: str = ""
    kind: str = "module"
    path: str = ""
    requires: list[str] = field(default_factory=list)
    satisfies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class Step:
    from_: str = ""
    to: str = ""
    via: str = ""
    description: str = ""


@dataclass
class Flow:
    id: str = ""
    name: str = ""
    trigger: str = ""
    steps: list[Step] = field(default_factory=list)


@dataclass
class Option:
    name: str = ""
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)


@dataclass
class Decision:
    id: str = ""
    title: str = ""
    context: str = ""
    options: list[Option] = field(default_factory=list)
    choice: str = ""
    rationale: str = ""
    consequences: str = ""
    affects: list[str] = field(default_factory=list)
    status: str = "accepted"


@dataclass
class Risk:
    id: str = ""
    description: str = ""
    likelihood: str = "medium"
    impact: str = "medium"
    mitigation: str = ""
    affects: list[str] = field(default_factory=list)


@dataclass
class Acceptance:
    id: str = ""
    description: str = ""
    kind: str = "test"
    command: str = ""
    metric: str = ""


@dataclass
class WorkPackage:
    id: str = ""
    title: str = ""
    goal: str = ""
    components: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    satisfies: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    size: str = "M"
    acceptance: list[Acceptance] = field(default_factory=list)
    notes: str = ""


@dataclass
class Conventions:
    language: str = ""
    test_command: str = ""
    lint_command: str = ""
    rules: list[str] = field(default_factory=list)
    definition_of_done: list[str] = field(default_factory=list)


@dataclass
class Design:
    name: str = ""
    version: str = "0.1.0"
    summary: str = ""
    goals: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    conventions: Conventions = field(default_factory=Conventions)
    requirements: list[Requirement] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    interfaces: list[Interface] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    work_packages: list[WorkPackage] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    #: (json path, key) pairs the loader did not recognise; reported by rule S006
    unknown_keys: list[tuple[str, str]] = field(default_factory=list, repr=False, compare=False)

    # -- lookups ----------------------------------------------------------

    def index(self) -> dict[str, tuple[str, Any]]:
        """Map every id to ``(collection, object)``. Later duplicates win; S001 reports them."""
        out: dict[str, tuple[str, Any]] = {}
        for coll in COLLECTIONS:
            for obj in getattr(self, coll):
                out[obj.id] = (coll, obj)
        for wp in self.work_packages:
            for acc in wp.acceptance:
                out[acc.id] = ("acceptance", acc)
        return out

    def get(self, id_: str) -> Any:
        hit = self.index().get(id_)
        return hit[1] if hit else None

    def component(self, id_: str) -> Optional[Component]:
        return next((c for c in self.components if c.id == id_), None)

    def interface(self, id_: str) -> Optional[Interface]:
        return next((i for i in self.interfaces if i.id == id_), None)

    def requirement(self, id_: str) -> Optional[Requirement]:
        return next((r for r in self.requirements if r.id == id_), None)

    def work_package(self, id_: str) -> Optional[WorkPackage]:
        return next((w for w in self.work_packages if w.id == id_), None)

    def provided_by(self, component_id: str) -> list[Interface]:
        """Interfaces a component provides (= owns). Single source of truth: ``Interface.owner``."""
        return [i for i in self.interfaces if i.owner == component_id]

    def packages_building(self, component_id: str) -> list[WorkPackage]:
        return [w for w in self.work_packages if component_id in w.components]

    def packages_implementing(self, interface_id: str) -> list[WorkPackage]:
        return [w for w in self.work_packages if interface_id in w.implements]


# ---------------------------------------------------------------------------
# Loading (tolerant) and dumping
# ---------------------------------------------------------------------------

#: JSON key -> attribute name, per class (only where the JSON key is a Python keyword)
_ALIASES: dict[type, dict[str, str]] = {Step: {"from": "from_"}}
_PRIVATE_FIELDS = {"unknown_keys"}
_TOP_LEVEL_ALIASES = {"sekkei": "schema_version"}


def _hints(cls: type) -> dict[str, Any]:
    return typing.get_type_hints(cls)


def _unwrap_optional(tp: Any) -> tuple[Any, bool]:
    origin = typing.get_origin(tp)
    if origin is Union or origin is types.UnionType:
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return tp, False


def _hydrate(cls: type, data: Any, path: str, unknown: list[tuple[str, str]]) -> Any:
    if not isinstance(data, dict):
        raise DesignError(f"{path}: expected an object, got {type(data).__name__}")
    aliases = _ALIASES.get(cls, {})
    attr_by_key = {**{f.name: f.name for f in fields(cls)}, **aliases}
    if cls is Design:
        attr_by_key.update(_TOP_LEVEL_ALIASES)
    hints = _hints(cls)
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        attr = attr_by_key.get(key)
        if attr is None or attr in _PRIVATE_FIELDS:
            unknown.append((path, key))
            continue
        kwargs[attr] = _coerce(hints[attr], value, f"{path}.{key}", unknown)
    return cls(**kwargs)


def _coerce(tp: Any, value: Any, path: str, unknown: list[tuple[str, str]]) -> Any:
    tp, optional = _unwrap_optional(tp)
    if value is None:
        if optional:
            return None
        return "" if tp is str else ([] if typing.get_origin(tp) is list else _hydrate(tp, {}, path, unknown))
    origin = typing.get_origin(tp)
    if origin is list:
        (item_tp,) = typing.get_args(tp)
        if isinstance(value, str) and item_tp is str:
            value = [value]  # a lone string where a list of strings was expected
        if not isinstance(value, list):
            raise DesignError(f"{path}: expected a list, got {type(value).__name__}")
        return [_coerce(item_tp, v, f"{path}[{i}]", unknown) for i, v in enumerate(value)]
    if origin is tuple:
        return value
    if tp is str:
        if isinstance(value, (int, float, bool)):
            return str(value)
        if not isinstance(value, str):
            raise DesignError(f"{path}: expected a string, got {type(value).__name__}")
        return value
    if is_dataclass(tp):
        return _hydrate(tp, value, path, unknown)
    return value


def from_dict(data: dict[str, Any]) -> Design:
    unknown: list[tuple[str, str]] = []
    design = _hydrate(Design, data, "$", unknown)
    design.unknown_keys = unknown
    return design


def to_dict(obj: Any) -> Any:
    """Serialise a model object to plain JSON-compatible data (aliases restored, None dropped)."""
    if is_dataclass(obj) and not isinstance(obj, type):
        cls = type(obj)
        rev = {v: k for k, v in _ALIASES.get(cls, {}).items()}
        out: dict[str, Any] = {}
        if cls is Design:
            out["sekkei"] = obj.schema_version
        for f in fields(cls):
            if f.name in _PRIVATE_FIELDS or (cls is Design and f.name == "schema_version"):
                continue
            value = getattr(obj, f.name)
            if value is None:
                continue
            out[rev.get(f.name, f.name)] = to_dict(value)
        return out
    if isinstance(obj, list):
        return [to_dict(v) for v in obj]
    return obj


def loads(text: str) -> Design:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DesignError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DesignError("the design file must contain a JSON object")
    return from_dict(data)


def load(path: str | Path) -> Design:
    """Load a JSON design file. (``sekkei.load`` also accepts ``.py`` DSL files.)"""
    return loads(Path(path).read_text(encoding="utf-8"))


def dumps(design: Design) -> str:
    return json.dumps(to_dict(design), indent=2, ensure_ascii=False) + "\n"


def dump(design: Design, path: str | Path) -> None:
    Path(path).write_text(dumps(design), encoding="utf-8")


# ---------------------------------------------------------------------------
# JSON Schema (generated from the dataclasses so it cannot drift from them)
# ---------------------------------------------------------------------------

_ENUMS: dict[tuple[type, str], tuple[str, ...]] = {
    (Requirement, "kind"): REQUIREMENT_KINDS,
    (Requirement, "priority"): PRIORITIES,
    (Component, "kind"): COMPONENT_KINDS,
    (Interface, "kind"): INTERFACE_KINDS,
    (Interface, "stability"): STABILITIES,
    (Decision, "status"): DECISION_STATUSES,
    (Risk, "likelihood"): LEVELS,
    (Risk, "impact"): LEVELS,
    (WorkPackage, "size"): SIZES,
    (Acceptance, "kind"): ACCEPTANCE_KINDS,
}

_DOC: dict[tuple[type, str], str] = {
    (Requirement, "metric"): "Required for kind=nonfunctional: how the requirement is measured.",
    (Interface, "owner"): "Component id. The owner *provides* the interface; there is no separate provides list.",
    (Component, "path"): "Repo-relative file or directory that holds this component's code.",
    (Component, "requires"): "Interface ids this component calls.",
    (Component, "satisfies"): "Requirement ids this component helps satisfy.",
    (Step, "from_"): "Component id making the call.",
    (Step, "via"): "Interface id used; must be owned by `to` and required by `from`.",
    (WorkPackage, "files"): "Write scope: the only files/directories an agent may change while doing this package.",
    (WorkPackage, "implements"): "Interface ids this package implements; their owners must be in `components`.",
    (WorkPackage, "depends_on"): "Work-package ids that must be done first.",
    (Acceptance, "command"): "Shell command for kind=test|command; must exit 0.",
    (Acceptance, "metric"): "Requirement id (kind=nonfunctional) for kind=metric.",
    (Design, "schema_version"): "Schema version; serialised as the top-level key `sekkei`.",
}


def _schema_for(tp: Any, cls: type, name: str, defs: dict[str, Any]) -> dict[str, Any]:
    tp, _ = _unwrap_optional(tp)
    origin = typing.get_origin(tp)
    if origin is list:
        (item,) = typing.get_args(tp)
        return {"type": "array", "items": _schema_for(item, cls, name, defs)}
    if tp is str:
        out: dict[str, Any] = {"type": "string"}
        enum = _ENUMS.get((cls, name))
        if enum:
            out["enum"] = list(enum)
        return out
    if is_dataclass(tp):
        _ensure_def(tp, defs)
        return {"$ref": f"#/$defs/{tp.__name__}"}
    return {}


def _ensure_def(cls: type, defs: dict[str, Any]) -> None:
    if cls.__name__ in defs:
        return
    defs[cls.__name__] = {}  # placeholder against recursion
    props: dict[str, Any] = {}
    hints = _hints(cls)
    rev = {v: k for k, v in _ALIASES.get(cls, {}).items()}
    for f in fields(cls):
        if f.name in _PRIVATE_FIELDS:
            continue
        if cls is Design and f.name == "schema_version":
            continue
        key = rev.get(f.name, f.name)
        sch = _schema_for(hints[f.name], cls, f.name, defs)
        doc = _DOC.get((cls, f.name))
        if doc:
            sch["description"] = doc
        props[key] = sch
    required = ["id"] if "id" in props else []
    if cls is Design:
        props = {"sekkei": {"type": "string", "const": SCHEMA_VERSION}, **props}
        required = ["sekkei", "name", "requirements", "components", "work_packages"]
    defs[cls.__name__] = {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def json_schema() -> dict[str, Any]:
    defs: dict[str, Any] = {}
    _ensure_def(Design, defs)
    root = defs.pop("Design")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/yui9696/sekkei/schema/design-1.json",
        "title": "sekkei design file",
        **root,
        "$defs": defs,
    }
