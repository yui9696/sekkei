"""Japanese input: glossary-based normalisation is deterministic, auditable and honest about gaps."""
from __future__ import annotations

from pathlib import Path

import pytest

from sekkei import model as M
from sekkei.engine import design
from sekkei.engine import ja

ZAIKO = Path(__file__).parent.parent / "examples" / "ja" / "zaiko.md"


def test_detection():
    assert ja.is_japanese("利用者は注文を登録できる。")
    assert not ja.is_japanese("Users can register orders.")
    assert not ja.is_japanese("")
    assert not ja.is_japanese("TypeScript (Node 20).")


@pytest.mark.parametrize("src, expect", [
    ("利用者は注文を登録できる。", "Users can register orders."),
    ("管理者は商品を追加・更新・削除できる", "Admins can add, update and delete products."),
    ("注文は削除してはならない", "The system must not delete orders."),
    ("顧客は自分の注文履歴を閲覧できること", "Customers can view their own orders history."),
    ("管理者はユーザーを招待できない", "Admins must not invite users."),
    ("月間稼働率 99.9% 以上。", "Monthly availability at least 99.9 %."),
    ("購買・仕入先管理は対象外", "Purchasing suppliers manage (out of scope)."),
])
def test_sentences(src, expect):
    assert ja.rewrite_sentence(src).english == expect


def test_numbers_and_units():
    assert "within 300 ms" in ja.numbers("300ms以内")
    assert "at least 99.9 %" in ja.numbers("99.9%以上")
    assert "10000 requests/s" in ja.numbers("毎秒1万件")
    assert "1000 requests/s" in ja.numbers("1,000件/秒")
    assert "every 5 seconds" in ja.numbers("5秒ごとに")
    assert "Team of 3" in ja.numbers("チームは3名")
    assert "Team of 3" in ja.numbers("3名のチーム")
    assert "200000 items" in ja.numbers("20万件の品目")
    assert "2000 vehicles" in ja.numbers("2,000台の車両")


def test_passive_and_negation():
    r = ja.rewrite_sentence("マネージャーは在庫が発注点を下回るとメールで通知される")
    assert r.english.startswith("Managers are notified")
    r = ja.rewrite_sentence("在庫数は同時更新でも失われず、二重に適用されない")
    assert "not lost" in r.english and "double-applied" in r.english


def test_unknown_words_are_listed_not_guessed():
    r = ja.rewrite_sentence("利用者は魔法陣を登録できる")
    assert r.untranslated == ["魔法陣"]
    assert r.english == "Users can register."


def test_document_sections_and_passthrough():
    n = ja.normalise("# 在庫サービス\n\n## 機能要件\n- 利用者は注文を登録できる。\n\n## 制約\n- PostgreSQL available. Team of 2.\n\n## 対象外\n- 購買。\n")
    assert "## Functional" in n.text and "## Constraints" in n.text and "## Out of scope" in n.text
    assert "- Users can register orders." in n.text
    assert "- PostgreSQL available. Team of 2." in n.text   # English lines pass through untouched
    assert n.sources["Users can register orders."] == "利用者は注文を登録できる。"
    assert n.title == "在庫サービス"


def test_design_from_japanese_is_lint_clean_and_traceable():
    text = ZAIKO.read_text(encoding="utf-8")
    r = design(text)
    assert r.ok, r.diagnostics
    assert r.analysis.normalisation is not None
    assert "crud_api" in r.analysis.patterns and "notification" in r.analysis.patterns
    assert "postgres" in r.analysis.constraints and r.analysis.team_size == 2
    ja_reqs = [q for q in r.design.requirements if "source (ja):" in q.rationale]
    assert len(ja_reqs) >= 8
    assert any("300 ms" in q.metric.target for q in r.design.requirements if q.metric)
    md = r.notes.to_markdown()
    assert "Input normalisation" in md and "| source | rewritten as |" in md


def test_japanese_design_is_deterministic():
    text = ZAIKO.read_text(encoding="utf-8")
    assert M.dumps(design(text).design) == M.dumps(design(text).design)


def test_english_input_is_unchanged_by_the_ja_layer():
    text = "# Inventory\n## Functional\n- Staff can add items through a REST API.\n## Constraints\n- Python. Team of 2.\n"
    r = design(text)
    assert r.analysis.normalisation is None
    assert r.design.requirements[0].statement == "Staff can add items through a REST API."
