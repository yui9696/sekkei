"""Exports engineers paste into the tools they already use: tracker issues and an OpenAPI skeleton.

- ``issues``: one Markdown body per work package (goal, requirements verbatim, components, acceptance
  checklist, dependencies) plus a shell script that creates them with the GitHub CLI in dependency
  order and a CSV for trackers that import one (Jira, Linear, Asana).
- ``openapi``: an OpenAPI 3.0 document built from the design's HTTP interfaces. Operation names
  of the form ``POST /orders/{id}/cancel`` become path items; other operations get a conventional
  path from the interface's resource; inputs become a request body (POST/PUT/PATCH) or query
  parameters (GET/DELETE); listed error strings that start with a status code become responses.
  Everything is a *skeleton*: schemas are ``object`` with the named fields and no validation.

Both are deterministic and need no model.
"""
from __future__ import annotations

import json
import re

from . import graph as G
from . import model as M
from .model import Design, Interface, Operation, WorkPackage

# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

SIZE_LABEL = {"S": "size:S", "M": "size:M", "L": "size:L"}


def issue_body(d: Design, wp: WorkPackage) -> str:
    s = [f"**Goal.** {wp.goal or wp.title}", ""]
    reqs = [r for r in d.requirements if r.id in wp.satisfies]
    if reqs:
        s.append("**Requirements (verbatim from the spec)**")
        for r in reqs:
            m = f" — _metric: {M.metric_text(r.metric)}_" if r.metric else ""
            s.append(f"- {r.id} ({r.kind}, {r.priority}): {r.statement}{m}")
        s.append("")
    comps = [c for c in d.components if c.id in wp.components]
    if comps:
        s.append("**Build**")
        for c in comps:
            s.append(f"- {c.id} {c.name} ({c.kind}){' — `' + c.path + '`' if c.path else ''}: {c.responsibility}")
        s.append("")
    ifaces = [i for i in d.interfaces if i.id in wp.implements]
    if ifaces:
        s.append("**Interfaces to implement**")
        for i in ifaces:
            ops = ", ".join(f"`{o.name}`" for o in i.operations[:12]) + (" …" if len(i.operations) > 12 else "")
            s.append(f"- {i.id} {i.name} ({i.kind}): {ops or '—'}")
        s.append("")
    if wp.depends_on:
        s.append("**Depends on** " + ", ".join(wp.depends_on) + " (create those issues first; link them as blockers)")
        s.append("")
    if wp.files:
        s.append("**Write scope** (files this package may change)")
        s += [f"- `{f}`" for f in wp.files]
        s.append("")
    if wp.acceptance:
        s.append("**Acceptance** (definition of done)")
        for a in wp.acceptance:
            cmd = f" — `{a.command}`" if a.command else ""
            s.append(f"- [ ] {a.id}: {a.description}{cmd}")
        s.append("")
    s.append(f"_Size {wp.size}. Generated from design `{d.name}` v{d.version}; regenerate with `sekkei issues` after a design change._")
    return "\n".join(s) + "\n"


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def issues(d: Design) -> dict[str, str]:
    """Files: issues/<WP>.md, issues/create_issues.sh, issues/issues.csv."""
    files: dict[str, str] = {}
    order = [w for wave in G.waves(G.package_graph(d)) for w in wave]
    by_id = {w.id: w for w in d.work_packages}
    script = ["#!/bin/sh", "# Creates one GitHub issue per work package in dependency order (needs the gh CLI, run inside the repo).",
              "# Usage: sh issues/create_issues.sh [extra gh flags, e.g. --milestone M1]", "set -e", "cd \"$(dirname \"$0\")\""]
    csv = ["id,title,size,depends_on,components,requirements"]
    for wid in order:
        w = by_id[wid]
        files[f"issues/{w.id}.md"] = issue_body(d, w)
        labels = ",".join(["sekkei", SIZE_LABEL.get(w.size, "size:M")])
        script.append(f"gh issue create --title {_sh_quote(w.id + ': ' + w.title)} --body-file {w.id}.md --label {_sh_quote(labels)} \"$@\"")
        csv.append(",".join([w.id, '"' + w.title.replace('"', '""') + '"', w.size, " ".join(w.depends_on), " ".join(w.components), " ".join(w.satisfies)]))
    files["issues/create_issues.sh"] = "\n".join(script) + "\n"
    files["issues/issues.csv"] = "\n".join(csv) + "\n"
    return files


# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------

_HTTP_OP = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/\S*)$", re.I)
_VERB_METHOD = {"create": "post", "register": "post", "add": "post", "publish": "post", "submit": "post", "upload": "post", "send": "post",
                "request": "post", "book": "post", "order": "post", "pay": "post", "refund": "post", "approve": "post", "reject": "post",
                "cancel": "post", "retry": "post", "rotate": "post", "enable": "post", "disable": "post", "run": "post", "sync": "post",
                "list": "get", "get": "get", "search": "get", "query": "get", "download": "get", "export": "get", "check": "get", "view": "get",
                "filter": "get", "count": "get", "update": "put", "edit": "put", "set": "put", "configure": "put", "change": "put",
                "delete": "delete", "remove": "delete", "revoke": "delete", "purge": "delete"}
_TYPE_MAP = {"str": "string", "string": "string", "int": "integer", "integer": "integer", "float": "number", "number": "number",
             "bool": "boolean", "boolean": "boolean", "datetime": "string", "date": "string", "json": "object", "dict": "object",
             "bytes": "string", "list": "array", "timedelta": "string"}


