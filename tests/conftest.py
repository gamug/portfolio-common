"""Shared fixtures for the portfolio-common test suite."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import pytest

from portfolio_common import news_nlp

# The universe.db schema `kg_schema.universe_source` reads -- identical to what
# `portfolio_common.universe_history` writes and to the copy other repos build in
# their own test fixtures.
_UNIVERSE_DDL = """
CREATE TABLE universe_membership (
    symbol TEXT NOT NULL, security TEXT NOT NULL,
    gics_sector TEXT, gics_sub_industry TEXT, hq_location TEXT,
    date_added TEXT, cik TEXT, founded TEXT,
    valid_from TEXT NOT NULL, valid_to TEXT, source TEXT NOT NULL
);
CREATE INDEX idx_membership_symbol ON universe_membership (symbol);
CREATE INDEX idx_membership_valid ON universe_membership (valid_from, valid_to);
"""


def write_universe_db(
    path: Path, members: Iterable[tuple[str, str, str | None]], *, source: str = "test"
) -> Path:
    """Build a minimal ``universe.db`` at *path*. Each member is
    ``(symbol, valid_from, valid_to)``; the other columns are filled with
    placeholders."""
    conn = sqlite3.connect(path)
    conn.executescript(_UNIVERSE_DDL)
    conn.executemany(
        "INSERT INTO universe_membership "
        "(symbol, security, gics_sector, gics_sub_industry, valid_from, valid_to, source) "
        "VALUES (?, ?, 'S1', 'SI0', ?, ?, ?)",
        [(sym, f"{sym} Inc.", vf, vt, source) for sym, vf, vt in members],
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def universe_db(tmp_path: Path) -> Callable[..., Path]:
    """Factory: write a temp ``universe.db`` and return its path.

    ``universe_db([("AAPL", "2020-01-01", None), ...])`` -- ``(symbol, valid_from,
    valid_to)`` per row."""

    def _make(members: Iterable[tuple[str, str, str | None]], name: str = "universe.db") -> Path:
        return write_universe_db(tmp_path / name, members)

    return _make


# --- news_nlp: results-store DB fixtures -------------------------------------

# `articles` DDL for the news_nlp results-store tests: the SOURCE-store shape
# (with `body_text`) but no FK to `discovered_urls` (the results store has no
# crawler tables). Mirrors portfolio-nlp's tests/news_nlp/conftest.py.
NEWS_NLP_ARTICLES_SCHEMA = """
CREATE TABLE articles (
    id INTEGER PRIMARY KEY,
    ticker TEXT,
    company TEXT,
    gics_sector TEXT,
    gics_sub_industry TEXT,
    title TEXT,
    author TEXT,
    pub_date TEXT,
    fetched_at TEXT,
    body_text TEXT,
    word_count INTEGER,
    source_domain TEXT,
    fetch_status TEXT,
    http_status_code INTEGER
)
"""
NEWS_NLP_LEAN_ARTICLES_SCHEMA = NEWS_NLP_ARTICLES_SCHEMA.replace("    body_text TEXT,\n", "")


def seed_article(
    conn: sqlite3.Connection,
    id: int,
    company: str = "3M",
    ticker: str = "MMM",
    title: str = "Test Title",
    pub_date: str | None = "2023-01-15T00:00:00Z",
    body_text: str = "Body text.",
    word_count: int = 2,
    source_domain: str = "example.com",
    fetch_status: str = "ok",
    gics_sector: str = "Industrials",
    gics_sub_industry: str = "Industrial Conglomerates",
    fetched_at: str = "2023-01-15T00:00:00Z",
    http_status_code: int = 200,
) -> None:
    conn.execute(
        """INSERT INTO articles
           (id, ticker, company, gics_sector, gics_sub_industry, title, author, pub_date,
            fetched_at, body_text, word_count, source_domain, fetch_status, http_status_code)
           VALUES (?, ?, ?, ?, ?, ?, 'Author', ?, ?, ?, ?, ?, ?, ?)""",
        (
            id,
            ticker,
            company,
            gics_sector,
            gics_sub_industry,
            title,
            pub_date,
            fetched_at,
            body_text,
            word_count,
            source_domain,
            fetch_status,
            http_status_code,
        ),
    )


@pytest.fixture
def news_nlp_db_path(tmp_path: Path) -> Path:
    """A single-file news_nlp DB: full `articles` + the five result tables."""
    path = tmp_path / "test.db"
    raw = sqlite3.connect(path)
    raw.executescript(NEWS_NLP_ARTICLES_SCHEMA)
    raw.commit()
    raw.close()

    conn = news_nlp.connect(path)
    news_nlp.init_schema(conn)
    conn.close()
    return path


@pytest.fixture
def conn(news_nlp_db_path: Path) -> Iterator[sqlite3.Connection]:
    c = news_nlp.connect(news_nlp_db_path)
    yield c
    c.close()


@pytest.fixture
def source_db_path(tmp_path: Path) -> Path:
    """A SOURCE database: `articles` (incl. `body_text`), three seeded rows, no
    result tables."""
    path = tmp_path / "source.db"
    conn = sqlite3.connect(path)
    conn.executescript(NEWS_NLP_ARTICLES_SCHEMA)
    for i, (ticker, sector) in enumerate(
        [("MMM", "Industrials"), ("AAPL", "Information Technology"), ("XOM", "Energy")], start=1
    ):
        seed_article(
            conn,
            id=i,
            ticker=ticker,
            company=f"Company {ticker}",
            gics_sector=sector,
            body_text=f"Body text for article {i}. " * 20,
        )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def results_db_path(tmp_path: Path) -> Path:
    """A RESULTS store: lean `articles` (no `body_text`) + the result tables."""
    path = tmp_path / "results.db"
    conn = sqlite3.connect(path)
    conn.executescript(NEWS_NLP_LEAN_ARTICLES_SCHEMA)
    conn.commit()
    conn.close()

    conn = news_nlp.connect(path)
    news_nlp.init_schema(conn)
    conn.close()
    return path


@pytest.fixture
def two_tier_conn(source_db_path: Path, results_db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = news_nlp.connect_pipeline(results_db=results_db_path, source_db=source_db_path)
    yield conn
    news_nlp.detach_source(conn)
    conn.close()
