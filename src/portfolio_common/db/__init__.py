"""The DB engine + injection-safe query-building primitives.

* :class:`~portfolio_common.db.engine.Database` -- the one connection class
  (open via :meth:`~portfolio_common.db.engine.Database.connect_url`),
  with schema introspection and a :attr:`~portfolio_common.db.engine.Database.dialect`.
* :class:`~portfolio_common.db.dialect.Dialect` -- the per-engine SQL
  fragments (``get_dialect()`` returns the SQLite one).
* :data:`~portfolio_common.db.engine.Row` / :class:`~portfolio_common.db.engine.RowLike`
  -- the row type consumers annotate with, and its access contract.
* :func:`~portfolio_common.db.two_store.connect_two_store` /
  :class:`~portfolio_common.db.two_store.TwoTierDatabase` -- writable
  primary + optional read-only attached secondary.
* :func:`~portfolio_common.db.safety.in_clause` /
  :class:`~portfolio_common.db.safety.Allowlist` -- injection-safe dynamic
  SQL.
"""

from __future__ import annotations

from portfolio_common.db.dialect import Dialect, SqliteDialect, get_dialect
from portfolio_common.db.engine import Database, DatabaseError, Row, RowLike
from portfolio_common.db.safety import Allowlist, in_clause
from portfolio_common.db.two_store import TwoTierDatabase, connect_two_store

__all__ = [
    "Allowlist",
    "Database",
    "DatabaseError",
    "Dialect",
    "Row",
    "RowLike",
    "SqliteDialect",
    "TwoTierDatabase",
    "connect_two_store",
    "get_dialect",
    "in_clause",
]
