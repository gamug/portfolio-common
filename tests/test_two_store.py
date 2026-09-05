"""Tests for portfolio_common.db.two_store -- writable primary + optional
read-only attached secondary, the generic form of portfolio-nlp's two-tier
SOURCE/RESULTS pattern.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from portfolio_common.db import Database, TwoTierDatabase, connect_two_store


@pytest.fixture
def primary_db_path(tmp_path: Path) -> Path:
    path = tmp_path / "primary.db"
    db = Database.connect(path)
    db.executescript("CREATE TABLE result (id INTEGER PRIMARY KEY, note TEXT)")
    db.commit()
    db.close()
    return path


@pytest.fixture
def secondary_db_path(tmp_path: Path) -> Path:
    path = tmp_path / "secondary.db"
    db = Database.connect(path)
    db.executescript("CREATE TABLE shared (id INTEGER PRIMARY KEY, payload TEXT)")
    db.execute("INSERT INTO shared VALUES (1, 'hello')")
    db.commit()
    db.close()
    return path


def test_distinct_paths_attach_secondary_read_only(
    primary_db_path: Path, secondary_db_path: Path
) -> None:
    db, read_schema = connect_two_store(primary_db_path, secondary_db_path)
    try:
        assert read_schema == "source"
        assert db.read_schema == "source"
        schemas = {row[1] for row in db.execute("PRAGMA database_list")}
        assert "source" in schemas
        assert db.execute("SELECT payload FROM source.shared WHERE id = 1").fetchone()[0] == "hello"
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO source.shared VALUES (2, 'x')")
    finally:
        db.close()


def test_same_path_skips_attach(tmp_path: Path) -> None:
    path = tmp_path / "single.db"
    Database.connect(path).close()
    db, read_schema = connect_two_store(path, path)
    try:
        assert read_schema == "main"
        assert db.read_schema == "main"
        schemas = {row[1] for row in db.execute("PRAGMA database_list")}
        assert "source" not in schemas
    finally:
        db.close()


def test_none_secondary_skips_attach(primary_db_path: Path) -> None:
    db, read_schema = connect_two_store(primary_db_path, None)
    try:
        assert read_schema == "main"
        assert db.read_schema == "main"
    finally:
        db.close()


def test_custom_alias(primary_db_path: Path, secondary_db_path: Path) -> None:
    db, read_schema = connect_two_store(primary_db_path, secondary_db_path, alias="crawl")
    try:
        assert read_schema == "crawl"
        assert db.read_schema == "crawl"
        assert "crawl" in {row[1] for row in db.execute("PRAGMA database_list")}
    finally:
        db.close()


def test_connect_kwargs_pass_through(primary_db_path: Path, secondary_db_path: Path) -> None:
    db, _ = connect_two_store(primary_db_path, secondary_db_path, foreign_keys=True)
    try:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        db.close()


def test_attach_readonly_then_detach_restores_primary_schema(
    primary_db_path: Path, secondary_db_path: Path
) -> None:
    tdb = TwoTierDatabase.connect_url(primary_db_path)
    try:
        assert tdb.read_schema == "main"
        tdb.attach_readonly("source", secondary_db_path)
        assert tdb.read_schema == "source"
        tdb.detach("source")
        assert tdb.read_schema == "main"
    finally:
        tdb.close()


def test_factory_returns_subclass_instance(primary_db_path: Path, secondary_db_path: Path) -> None:
    class NewsNlpDatabase(TwoTierDatabase):
        @property
        def articles_rel(self) -> str:
            return self.read_schema

    db, _ = connect_two_store(primary_db_path, secondary_db_path, factory=NewsNlpDatabase)
    try:
        assert isinstance(db, NewsNlpDatabase)
        assert db.articles_rel == "source"
    finally:
        db.close()
