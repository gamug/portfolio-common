"""The ``schema_version`` table: a monotonic floor other repos can assert against.

Additive DDL (new tables, new nullable columns) never bumps the version -- it is
safe to ship at any time. Only the non-additive rebuilds in :mod:`kg_schema.migrations`
advance it.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from portfolio_common.db import Database

VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def ensure(db: Database) -> None:
    """Create the ``schema_version`` table if it is missing."""
    db.executescript(VERSION_DDL)
    db.commit()


def current_version(db: Database) -> int:
    """Highest recorded schema version, or ``0`` when nothing has been applied."""
    ensure(db)
    row = db.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    value = row["v"] if isinstance(row, sqlite3.Row) else (row[0] if row else None)
    return int(value) if value is not None else 0


def record(db: Database, version: int, description: str) -> None:
    """Mark *version* as applied. Idempotent -- a re-recorded version is ignored."""
    db.execute(
        "INSERT OR IGNORE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
        (version, _now(), description),
    )
    db.commit()
