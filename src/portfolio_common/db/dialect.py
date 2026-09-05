"""Per-engine SQL fragments -- the one place a database engine's *dialect*
is spelled out.

Every consumer repo (portfolio-nlp, -knowledge-graph, -financial-analysis,
-data-mining) keeps its own domain queries, but the handful of fragments
that differ between engines -- the upsert verb, the date/time functions, the
regexp-ish predicate, the auto-increment PK spelling, the parameter marker
-- come from here instead of being written as SQLite literals at the call
site. Swapping the engine later is then a new :class:`Dialect` implementation
plus a :func:`portfolio_common.db.engine.Database.connect_url` scheme, and
nothing in the consumers changes.

This module is a **pure string builder**. It does not sanitize table or
column names -- that stays the caller's job via
:class:`portfolio_common.db.safety.Allowlist`, exactly as it is today for the
hand-written f-strings this replaces. Values are still bound as ``?``
parameters by the caller; these helpers only assemble the surrounding text.

Semantics a non-SQLite implementation MUST preserve (the consumers rely on
them, and a subtly wrong reimplementation fails silently):

* :meth:`Dialect.year_expr` / :meth:`Dialect.year_month_expr` /
  :meth:`Dialect.week_start_expr` / :meth:`Dialect.week_end_expr` /
  :meth:`Dialect.current_date_expr` all return an expression whose value is
  a ``TEXT`` string in ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD`` form --
  lexically comparable to the ISO-8601 strings the schema stores in
  ``pub_date`` / ``fetched_at`` / ``week_start`` / ``week_end``.
* ``week_start`` is the **Monday** of the ISO week containing the argument;
  ``week_end`` is the **Sunday** of that same week.
* ``current_date_expr`` is "today" in **UTC**.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

__all__ = ["Dialect", "SqliteDialect", "get_dialect"]


@runtime_checkable
class Dialect(Protocol):
    """The engine-specific SQL surface the shared query layers draw from."""

    name: str
    paramstyle: str
    placeholder: str
    autoincrement_pk: str

    def placeholders(self, n: int) -> str: ...

    # -- DML statement text (caller binds the values positionally) ----------
    def insert(self, table: str, columns: Sequence[str]) -> str: ...
    def insert_or_ignore(self, table: str, columns: Sequence[str]) -> str: ...
    def upsert(
        self,
        table: str,
        columns: Sequence[str],
        *,
        conflict: Sequence[str],
        update: Sequence[str] | None = None,
        do_nothing: bool = False,
    ) -> str: ...
    def insert_or_ignore_select(
        self, dest: str, columns: Sequence[str], source: str, where: str
    ) -> str: ...

    # -- date/time expressions (arg is a column or sub-expression) ----------
    def year_expr(self, col: str) -> str: ...
    def year_month_expr(self, col: str) -> str: ...
    def week_start_expr(self, col: str) -> str: ...
    def week_end_expr(self, col: str) -> str: ...
    def current_date_expr(self) -> str: ...

    # -- misc fragments ---------------------------------------------------
    def group_concat(self, expr: str, separator: str) -> str: ...
    def excludes_bare_digit(self, col: str) -> str: ...
    def json_extract(self, column: str, path: str) -> str: ...
    def json_each(self, expr: str) -> str: ...


class SqliteDialect:
    """SQLite. Emits exactly the strings the consumers used inline before
    this module existed -- adopting the seam is a pure refactor, byte for
    byte."""

    name = "sqlite"
    paramstyle = "qmark"
    placeholder = "?"
    autoincrement_pk = "INTEGER PRIMARY KEY AUTOINCREMENT"

    def placeholders(self, n: int) -> str:
        if n < 1:
            raise ValueError("placeholders(n) requires n >= 1")
        return ", ".join([self.placeholder] * n)

    # -- DML --------------------------------------------------------------

    def _insert(self, verb: str, table: str, columns: Sequence[str]) -> str:
        cols = ", ".join(columns)
        return f"{verb} INTO {table} ({cols}) VALUES ({self.placeholders(len(columns))})"

    def insert(self, table: str, columns: Sequence[str]) -> str:
        return self._insert("INSERT", table, columns)

    def insert_or_ignore(self, table: str, columns: Sequence[str]) -> str:
        return self._insert("INSERT OR IGNORE", table, columns)

    def upsert(
        self,
        table: str,
        columns: Sequence[str],
        *,
        conflict: Sequence[str],
        update: Sequence[str] | None = None,
        do_nothing: bool = False,
    ) -> str:
        """An INSERT that resolves a conflict on *conflict* (a non-empty
        PK/UNIQUE column list -- a call site that can't name its target is a
        bug):

        * default -- ``INSERT OR REPLACE INTO ...``: whole-row replace
          (delete + reinsert). Fine for single-row-per-key result tables
          with no triggers/cascades on them.
        * ``update=[cols]`` -- ``INSERT INTO ... ON CONFLICT (conflict) DO
          UPDATE SET c = excluded.c`` for each *c* in *update*: an in-place
          update of just those columns (fires no delete). Pass the columns
          that should be overwritten on conflict.
        * ``do_nothing=True`` -- ``INSERT INTO ... ON CONFLICT (conflict) DO
          NOTHING``: keep the existing row.

        ``ON CONFLICT`` is SQLite (3.24+) and PostgreSQL syntax; ``INSERT OR
        REPLACE`` is SQLite-only, which is why the portable call sites pass
        *update* / *do_nothing* explicitly.
        """
        if not conflict:
            raise ValueError("upsert() requires a non-empty `conflict` column list")
        if update is not None and do_nothing:
            raise ValueError("upsert(): pass `update` or `do_nothing`, not both")
        if update is None and not do_nothing:
            return self._insert("INSERT OR REPLACE", table, columns)
        head = self._insert("INSERT", table, columns)
        target = ", ".join(conflict)
        if do_nothing:
            return f"{head} ON CONFLICT ({target}) DO NOTHING"
        assert update is not None  # guarded above: neither-branch and both-branch handled
        assignments = ", ".join(f"{c} = excluded.{c}" for c in update)
        if not assignments:
            raise ValueError("upsert(update=[...]) requires a non-empty column list")
        return f"{head} ON CONFLICT ({target}) DO UPDATE SET {assignments}"

    def insert_or_ignore_select(
        self, dest: str, columns: Sequence[str], source: str, where: str
    ) -> str:
        cols = ", ".join(columns)
        return (
            f"INSERT OR IGNORE INTO {dest} ({cols}) "  # noqa: S608
            f"SELECT {cols} FROM {source} WHERE {where}"
        )

    # -- date/time ------------------------------------------------------

    def year_expr(self, col: str) -> str:
        return f"strftime('%Y', {col})"

    def year_month_expr(self, col: str) -> str:
        return f"strftime('%Y-%m', {col})"

    def week_start_expr(self, col: str) -> str:
        # 'weekday 0' snaps forward to Sunday; '-6 days' backs up to Monday.
        return f"date({col}, 'weekday 0', '-6 days')"

    def week_end_expr(self, col: str) -> str:
        return f"date({col}, 'weekday 0')"

    def current_date_expr(self) -> str:
        return "date('now')"

    # -- misc ----------------------------------------------------------

    def group_concat(self, expr: str, separator: str) -> str:
        if "'" in separator:
            raise ValueError("group_concat() separator must not contain a single quote")
        return f"GROUP_CONCAT({expr}, '{separator}')"

    def excludes_bare_digit(self, col: str) -> str:
        """True when *col* is NOT a single bare digit ``0``-``9`` -- SQLite's
        ``GLOB '[0-9]'`` only matches one character, so multi-digit and
        alphanumeric values pass."""
        return f"{col} NOT GLOB '[0-9]'"

    def json_extract(self, column: str, path: str) -> str:
        """Value at JSON *path* (e.g. ``'$.score_weights'``) inside the JSON
        held in *column*. SQLite JSON1 / PostgreSQL both spell it
        ``json_extract`` here, though a PG dialect would more likely emit the
        ``->>`` / ``jsonb_path_query`` form."""
        if "'" in path:
            raise ValueError("json_extract() path must not contain a single quote")
        return f"json_extract({column}, '{path}')"

    def json_each(self, expr: str) -> str:
        """A table-valued ``json_each(<expr>)`` for ``FROM ..., json_each(...)``
        iteration over a JSON array/object. SQLite JSON1; a PG dialect emits
        ``jsonb_array_elements`` / ``jsonb_each``."""
        return f"json_each({expr})"


_SQLITE_DIALECT = SqliteDialect()


def get_dialect(name: str = "sqlite") -> Dialect:
    """The :class:`Dialect` for *name* (a shared singleton). Only
    ``"sqlite"`` is implemented; anything else raises -- the point of the
    seam is that a new engine is added *here*, deliberately."""
    if name == "sqlite":
        return _SQLITE_DIALECT
    raise ValueError(f"unknown SQL dialect {name!r}: the only implemented dialect is 'sqlite'")
