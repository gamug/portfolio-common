"""Tests for the engine-agnostic surface added to Database in v1.2.0:
connect_url, the schema-introspection helpers, create_schema, copy_row_lean,
and the Row type.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from portfolio_common.db import Database, Row, RowLike
from portfolio_common.db.engine import _split_url

# -- Row --------------------------------------------------------------------


def test_row_is_the_sqlite_row_alias_and_matches_rowlike(tmp_path: Path) -> None:
    assert Row is sqlite3.Row
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE t (a INTEGER, b TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'x')")
        row = db.execute("SELECT a, b FROM t").fetchone()
        assert isinstance(row, RowLike)
        assert row["a"] == 1 and row[0] == 1  # mapping AND positional
        a, b = row  # tuple-unpack
        assert (a, b) == (1, "x")
        assert dict(row) == {"a": 1, "b": "x"}  # keys()
    finally:
        db.close()


# -- _split_url -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("D:/thesis/data/nlp.db", "D:/thesis/data/nlp.db"),  # Windows drive, not a "d:" URL
        ("/abs/path.db", "/abs/path.db"),
        ("data/nlp.db", "data/nlp.db"),
        ("sqlite:///D:/thesis/data/nlp.db", "D:/thesis/data/nlp.db"),
        ("sqlite:////abs/p.db", "/abs/p.db"),
        ("file:/x/y.db?mode=ro", "file:/x/y.db?mode=ro"),
    ],
)
def test_split_url_treats_plain_and_sqlite_values_as_sqlite_paths(
    value: str, expected: str
) -> None:
    assert _split_url(value) == ("sqlite", expected)


def test_split_url_accepts_pathlike() -> None:
    assert _split_url(Path("/x/y.db")) == ("sqlite", "/x/y.db")


def test_split_url_rejects_unknown_scheme() -> None:
    with pytest.raises(ValueError, match="unsupported database URL scheme 'postgresql'"):
        _split_url("postgresql://host/db")


# -- connect_url --------------------------------------------------------


def test_connect_url_opens_a_path(tmp_path: Path) -> None:
    db = Database.connect_url(tmp_path / "t.db", foreign_keys=True)
    try:
        assert db.dialect.name == "sqlite"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        db.close()


def test_connect_url_opens_a_sqlite_scheme_url(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    db = Database.connect_url(url)
    try:
        db.execute("CREATE TABLE t (id INTEGER)")
        db.commit()
    finally:
        db.close()
    assert (tmp_path / "t.db").exists()


def test_connect_url_keeps_uri_mode_so_readonly_attach_is_honored(tmp_path: Path) -> None:
    secondary = tmp_path / "secondary.db"
    setup = Database.connect(secondary)
    setup.executescript("CREATE TABLE t (id INTEGER)")
    setup.execute("INSERT INTO t VALUES (42)")
    setup.commit()
    setup.close()

    db = Database.connect_url(tmp_path / "main.db")
    try:
        db.attach(secondary, "s", read_only=True)
        assert db.execute("SELECT id FROM s.t").fetchone()[0] == 42
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO s.t VALUES (1)")
    finally:
        db.close()


# -- introspection -----------------------------------------------------


def test_table_columns_and_exists(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE widget (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER)")
        assert db.table_columns("widget") == ["id", "name", "qty"]
        assert db.table_exists("widget") is True
        assert db.table_exists("nope") is False
        assert db.table_columns("nope") == []
    finally:
        db.close()


def test_table_columns_reads_an_attached_schema(tmp_path: Path) -> None:
    other = tmp_path / "other.db"
    setup = Database.connect(other)
    setup.executescript("CREATE TABLE t (x INTEGER, y INTEGER)")
    setup.commit()
    setup.close()

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(other, "other", read_only=True)
        assert db.table_columns("t", schema="other") == ["x", "y"]
        assert db.table_exists("t", schema="other") is True
    finally:
        db.close()


def test_table_columns_rejects_non_identifier(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        with pytest.raises(ValueError, match="invalid table name"):
            db.table_columns("t; DROP TABLE x")
    finally:
        db.close()


def test_ensure_columns_adds_only_missing_is_idempotent_and_noop_when_absent(
    tmp_path: Path,
) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE s (id INTEGER)")
        wanted = {
            "id": "INTEGER",
            "flag": "INTEGER NOT NULL DEFAULT 0",
            "note": "TEXT NOT NULL DEFAULT ''",
        }
        db.ensure_columns("s", wanted)
        db.ensure_columns("s", wanted)  # idempotent
        assert db.table_columns("s") == ["id", "flag", "note"]

        db.ensure_columns("missing", {"a": "TEXT"})  # no-op, no raise
        assert db.table_exists("missing") is False
    finally:
        db.close()


def test_create_schema_runs_multi_statement_ddl(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.create_schema(
            "CREATE TABLE a (id INTEGER);\n"
            "CREATE TABLE b (id INTEGER);\n"
            "CREATE INDEX idx_b ON b(id);"
        )
        assert db.table_exists("a") and db.table_exists("b")
    finally:
        db.close()


# -- copy_row_lean ----------------------------------------------------


def test_copy_row_lean_copies_shared_columns_minus_exclude(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    setup = Database.connect(source)
    setup.executescript(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, ticker TEXT, body_text TEXT)"
    )
    setup.execute("INSERT INTO articles VALUES (7, 'MMM', 'a long body')")
    setup.commit()
    setup.close()

    db = Database.connect(tmp_path / "main.db", uri=True, foreign_keys=True)
    try:
        db.executescript("CREATE TABLE articles (id INTEGER PRIMARY KEY, ticker TEXT)")
        db.attach(source, "source", read_only=True)

        db.copy_row_lean(
            "main.articles", "source.articles", key="id", key_value=7, exclude=("body_text",)
        )
        db.copy_row_lean(  # repeat -> INSERT OR IGNORE, still one row
            "main.articles", "source.articles", key="id", key_value=7, exclude=("body_text",)
        )
        db.commit()

        rows = db.execute("SELECT id, ticker FROM main.articles").fetchall()
        assert [tuple(r) for r in rows] == [(7, "MMM")]
        assert "body_text" not in db.table_columns("articles", schema="main")
    finally:
        db.close()
