"""Tests for portfolio_common.db.safety -- the injection-prevention
primitives every domain's queries.py builds dynamic SQL text with."""

from __future__ import annotations

from pathlib import Path

import pytest

from portfolio_common.db import Allowlist, Database, in_clause


def test_in_clause_sizes_placeholder_group_to_input() -> None:
    assert in_clause([1]) == "(?)"
    assert in_clause([1, 2, 3]) == "(?,?,?)"


def test_in_clause_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one value"):
        in_clause([])


def test_in_clause_used_against_a_real_query(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE assets (id INTEGER, ticker TEXT)")
        db.executemany(
            "INSERT INTO assets (id, ticker) VALUES (?, ?)",
            [(1, "AAPL"), (2, "MSFT"), (3, "GOOG")],
        )
        db.commit()

        tickers = ["AAPL", "GOOG", "DROP TABLE assets; --"]
        placeholders = in_clause(tickers)
        rows = db.execute(
            f"SELECT ticker FROM assets WHERE ticker IN {placeholders}",  # noqa: S608
            tickers,
        ).fetchall()

        assert {r[0] for r in rows} == {"AAPL", "GOOG"}
        # the malicious-looking value was safely bound, not executed as SQL
        assert db.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 3
    finally:
        db.close()


def test_allowlist_check_returns_known_name() -> None:
    allowed = Allowlist("ticker", "sector")
    assert allowed.check("ticker") == "ticker"


def test_allowlist_check_rejects_unknown_name() -> None:
    allowed = Allowlist("ticker", "sector")
    with pytest.raises(ValueError, match="not one of the allowed names"):
        allowed.check("ticker; DROP TABLE assets")


def test_allowlist_contains() -> None:
    allowed = Allowlist("a", "b")
    assert "a" in allowed
    assert "c" not in allowed


def test_allowlist_used_to_guard_dynamic_order_by(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE t (id INTEGER, name TEXT)")
        db.executemany("INSERT INTO t (id, name) VALUES (?, ?)", [(2, "b"), (1, "a")])
        db.commit()

        order_columns = Allowlist("id", "name")
        column = order_columns.check("id")
        rows = db.execute(f"SELECT id FROM t ORDER BY {column}")  # noqa: S608
        assert [r[0] for r in rows] == [1, 2]

        with pytest.raises(ValueError):
            order_columns.check("id; DROP TABLE t")
    finally:
        db.close()
