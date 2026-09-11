"""The starter design written by ``sekkei init``. Kept as code so the test-suite can lint it."""
from __future__ import annotations

from .dsl import DesignBuilder, check, op, option
from .model import Design


def starter_design(name: str = "todo-api") -> Design:
    b = DesignBuilder(name, summary="A small HTTP to-do service. Replace this with your system.")
    b.goal("Serve as a worked example of a sekkei design that lints clean.")
    b.non_goal("Authentication, multi-user, persistence beyond process lifetime.")
    b.conventions(
        language="python",
        test_command="python -m pytest -q",
        rules=["Standard library only.", "Every public function has a docstring."],
        definition_of_done=["Acceptance checks pass.", "No file outside the write scope was changed."],
    )
    b.requirement("R-1", "A client can create a to-do item by POSTing a title and gets back its id.")
    b.requirement("R-2", "A client can list all to-do items in creation order.")
    b.requirement(
        "R-3", "Listing 1,000 items completes within the latency target on a laptop.",
        kind="nonfunctional", metric=("p95 latency of GET /todos with 1000 items", "<= 50", "ms"),
    )
    b.component("C-1", "Store", "Keeps to-do items in memory in insertion order.", path="app/store.py", satisfies=["R-2", "R-3"])
    b.component("C-2", "HTTP API", "Translates HTTP requests into store calls and JSON responses.",
                kind="service", path="app/api.py", requires=["I-1"], satisfies=["R-1", "R-2"])
    b.interface("I-1", "Store API", owner="C-1", kind="class", stability="stable", operations=[
        op("add", inputs=[("title", "str")], output="int (new id)", errors=["ValueError if title is empty"]),
        op("list_all", output="list[Todo] in creation order"),
    ])
    b.interface("I-2", "REST API", owner="C-2", kind="http", operations=[
        op("POST /todos", inputs=[("title", "str")], output="201 {id}", errors=["400 on empty title"]),
        op("GET /todos", output="200 [{id, title}]"),
    ])
    b.entity("E-1", "Todo", owner="C-1", fields=[])
    b.flow("F-1", "Create a to-do", trigger="POST /todos", steps=[("C-2", "C-1", "I-1", "API adds the item")])
    b.decision(
        "D-1", "Storage", context="The input says nothing about persistence.",
        options=[option("in-memory list", pros=["no dependencies"], cons=["lost on restart"]),
                 option("sqlite", pros=["survives restart"], cons=["schema and migrations"])],
        choice="in-memory list", rationale="Non-goal: persistence.", affects=["C-1"],
    )
    b.risk("K-1", "Unbounded growth of the in-memory list.", likelihood="low", impact="low",
           mitigation="Document the limit; out of scope for v0.", affects=["C-1"])
    b.work_package(
        "WP-1", "Store", goal="Implement the in-memory store with add/list_all and its tests.",
        components=["C-1"], implements=["I-1"], satisfies=["R-2", "R-3"], size="S",
        files=["app/store.py", "tests/test_store.py"],
        acceptance=[
            check("A-1", "store unit tests pass", command="python -m pytest -q tests/test_store.py"),
            check("A-2", "listing 1000 items meets the latency target", kind="metric", metric="R-3"),
        ],
    )
    b.work_package(
        "WP-2", "HTTP API", goal="Expose POST /todos and GET /todos over the store using the standard library.",
        components=["C-2"], implements=["I-2"], depends_on=["WP-1"], satisfies=["R-1", "R-2"], size="M",
        files=["app/api.py", "tests/test_api.py"],
        acceptance=[check("A-3", "API tests pass", command="python -m pytest -q tests/test_api.py")],
    )
    return b.build()
