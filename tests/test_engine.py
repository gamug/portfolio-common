"""Tests for portfolio_common.db.engine.Database -- the one connection
factory every domain in this project's ecosystem uses.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from portfolio_common.db import Database


def test_connect_always_sets_row_factory_and_busy_timeout(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        assert db.raw.row_factory is sqlite3.Row
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 30_000
    finally:
        db.close()


def test_connect_custom_busy_timeout(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db", busy_timeout_ms=5_000)
    try:
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
    finally:
        db.close()


def test_connect_defaults_leave_wal_and_fk_off(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    finally:
        db.close()


def test_connect_wal_true_enables_wal_and_normal_sync(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db", wal=True)
    try:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    finally:
        db.close()


def test_connect_foreign_keys_true_enforces_fk(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db", foreign_keys=True)
    try:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        db.close()


def test_connect_check_same_thread_false_is_accepted(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db", wal=True, check_same_thread=False)
    try:
        db.execute("SELECT 1")
    finally:
        db.close()


def test_connect_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "t.db"
    db = Database.connect(path)
    try:
        assert path.parent.is_dir()
    finally:
        db.close()


def test_connect_create_parents_false_does_not_create(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "t.db"
    with pytest.raises(sqlite3.OperationalError):
        Database.connect(path, create_parents=False)


def test_read_only_opens_existing_file_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    setup = Database.connect(path)
    setup.execute("CREATE TABLE t (id INTEGER)")
    setup.commit()
    setup.close()

    db = Database.connect(path, read_only=True)
    try:
        assert db.raw.row_factory is sqlite3.Row
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO t (id) VALUES (1)")
    finally:
        db.close()


def test_read_only_does_not_create_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        Database.connect(path, read_only=True)


def test_execute_executemany_executescript(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE t (id INTEGER, name TEXT)")
        db.executemany("INSERT INTO t (id, name) VALUES (?, ?)", [(1, "a"), (2, "b")])
        db.commit()
        rows = db.execute("SELECT id, name FROM t ORDER BY id").fetchall()
        assert [tuple(r) for r in rows] == [(1, "a"), (2, "b")]
    finally:
        db.close()


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE t (id INTEGER)")
        with db.transaction():
            db.execute("INSERT INTO t (id) VALUES (1)")
        assert db.execute("SELECT id FROM t").fetchone()[0] == 1
    finally:
        db.close()


def test_transaction_rolls_back_on_exception(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE t (id INTEGER)")
        db.execute("INSERT INTO t (id) VALUES (1)")
        db.commit()
        with pytest.raises(ValueError, match="boom"), db.transaction():
            db.execute("INSERT INTO t (id) VALUES (2)")
            raise ValueError("boom")
        assert [r[0] for r in db.execute("SELECT id FROM t")] == [1]
    finally:
        db.close()


def test_subclass_connect_returns_subclass_instance(tmp_path: Path) -> None:
    class MyDatabase(Database):
        extra: str = "default"

    db = MyDatabase.connect(tmp_path / "t.db")
    try:
        assert isinstance(db, MyDatabase)
        db.extra = "custom"
        assert db.extra == "custom"
    finally:
        db.close()


# -- attach / detach ----------------------------------------------------------


def test_attach_read_only_makes_second_schema_visible(tmp_path: Path) -> None:
    other_path = tmp_path / "other.db"
    setup = Database.connect(other_path)
    setup.executescript("CREATE TABLE t (id INTEGER)")
    setup.execute("INSERT INTO t (id) VALUES (42)")
    setup.commit()
    setup.close()

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(other_path, "other", read_only=True)
        schemas = {row[1] for row in db.execute("PRAGMA database_list")}
        assert "other" in schemas
        assert db.execute("SELECT id FROM other.t").fetchone()[0] == 42
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO other.t (id) VALUES (1)")
    finally:
        db.close()


def test_attach_then_detach_removes_schema(tmp_path: Path) -> None:
    other_path = tmp_path / "other.db"
    Database.connect(other_path).close()

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(other_path, "other", read_only=True)
        db.detach("other")
        schemas = {row[1] for row in db.execute("PRAGMA database_list")}
        assert "other" not in schemas
    finally:
        db.close()


def test_attach_rejects_invalid_alias(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        with pytest.raises(ValueError, match="invalid ATTACH alias"):
            db.attach(tmp_path / "other.db", "not a valid alias!")
    finally:
        db.close()


def test_attach_rejects_stale_wal(tmp_path: Path) -> None:
    other_path = tmp_path / "other.db"
    holder = sqlite3.connect(other_path)
    assert holder.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    holder.execute("PRAGMA wal_autocheckpoint=0")
    holder.execute("CREATE TABLE t (id INTEGER)")
    holder.commit()
    try:
        assert Path(f"{other_path}-wal").stat().st_size > 0

        db = Database.connect(tmp_path / "main.db", uri=True)
        try:
            with pytest.raises(RuntimeError, match="wal_checkpoint"):
                db.attach(other_path, "other", read_only=True)
        finally:
            db.close()
    finally:
        holder.close()


def test_attach_read_write_does_not_require_uri_scheme_on_alias(tmp_path: Path) -> None:
    other_path = tmp_path / "other.db"
    Database.connect(other_path).close()

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(other_path, "other", read_only=False)
        db.execute("CREATE TABLE other.t (id INTEGER)")
        db.execute("INSERT INTO other.t (id) VALUES (7)")
        db.commit()
        assert db.execute("SELECT id FROM other.t").fetchone()[0] == 7
    finally:
        db.close()
