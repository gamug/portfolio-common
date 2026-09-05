"""Tests for portfolio_common.db.dialect -- the per-engine SQL fragments.

The SQLite dialect must emit exactly the strings the consumers used inline
before the seam existed (so adopting it is a pure refactor), and the
date/time expressions must actually compute Monday-start ISO weeks and a
UTC "today" when run.
"""

from __future__ import annotations

import sqlite3

import pytest

from portfolio_common.db import Dialect, SqliteDialect, get_dialect


@pytest.fixture
def d() -> SqliteDialect:
    return SqliteDialect()


def test_get_dialect_returns_shared_sqlite_singleton() -> None:
    assert get_dialect() is get_dialect("sqlite")
    assert isinstance(get_dialect(), Dialect)
    assert get_dialect().name == "sqlite"


def test_get_dialect_rejects_unknown_engine() -> None:
    with pytest.raises(ValueError, match="only implemented dialect is 'sqlite'"):
        get_dialect("postgresql")


def test_placeholders(d: SqliteDialect) -> None:
    assert d.placeholder == "?"
    assert d.paramstyle == "qmark"
    assert d.placeholders(1) == "?"
    assert d.placeholders(3) == "?, ?, ?"
    with pytest.raises(ValueError, match="n >= 1"):
        d.placeholders(0)


def test_autoincrement_pk_token(d: SqliteDialect) -> None:
    assert d.autoincrement_pk == "INTEGER PRIMARY KEY AUTOINCREMENT"


def test_insert_variants(d: SqliteDialect) -> None:
    assert d.insert("t", ["a", "b"]) == "INSERT INTO t (a, b) VALUES (?, ?)"
    assert d.insert_or_ignore("t", ["a"]) == "INSERT OR IGNORE INTO t (a) VALUES (?)"


def test_upsert_is_insert_or_replace_on_sqlite(d: SqliteDialect) -> None:
    assert (
        d.upsert("article_sentiment", ["article_id", "label"], conflict=["article_id"])
        == "INSERT OR REPLACE INTO article_sentiment (article_id, label) VALUES (?, ?)"
    )


def test_upsert_requires_a_conflict_target(d: SqliteDialect) -> None:
    with pytest.raises(ValueError, match="non-empty `conflict`"):
        d.upsert("t", ["a"], conflict=[])


def test_insert_or_ignore_select(d: SqliteDialect) -> None:
    assert d.insert_or_ignore_select(
        "main.articles", ["id", "ticker"], "source.articles", "id = ?"
    ) == (
        "INSERT OR IGNORE INTO main.articles (id, ticker) "
        "SELECT id, ticker FROM source.articles WHERE id = ?"
    )


def test_date_expression_strings(d: SqliteDialect) -> None:
    assert d.year_expr("a.pub_date") == "strftime('%Y', a.pub_date)"
    assert d.year_month_expr("a.pub_date") == "strftime('%Y-%m', a.pub_date)"
    assert d.week_start_expr("x") == "date(x, 'weekday 0', '-6 days')"
    assert d.week_end_expr("x") == "date(x, 'weekday 0')"
    assert d.current_date_expr() == "date('now')"


def test_group_concat_and_bare_digit_strings(d: SqliteDialect) -> None:
    assert d.group_concat("text", ", ") == "GROUP_CONCAT(text, ', ')"
    assert d.excludes_bare_digit("e.text") == "e.text NOT GLOB '[0-9]'"
    with pytest.raises(ValueError, match="single quote"):
        d.group_concat("text", "'; DROP")


def _scalar(sql: str) -> object:
    conn = sqlite3.connect(":memory:")
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def test_week_expressions_compute_monday_start_iso_weeks(d: SqliteDialect) -> None:
    wed = "'2026-08-05'"  # a Wednesday -> Mon 2026-08-03 .. Sun 2026-08-09
    mon = "'2026-08-03'"
    assert _scalar(f"SELECT {d.week_start_expr(wed)}") == "2026-08-03"
    assert _scalar(f"SELECT {d.week_end_expr(wed)}") == "2026-08-09"
    # A Monday maps to itself as the start.
    assert _scalar(f"SELECT {d.week_start_expr(mon)}") == "2026-08-03"


def test_year_expressions_compute_lexically_sortable_text(d: SqliteDialect) -> None:
    ts = "'2023-04-15T10:00:00Z'"
    assert _scalar(f"SELECT {d.year_expr(ts)}") == "2023"
    assert _scalar(f"SELECT {d.year_month_expr(ts)}") == "2023-04"


# -- v1.2.1: upsert ON CONFLICT variants + JSON fragments ------------------


def test_upsert_default_is_still_insert_or_replace(d: SqliteDialect) -> None:
    assert d.upsert("t", ["a", "b"], conflict=["a"]) == (
        "INSERT OR REPLACE INTO t (a, b) VALUES (?, ?)"
    )


def test_upsert_with_update_emits_on_conflict_do_update(d: SqliteDialect) -> None:
    assert d.upsert(
        "assets", ["id", "ticker", "name"], conflict=["id"], update=["ticker", "name"]
    ) == (
        "INSERT INTO assets (id, ticker, name) VALUES (?, ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET ticker = excluded.ticker, name = excluded.name"
    )


def test_upsert_do_nothing(d: SqliteDialect) -> None:
    assert d.upsert("edge", ["a", "b"], conflict=["a", "b"], do_nothing=True) == (
        "INSERT INTO edge (a, b) VALUES (?, ?) ON CONFLICT (a, b) DO NOTHING"
    )


def test_upsert_rejects_update_and_do_nothing_together(d: SqliteDialect) -> None:
    with pytest.raises(ValueError, match="not both"):
        d.upsert("t", ["a"], conflict=["a"], update=["a"], do_nothing=True)


def test_upsert_on_conflict_do_update_round_trips_in_sqlite() -> None:
    d = SqliteDialect()
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE kv (k TEXT PRIMARY KEY, v INTEGER, note TEXT)")
        sql = d.upsert("kv", ["k", "v", "note"], conflict=["k"], update=["v"])
        conn.execute(sql, ("x", 1, "first"))
        conn.execute(sql, ("x", 2, "second-ignored-for-note"))
        row = conn.execute("SELECT v, note FROM kv WHERE k = 'x'").fetchone()
        assert row == (2, "first")  # v updated, note left from the first insert
    finally:
        conn.close()


def test_json_fragments(d: SqliteDialect) -> None:
    assert d.json_extract("cr.params_json", "$.score_weights") == (
        "json_extract(cr.params_json, '$.score_weights')"
    )
    assert d.json_each("cr.params_json") == "json_each(cr.params_json)"
    with pytest.raises(ValueError, match="single quote"):
        d.json_extract("c", "$.a'; DROP")
