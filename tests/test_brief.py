from __future__ import annotations

import json
import re

import pytest

from sekkei import state as S
from sekkei.brief import render_brief
from sekkei.examples import starter_design


def test_brief_contains_exactly_what_the_package_needs(tmp_path):
    d = starter_design()
    st = S.State.load(tmp_path)
    st.set_status("WP-1", "done")
    text = render_brief(d, "WP-2", st)
    # goal and verbatim requirements
    assert d.work_packages[1].goal in text
    assert d.requirements[0].statement in text and d.requirements[1].statement in text
    assert d.requirements[2].statement not in text  # R-3 is WP-1's
    # implements I-2 and consumes I-1 with the full contract
    assert "## 3. Implement these interfaces" in text and "`POST /todos`" in text
    assert "## 4. Use, do not modify" in text and "`add`" in text and "ValueError if title is empty" in text
    assert "WP-1=done" in text
    # scope, conventions, acceptance, dependencies, decisions do not leak
    assert "- `app/api.py`" in text and "- `tests/test_api.py`" in text
    assert "python -m pytest -q" in text and "Standard library only." in text
    assert "**A-3** (test)" in text and "A-1" not in text.split("## 7. Acceptance")[1].split("## 8.")[0]
    assert "- WP-1 Store — done" in text
    assert "D-1" not in text  # D-1 affects C-1 only, not this package
    # report template is valid JSON and matches the package
    block = re.search(r"```json\n(.*?)\n```", text, re.S).group(1)
    assert json.loads(block)["work_package"] == "WP-2"


def test_brief_never_names_another_packages_components():
    d = starter_design()
    text = render_brief(d, "WP-1")
    assert "C-2" not in text and "I-2" not in text and "WP-2" not in text
    assert "(this package consumes no other interface)" in text
    assert "(none; this package can start now)" in text
    assert "D-1" in text  # decision affecting C-1 is included


def test_brief_unknown_package():
    with pytest.raises(KeyError):
        render_brief(starter_design(), "WP-42")
