"""Tests for portfolio_common.news_export -- the shared read-only two-tier
connect + fetch_processed_articles contract consumed by portfolio-nlp and
portfolio-knowledge-graph.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from portfolio_common.news_export import connect_readonly, fetch_processed_articles

_ARTICLES_SCHEMA = """
CREATE TABLE articles (
    id INTEGER PRIMARY KEY,
    ticker TEXT,
    pub_date TEXT,
    fetched_at TEXT,
    body_text TEXT,
    fetch_status TEXT
)
"""
_RESULT_TABLES_SCHEMA = """
CREATE TABLE article_sentiment (
    article_id INTEGER PRIMARY KEY,
    positive REAL,
    negative REAL,
    processed_at TEXT
);
CREATE TABLE article_category (
    article_id INTEGER PRIMARY KEY,
    label TEXT,
    score REAL,
    processed_at TEXT
);
"""


def _seed_article(conn: sqlite3.Connection, id: int, fetch_status: str = "ok") -> None:
    conn.execute(
        "INSERT INTO articles (id, ticker, pub_date, fetched_at, body_text, fetch_status) "
        "VALUES (?, 'MMM', '2023-01-01', '2023-01-01', 'body', ?)",
        (id, fetch_status),
    )


@pytest.fixture
def source_db_path(tmp_path: Path) -> Path:
    path = tmp_path / "source.db"
    conn = sqlite3.connect(path)
    conn.executescript(_ARTICLES_SCHEMA)
    for i in (1, 2, 3):
        _seed_article(conn, i)
    _seed_article(conn, 4, fetch_status="error")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def results_db_path(tmp_path: Path) -> Path:
    path = tmp_path / "results.db"
    conn = sqlite3.connect(path)
    conn.executescript(_RESULT_TABLES_SCHEMA)
    conn.execute("INSERT INTO article_sentiment VALUES (1, 0.9, 0.05, '2023-01-02')")
    conn.execute(
        "INSERT INTO article_category VALUES (1, 'earnings_performance', 0.8, '2023-01-02')"
    )
    # id 2 has a sentiment but no category yet -- must not appear (inner join).
    conn.execute("INSERT INTO article_sentiment VALUES (2, 0.4, 0.4, '2023-01-02')")
    conn.commit()
    conn.close()
    return path


def test_distinct_paths_attaches_source_read_only(
    source_db_path: Path, results_db_path: Path
) -> None:
    db, articles_rel = connect_readonly(source_db_path, results_db_path)
    try:
        assert articles_rel == "source"
        schemas = {row[1] for row in db.execute("PRAGMA database_list")}
        assert "source" in schemas
    finally:
        db.close()


def test_same_path_skips_attach(tmp_path: Path) -> None:
    path = tmp_path / "single.db"
    conn = sqlite3.connect(path)
    conn.executescript(_ARTICLES_SCHEMA)
    conn.executescript(_RESULT_TABLES_SCHEMA)
    conn.commit()
    conn.close()

    db, articles_rel = connect_readonly(path, path)
    try:
        assert articles_rel == "main"
        schemas = {row[1] for row in db.execute("PRAGMA database_list")}
        assert "source" not in schemas
    finally:
        db.close()


def test_fetch_processed_articles_requires_both_sentiment_and_category(
    source_db_path: Path, results_db_path: Path
) -> None:
    db, articles_rel = connect_readonly(source_db_path, results_db_path)
    try:
        rows = fetch_processed_articles(db, articles_rel)
        assert [r["id"] for r in rows] == [1]  # id 2 lacks a category row
        assert rows[0]["cat_label"] == "earnings_performance"
    finally:
        db.close()


def test_fetch_processed_articles_excludes_non_ok_fetch_status(
    tmp_path: Path,
) -> None:
    path = tmp_path / "single.db"
    conn = sqlite3.connect(path)
    conn.executescript(_ARTICLES_SCHEMA)
    conn.executescript(_RESULT_TABLES_SCHEMA)
    _seed_article(conn, 4, fetch_status="error")
    conn.execute("INSERT INTO article_sentiment VALUES (4, 0.9, 0.05, '2023-01-02')")
    conn.execute(
        "INSERT INTO article_category VALUES (4, 'earnings_performance', 0.8, '2023-01-02')"
    )
    conn.commit()
    conn.close()

    db, articles_rel = connect_readonly(path, path)
    try:
        rows = fetch_processed_articles(db, articles_rel)
        assert rows == []
    finally:
        db.close()


def test_fetch_processed_articles_respects_limit(source_db_path: Path, tmp_path: Path) -> None:
    path = tmp_path / "results2.db"
    conn = sqlite3.connect(path)
    conn.executescript(_RESULT_TABLES_SCHEMA)
    for i in (1, 2, 3):
        conn.execute("INSERT INTO article_sentiment VALUES (?, 0.9, 0.05, '2023-01-02')", (i,))
        conn.execute(
            "INSERT INTO article_category VALUES (?, 'earnings_performance', 0.8, '2023-01-02')",
            (i,),
        )
    conn.commit()
    conn.close()

    db, articles_rel = connect_readonly(source_db_path, path)
    try:
        rows = fetch_processed_articles(db, articles_rel, limit=2)
        assert [r["id"] for r in rows] == [1, 2]
    finally:
        db.close()


def test_fetch_processed_articles_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "single.db"
    conn = sqlite3.connect(path)
    conn.executescript(_ARTICLES_SCHEMA)
    conn.executescript(_RESULT_TABLES_SCHEMA)
    conn.commit()
    conn.close()

    db, _ = connect_readonly(path, path)
    try:
        with pytest.raises(ValueError, match="not one of the allowed names"):
            fetch_processed_articles(db, "not-a-real-schema")
    finally:
        db.close()
