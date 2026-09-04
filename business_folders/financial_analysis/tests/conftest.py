"""Shared fixtures for the financial_analysis (kg_schema) test suite."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

# The universe.db schema `universe_source` reads -- identical to what the
# data_mining domain's `universe_history` writes (see
# business_folders/data_mining/universe_history.py) and to the copy other
# repos build in their own test fixtures.
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
