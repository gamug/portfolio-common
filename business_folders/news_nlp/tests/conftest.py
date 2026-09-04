"""Shared fixtures for the news_nlp test suite."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

import news_nlp

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

    db = news_nlp.connect(path)
    news_nlp.init_schema(db)
    db.close()
    return path


@pytest.fixture
def conn(news_nlp_db_path: Path) -> Iterator[news_nlp.NewsNlpDatabase]:
    db = news_nlp.connect(news_nlp_db_path)
    yield db
    db.close()


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

    db = news_nlp.connect(path)
    news_nlp.init_schema(db)
    db.close()
    return path


@pytest.fixture
def two_tier_conn(
    source_db_path: Path, results_db_path: Path
) -> Iterator[news_nlp.NewsNlpDatabase]:
    db = news_nlp.connect_pipeline(results_db=results_db_path, source_db=source_db_path)
    yield db
    news_nlp.detach_source(db)
    db.close()