def _schema_of(type_text: str) -> dict:
    t = (type_text or "").strip()
    low = t.lower()
    if low.startswith("list[") or low.startswith("array"):
        return {"type": "array", "items": {"type": "string"}}
    base = re.split(r"[ |\[]", low)[0]
    out: dict = {"type": _TYPE_MAP.get(base, "string")}
    if base in ("datetime", "date"):
        out["format"] = "date-time" if base == "datetime" else "date"
    if t and out["type"] == "string" and base not in _TYPE_MAP:
        out["description"] = t
    return out


def _resource(iface: Interface, d: Design) -> str:
    owner = d.component(iface.owner)
    name = (owner.name if owner else iface.name).lower()
    name = re.sub(r"\b(public|admin|ingest|http|api|interface|service)\b", "", name).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "resource"
    return slug if slug.endswith("s") else slug + "s"


def _path_and_method(op: Operation, iface: Interface, d: Design) -> tuple[str, str]:
    m = _HTTP_OP.match(op.name.strip())
    if m:
        return m.group(2), m.group(1).lower()
    verb = re.split(r"[_ ]", op.name.strip().lower())[0]
    method = _VERB_METHOD.get(verb, "post")
    rest = "_".join(re.split(r"[_ ]", op.name.strip().lower())[1:])
    res = re.sub(r"[^a-z0-9]+", "-", rest).strip("-") or _resource(iface, d)
    if method in ("get", "delete", "put") and verb in ("get", "view", "update", "edit", "set", "delete", "remove", "revoke", "change"):
        return f"/{res}/{{id}}", method
    if method == "post" and verb not in ("create", "register", "add", "submit", "upload", "publish", "send", "request", "book", "order", "pay"):
        return f"/{res}/{{id}}/{verb}", method
    return f"/{res}", method


def openapi(d: Design) -> dict:
    paths: dict = {}
    used: set[str] = set()
    for iface in d.interfaces:
        if iface.kind != "http":
            continue
        owner = d.component(iface.owner)
        if owner is not None and owner.kind == "external":
            continue          # we do not publish the contracts of services we merely call
        tag = (owner.name if owner else iface.name)
        for op in iface.operations:
            path, method = _path_and_method(op, iface, d)
            key = f"{method} {path}"
            n = 2
            while key in used:
                path2 = f"{path}-{n}"
                key = f"{method} {path2}"
                n += 1
            if key != f"{method} {path}":
                path = key.split(" ", 1)[1]
            used.add(key)
            params = []
            body_props: dict = {}
            for p in op.inputs:
                if f"{{{p.name}}}" in path:
                    params.append({"name": p.name, "in": "path", "required": True, "schema": _schema_of(p.type)})
                elif method in ("get", "delete", "head"):
                    params.append({"name": p.name, "in": "query", "required": False, "schema": _schema_of(p.type), **({"description": p.description} if p.description else {})})
                else:
                    body_props[p.name] = {**_schema_of(p.type), **({"description": p.description} if p.description else {})}
            for seg in re.findall(r"\{([^}]+)\}", path):
                if not any(x["name"] == seg for x in params):
                    params.insert(0, {"name": seg, "in": "path", "required": True, "schema": {"type": "string"}})
            responses: dict = {}
            ok = "201" if method == "post" and re.match(r"^(create|register|add|submit|upload|request|book|order)", op.name.lower()) else "200"
            om = re.match(r"^(\d{3})\b", (op.output or "").strip())
            if om:
                ok = om.group(1)
            responses[ok] = {"description": op.output or "OK"}
            for e in op.errors:
                em = re.match(r"^(\d{3})\b\s*(.*)$", e.strip())
                if em:
                    responses[em.group(1)] = {"description": em.group(2) or e}
                else:
                    responses.setdefault("400", {"description": e})
            operation: dict = {
                "operationId": re.sub(r"[^A-Za-z0-9_]+", "_", f"{iface.id}_{op.name}").strip("_"),
                "summary": op.description or op.name,
                "tags": [tag],
                "responses": dict(sorted(responses.items())),
                "x-sekkei-interface": iface.id,
            }
            if op.pre or op.post:
                operation["description"] = " ".join(x for x in (f"Precondition: {op.pre}." if op.pre else "", f"Postcondition: {op.post}." if op.post else "") if x)
            if params:
                operation["parameters"] = params
            if body_props and method in ("post", "put", "patch"):
                operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": body_props}}}}
            paths.setdefault(path, {})[method] = operation
    schemas = {}
    for e in d.entities:
        props = {f.name: {**_schema_of(f.type), **({"description": f.constraints} if f.constraints else {})} for f in e.fields}
        schemas[re.sub(r"[^A-Za-z0-9]+", "", e.name) or e.id] = {"type": "object", "properties": props, "x-sekkei-entity": e.id}
    return {
        "openapi": "3.0.3",
        "info": {"title": d.name, "version": d.version, "description": (d.summary or "") + "\n\nSkeleton generated by sekkei from the design; schemas carry field names only."},
        "paths": dict(sorted(paths.items())),
        "components": {"schemas": dict(sorted(schemas.items()))},
    }


def openapi_json(d: Design) -> str:
    return json.dumps(openapi(d), indent=2, ensure_ascii=False) + "\n"
