"""Tracker issues and the OpenAPI skeleton."""
from __future__ import annotations

import json
from pathlib import Path

from sekkei import export as X
from sekkei.engine import design

REAL = Path(__file__).parent.parent / "examples" / "real"


def test_issues_cover_every_package_in_dependency_order():
    r = design((REAL / "jira_export.md").read_text(encoding="utf-8"))
    files = X.issues(r.design)
    ids = [w.id for w in r.design.work_packages]
    assert all(f"issues/{i}.md" in files for i in ids)
    script = files["issues/create_issues.sh"]
    import re as _re
    order = [_re.search(r"\b(WP-\d+)\.md", ln).group(1) for ln in script.splitlines() if ln.startswith("upsert '")]
    pos = {w: n for n, w in enumerate(order)}
    for w in r.design.work_packages:
        for dep in w.depends_on:
            assert pos[dep] < pos[w.id]
    body = files[f"issues/{ids[0]}.md"]
    assert "**Acceptance**" in body and "- [ ]" in body and "sekkei-key:" in body
    assert files["issues/issues.csv"].splitlines()[0] == "key,title,size,depends_on,components,requirements"
    assert "find_issue()" in script and any(ln.startswith("blocked_by ") for ln in script.splitlines())


def test_diff_and_issues_survive_a_two_bullet_change():
    from sekkei import diff as DF
    base = (REAL.parent / "real3" / "05_postmortem_ediscovery.md").read_text(encoding="utf-8")
    v2 = base.replace("Constraints noted in the meeting", "AI-10 (must): Quarantined files shall be listed on the dashboard with their error.\nAI-11 (should): A quarantined file can be retried by a case manager.\n\nConstraints noted in the meeting")
    d1, d2 = design(base).design, design(v2).design
    changes = DF.diff(d1, d2)
    real = [c for c in changes if c.kind != "renumbered"]
    assert any(c.kind == "added" and c.collection == "requirements" for c in real)
    changed_reqs = [c for c in real if c.collection == "requirements" and c.kind == "changed"]
    assert not changed_reqs, [str(c) for c in changed_reqs]            # renumbering is not a change
    affected = DF.affected_packages(d2, changes)
    assert len(affected) < len(d2.work_packages)                        # not every brief is stale
    i1, i2 = X.issues(d1), X.issues(d2)
    keys1 = {ln.split("'")[1] for ln in i1["issues/create_issues.sh"].splitlines() if ln.startswith("upsert '")}
    keys2 = {ln.split("'")[1] for ln in i2["issues/create_issues.sh"].splitlines() if ln.startswith("upsert '")}
    assert keys1 & keys2 and len(keys1 & keys2) >= len(keys1) - 3        # the same tickets are found again by key


def test_openapi_from_the_returns_portal_is_valid_shaped_and_sane():
    r = design((REAL / "jira_export.md").read_text(encoding="utf-8"))
    doc = X.openapi(r.design)
    assert doc["openapi"] == "3.0.3"
    assert "/returns" in doc["paths"] and set(doc["paths"]["/returns"]) == {"post", "get"}
    for path, ops in doc["paths"].items():
        assert path.startswith("/")
        for method, op in ops.items():
            assert "responses" in op and op["operationId"]
            if method in ("post", "put"):
                assert "requestBody" in op or "parameters" in op
    assert not any("customer" in p for p in doc["paths"]), "a notification sentence must not become an endpoint"
    json.dumps(doc)     # serialisable


def test_openapi_uses_stated_http_operations():
    from sekkei import model as M
    d = M.Design(name="t")
    d.components.append(M.Component("C-1", "API", "x", "service"))
    d.interfaces.append(M.Interface("I-1", "API", "C-1", "http", [
        M.Operation("POST /orders/{id}/cancel", [M.Param("id", "str"), M.Param("reason", "str")], "202 accepted", ["404 unknown id", "409 not applicable"]),
        M.Operation("GET /orders", [M.Param("filter", "query")], "200 [order]", ["401 unauthenticated"]),
    ]))
    doc = X.openapi(d)
    op = doc["paths"]["/orders/{id}/cancel"]["post"]
    assert op["parameters"][0] == {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
    assert set(op["responses"]) == {"202", "404", "409"}
    assert doc["paths"]["/orders"]["get"]["parameters"][0]["in"] == "query"
