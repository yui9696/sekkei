"""Work packages as deliverable slices: one owner per requirement, acceptance from the sentence, a size with its counts.

Every independent review scored the work packages 0/2 while a package was "the components of one
layer that share a pattern": a requirement was claimed by four packages, the acceptance check of a
functional requirement was "unit tests of <component> pass", and the size was a letter with no
basis. These tests hold the new shape.
"""
from __future__ import annotations

from sekkei.engine import design

SPEC = """# Fleet maintenance

## Functional
- Mechanics can open a repair order for a vehicle with the fault code and the odometer reading.
- Mechanics can close a repair order once the parts are fitted; a closed order cannot be reopened.
- Dispatchers can see every open repair order for a depot, newest first.
- The system emails the depot manager when a repair order stays open for more than 48 hours.

## Non-functional
- The order list returns within 400 ms p95.
- No repair order is lost or double-closed under concurrent updates.
- Repair orders are kept for 5 years.

## Constraints
- Python. PostgreSQL available. Team of 3.
"""


def _design():
    return design(SPEC).design


def test_every_requirement_is_delivered_by_exactly_one_package():
    d = _design()
    delivered = [r for w in d.work_packages for r in w.satisfies]
    assert sorted(delivered) == sorted(set(delivered)), "a requirement is claimed by two packages"
    assert {r.id for r in d.requirements} == set(delivered), "a requirement nobody delivers"


def test_a_functional_requirement_gets_its_own_acceptance_check_with_a_command():
    d = _design()
    req = next(r for r in d.requirements if r.kind == "functional" and "open a repair order" in r.statement)
    wp = next(w for w in d.work_packages if req.id in w.satisfies)
    acc = [a for a in wp.acceptance if a.description.startswith(req.id + " (")]
    assert acc, "the delivering package has no check naming the requirement"
    assert req.statement[:40] in acc[0].description, "the check does not quote the requirement"
    assert acc[0].kind == "test" and acc[0].command, "a test check must carry the command that runs it"


def test_a_metric_check_lives_only_in_the_package_that_owns_the_metric():
    d = _design()
    for r in d.requirements:
        if r.kind != "nonfunctional" or not r.metric:
            continue
        carriers = [w.id for w in d.work_packages for a in w.acceptance if a.kind == "metric" and a.metric == r.id]
        assert len(carriers) <= 1, f"{r.id} is checked by {carriers}"


def test_foundations_come_before_the_slices_that_use_them():
    d = _design()
    store = next(c for c in d.components if "archetype:store" in c.tags)
    foundation = next(w for w in d.work_packages if store.id in w.components)
    users = [w for w in d.work_packages
             if any(i in [x.id for x in d.provided_by(store.id)] for c in w.components for i in (d.component(c).requires if d.component(c) else []))]
    assert users, "nothing uses the store"
    for w in users:
        assert foundation.id in w.depends_on, f"{w.id} uses the store without depending on {foundation.id}"
    assert not foundation.depends_on or all(int(x.split("-")[1]) < int(foundation.id.split("-")[1]) for x in foundation.depends_on)


def test_the_size_states_the_counts_it_was_computed_from():
    d = _design()
    for w in d.work_packages:
        assert "→ weight" in w.notes and "requirement(s)" in w.notes, w.notes
        assert w.notes.endswith(w.size) or f"→ {w.size}" in w.notes


def test_a_slice_writes_its_own_router_file_never_a_shared_one():
    d = _design()
    files = [f for w in d.work_packages for f in w.files]
    assert len(files) == len(set(files)), "two packages share a file in their write scope"


def test_requirements_a_package_touches_but_does_not_deliver_are_named_in_its_notes():
    d = _design()
    assert any("Also constrained by" in w.notes for w in d.work_packages), \
        "no package records the requirements it must honour but does not deliver"
