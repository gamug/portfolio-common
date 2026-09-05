"""The single SQLite connection engine every domain in this project's
ecosystem uses to talk to a database.

Before this module existed, connection lifecycle (opening, pragma policy,
read-only mode, ATTACH/DETACH) was reimplemented four times across this
repo, each with slightly different defaults -- see CHANGELOG.md's v1.0.0
entry. :class:`Database` centralizes all of it behind one class, so a future
change to that policy (or a future engine swap entirely) is one place to
change, not N near-duplicate connection recipes scattered across every
domain module.

:class:`Database` wraps a ``sqlite3.Connection`` by composition rather than
subclassing it. A domain that needs extra per-connection state (see the
two-tier SOURCE/RESULTS attach tracking in
:mod:`portfolio_common.db.two_store`) subclasses :class:`Database` itself and
gets ordinary Python attributes for free -- no ``sqlite3.Connection``
subclassing trick required.

The engine is meant to be swappable in *one* place. Consumers get the
engine-specific SQL fragments they need from :attr:`Database.dialect` (see
:mod:`portfolio_common.db.dialect`), open connections through
:meth:`Database.connect_url` (a path *or* a ``scheme://`` URL), and do
runtime schema introspection through :meth:`Database.table_columns` /
:meth:`Database.table_exists` / :meth:`Database.ensure_columns` rather than
writing ``PRAGMA`` themselves. ``Row`` is the row type they annotate with --
today an alias for ``sqlite3.Row``; :class:`RowLike` is the contract any
future engine's row factory has to meet.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable
from urllib.parse import urlsplit

from portfolio_common.db.dialect import Dialect, get_dialect

__all__ = ["Database", "DatabaseError", "Row", "RowLike"]

_CONNECT_TIMEOUT_S = 30.0
DEFAULT_BUSY_TIMEOUT_MS = 30_000

#: The row type consumers annotate query results with. An alias, not a
#: subclass -- today every :class:`Database` is SQLite, so this *is*
#: ``sqlite3.Row``. A future engine swap re-points this alias; see
#: :class:`RowLike` for the access contract it must keep.
Row = sqlite3.Row

#: The engine-neutral exception type for a statement that failed against the
#: database (a missing table/column, a locked file, bad SQL, ...). Today it
#: *is* ``sqlite3.OperationalError``; catch this instead of importing
#: ``sqlite3`` yourself, and prefer :meth:`Database.relation_exists` over a
#: ``try/except`` where you're really only asking "does this table exist".
DatabaseError = sqlite3.OperationalError


@runtime_checkable
class RowLike(Protocol):
    """What a row object must support so the shared query layers stay
    engine-agnostic: mapping access (``row["col"]``), positional access and
    tuple-unpacking (``row[0]``, ``a, b = row``), and ``dict(row)`` (needs
    ``keys()``). ``sqlite3.Row`` satisfies all of it; a non-SQLite engine
    would need a hybrid row factory, not psycopg's dict-only or tuple-only
    default -- this is the main constraint the "swap in one place" promise
    puts on a future engine."""

    def __getitem__(self, key: int | str) -> Any: ...
    def __iter__(self) -> Iterator[Any]: ...
    def keys(self) -> Sequence[str]: ...
    def __len__(self) -> int: ...


# ATTACH/DETACH cannot bind the alias as a `?` parameter (SQLite only allows
# parameterizing values, never identifiers) -- this checks it is at least
# syntactically a plain identifier before it reaches an f-string. Every
# known caller passes a literal alias from its own source code (not
# attacker-controlled input), so this guards against a typo producing a
# broken ATTACH, not an injection attack surface.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_STALE_WAL_MSG = (
    "{path} has an un-checkpointed write-ahead log ({wal} exists and is "
    "non-empty). It is being ATTACHed read-only (mode=ro), which cannot "
    "replay a WAL, so the newest data would be invisible. Checkpoint it "
    'first -- `sqlite3 {path} "PRAGMA wal_checkpoint(TRUNCATE);"` -- or '
    "let its writer close cleanly, then re-run."
)
_ATTACH_FAILED_MSG = "Could not ATTACH {path} read-only (mode=ro) as {alias!r}: {error}."

T = TypeVar("T", bound="Database")

# Registered URL schemes for connect_url(). Only "sqlite" today -- a future
# engine registers its own connector here and nothing else in this repo (or
# any consumer) has to learn a new connect call.
_KNOWN_SCHEMES = ("sqlite",)


def _split_qualified(name: str) -> tuple[str | None, str]:
    """``"main.articles"`` -> ``("main", "articles")``; ``"articles"`` ->
    ``(None, "articles")``."""
    if "." in name:
        schema, _, table = name.partition(".")
        return schema, table
    return None, name


def _split_url(url: str | os.PathLike[str]) -> tuple[str, str]:
    """``(scheme, target)`` for :meth:`Database.connect_url`.

    A value is a **filesystem path** (scheme ``"sqlite"``, target = the path
    text) unless it is a ``file:`` URI (handed through to SQLite as-is) or a
    ``scheme://...`` URL for a known engine. ``"D:/thesis/data/nlp.db"`` is a
    path, not a ``d:`` URL -- a single-letter scheme without ``://`` is a
    Windows drive. An unknown ``scheme://`` raises rather than being opened
    as a weirdly-named file.
    """
    if isinstance(url, os.PathLike):
        return "sqlite", os.fspath(url)
    text = str(url)
    if text.startswith("file:"):
        return "sqlite", text  # a SQLite file: URI -- hand through untouched
    if text.startswith("sqlite:///"):
        # SQLAlchemy-style: sqlite:///rel.db -> rel.db ; sqlite:////abs -> /abs ;
        # sqlite:///D:/win -> D:/win. Everything after the fixed prefix is the path.
        return "sqlite", text[len("sqlite:///") :]
    scheme = urlsplit(text).scheme.lower()
    if "://" in text and len(scheme) > 1 and scheme not in _KNOWN_SCHEMES:
        raise ValueError(
            f"unsupported database URL scheme {scheme!r}: "
            f"known schemes are {sorted((*_KNOWN_SCHEMES, 'file'))}"
        )
    if scheme == "sqlite" and "://" in text:  # sqlite://host/path -- rare, take the remainder
        return "sqlite", text.split("://", 1)[1]
    # bare path, Windows drive letter ("D:/..."), or relative path
    return "sqlite", text


class Database:
    """One SQLite connection, opened and configured through :meth:`connect`
    or :meth:`connect_url`."""

    def __init__(self, conn: sqlite3.Connection, *, dialect: Dialect | None = None) -> None:
        self._conn = conn
        self._dialect: Dialect = dialect or get_dialect("sqlite")
        # copy_row_lean() resolves a column-intersection per (dest, source,
        # exclude) once and reuses it -- a two-tier pipeline calls it once
        # per processed row and the column set never changes mid-connection.
        self._lean_cols_cache: dict[tuple[str, str, tuple[str, ...]], list[str]] = {}

    @property
    def dialect(self) -> Dialect:
        """The engine-specific SQL fragments for this connection (see
        :mod:`portfolio_common.db.dialect`)."""
        return self._dialect

    # -- connecting -------------------------------------------------------

    @classmethod
    def connect_url(cls: type[T], url: str | os.PathLike[str], **kwargs: Any) -> T:
        """Open *url* -- a filesystem path, a ``file:`` URI, or a
        ``sqlite:///path`` URL -- with the shared pragma policy.

        The one entry point a consumer's ``connect()`` should call, so that
        *what engine* a ``DATABASE_URL`` names is decided here, not in each
        repo's env-resolution code. ``**kwargs`` pass through to
        :meth:`connect` (``foreign_keys=``, ``wal=``, ``read_only=`` ...).
        SQLite targets are always opened ``uri=True`` so a later read-only
        :meth:`attach` on the connection is honored.
        """
        scheme, target = _split_url(url)
        if scheme != "sqlite":  # pragma: no cover - guarded by _split_url today
            raise ValueError(f"no connector registered for URL scheme {scheme!r}")
        spec = target if target.startswith("file:") else f"file:{Path(target).as_posix()}"
        return cls.connect(spec, uri=True, **kwargs)

    @classmethod
    def connect(
        cls: type[T],
        path: str | os.PathLike[str],
        *,
        read_only: bool = False,
        wal: bool = False,
        foreign_keys: bool = False,
        create_parents: bool = True,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        check_same_thread: bool = True,
        uri: bool = False,
    ) -> T:
        """Open *path* with the shared pragma policy.

        Always: rows come back as ``sqlite3.Row``.

        ``read_only=True``: opens ``file:{path}?mode=ro`` -- URI read-only.
        No busy_timeout/WAL/foreign_keys pragmas (nothing to retry or
        enforce on a connection that can't write), no directory creation.
        Every other flag below is ignored.

        ``read_only=False`` (default): parent directories of *path* are
        created unless *create_parents* is False. *busy_timeout_ms* is
        always applied (not persistent, so every connection has to set it --
        without it, a connection that finds the file locked by another
        writer gets an immediate ``sqlite3.OperationalError: database is
        locked`` instead of retrying internally for up to this long).
        ``wal=True`` also sets ``journal_mode=WAL`` + ``synchronous=NORMAL``
        (``journal_mode`` is persistent at the file level, so setting it
        once on the writer is enough -- other connections inherit it).
        ``foreign_keys=True`` sets ``PRAGMA foreign_keys=ON`` (also not
        persistent -- SQLite declares FK constraints in the schema but does
        not enforce them unless this is set on every connection).

        ``check_same_thread=False`` lifts sqlite3's thread-binding.
        ``uri=True`` interprets *path* as a ``file:...`` URI -- required for
        a later :meth:`attach` on this connection to be honored.
        """
        if read_only:
            conn = sqlite3.connect(
                f"file:{Path(path)}?mode=ro", uri=True, timeout=_CONNECT_TIMEOUT_S
            )
            conn.row_factory = sqlite3.Row
            return cls(conn)

        if not uri:
            p = Path(path)
            if create_parents:
                p.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            path,
            timeout=_CONNECT_TIMEOUT_S,
            check_same_thread=check_same_thread,
            uri=uri,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        if wal:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        if foreign_keys:
            conn.execute("PRAGMA foreign_keys = ON")
        return cls(conn)

    # -- ATTACH / DETACH ----------------------------------------------------

    def attach(self, path: str | os.PathLike[str], alias: str, *, read_only: bool = True) -> None:
        """ATTACH *path* to this connection as schema *alias*.

        *alias* must be a plain SQL identifier (checked against a fixed
        regex -- see the module-level note on why this isn't an
        :class:`~portfolio_common.db.safety.Allowlist` check).

        ``read_only=True`` (default) attaches via ``file:{path}?mode=ro``,
        and first runs a stale-WAL preflight: a read-only attach cannot
        replay a leftover write-ahead log, so a database left with an
        un-checkpointed ``-wal`` sidecar (its writer killed mid-run, or the
        file copied without checkpointing) would otherwise silently serve
        stale data instead of failing loudly. Raises :class:`RuntimeError`
        with a fix-it message instead.
        """
        if not _IDENTIFIER_RE.match(alias):
            raise ValueError(f"invalid ATTACH alias: {alias!r}")
        p = Path(path)
        if read_only:
            wal = p.with_name(p.name + "-wal")
            if wal.exists() and wal.stat().st_size > 0:
                raise RuntimeError(_STALE_WAL_MSG.format(path=p, wal=wal))
            uri = f"file:{p.as_posix()}?mode=ro"
        else:
            uri = f"file:{p.as_posix()}"
        try:
            # alias is validated above (not a bindable `?` parameter --
            # SQLite only parameterizes values); the path is bound.
            self._conn.execute(f"ATTACH DATABASE ? AS {alias}", (uri,))
        except sqlite3.OperationalError as exc:
            raise RuntimeError(_ATTACH_FAILED_MSG.format(path=p, alias=alias, error=exc)) from exc

    def detach(self, alias: str) -> None:
        """Undo :meth:`attach`. Raises ``sqlite3.OperationalError`` if
        *alias* isn't currently attached -- callers that attach
        conditionally should track that themselves (see
        :class:`portfolio_common.db.two_store.TwoTierDatabase`)."""
        if not _IDENTIFIER_RE.match(alias):
            raise ValueError(f"invalid DETACH alias: {alias!r}")
        self._conn.execute(f"DETACH DATABASE {alias}")

    # -- schema introspection & DDL --------------------------------------

    def table_columns(self, table: str, *, schema: str | None = None) -> list[str]:
        """Column names of *table* (optionally in an attached *schema*), in
        definition order. Empty list if the table does not exist -- so this
        doubles as an existence check (see :meth:`table_exists`). Replaces
        hand-written ``PRAGMA table_info`` at consumer call sites."""
        if not _IDENTIFIER_RE.match(table):
            raise ValueError(f"invalid table name: {table!r}")
        if schema is not None:
            if not _IDENTIFIER_RE.match(schema):
                raise ValueError(f"invalid schema name: {schema!r}")
            cur = self._conn.execute(f"PRAGMA {schema}.table_info({table})")
        else:
            cur = self._conn.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cur]

    def table_exists(self, table: str, *, schema: str | None = None) -> bool:
        return bool(self.table_columns(table, schema=schema))

    def relation_exists(self, name: str) -> bool:
        """Whether a table **or view** named *name* exists. Prefer this over
        ``try: conn.execute(...) except DatabaseError`` at call sites whose
        real question is "is this relation present in a partial database"."""
        return self.relation_kind(name) is not None

    def relation_kind(self, name: str) -> str | None:
        """``"table"`` / ``"view"`` / ``None`` for *name* -- the engine's
        catalog lookup, replacing hand-written ``sqlite_master`` queries."""
        row = self._conn.execute(
            "SELECT type FROM sqlite_master WHERE name = ? AND type IN ('table', 'view') LIMIT 1",
            (name,),
        ).fetchone()
        return row[0] if row is not None else None

    def relation_ddl(self, name: str) -> str | None:
        """The stored ``CREATE`` text for table/view *name*, or ``None``. A
        SQLite-ism (``SELECT sql FROM sqlite_master``) that migration code
        uses to gate CHECK-constraint changes; a non-SQLite migration path
        would not use it."""
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = ? LIMIT 1", (name,)
        ).fetchone()
        return row[0] if row is not None else None

    @property
    def schema_version(self) -> int:
        """The database's schema-version counter (SQLite ``PRAGMA
        user_version``). Consumers that track their schema with a dedicated
        ``schema_version`` table don't need this."""
        return int(self._conn.execute("PRAGMA user_version").fetchone()[0])

    def set_schema_version(self, version: int) -> None:
        if not isinstance(version, int) or version < 0:
            raise ValueError(f"schema version must be a non-negative int, got {version!r}")
        self._conn.execute(f"PRAGMA user_version = {version}")

    def ensure_columns(
        self, table: str, columns: dict[str, str], *, schema: str | None = None
    ) -> None:
        """Add each ``name -> column-definition`` in *columns* that *table*
        does not already have (``ALTER TABLE ... ADD COLUMN``). No-op if
        *table* is absent -- callers that need the table created should do
        that first. Idempotent; safe to run on every startup. The column
        *definitions* are trusted caller literals (e.g.
        ``"INTEGER NOT NULL DEFAULT 0"``); the names are identifier-checked."""
        existing = set(self.table_columns(table, schema=schema))
        if not existing:
            return
        qualified = f"{schema}.{table}" if schema is not None else table
        for name, definition in columns.items():
            if not _IDENTIFIER_RE.match(name):
                raise ValueError(f"invalid column name: {name!r}")
            if name not in existing:
                self._conn.execute(f"ALTER TABLE {qualified} ADD COLUMN {name} {definition}")

    def create_schema(self, ddl: str) -> None:
        """Run a multi-statement DDL script. On SQLite this is
        ``executescript`` (implicit ``COMMIT``, no parameter binding, split
        on ``;``). A future engine owns its own multi-statement strategy
        here, so consumers' ``init_schema`` never has to care."""
        self._conn.executescript(ddl)

    def copy_row_lean(
        self,
        dest: str,
        source: str,
        *,
        key: str,
        key_value: Any,
        exclude: Sequence[str] = (),
    ) -> None:
        """``INSERT OR IGNORE`` the row with ``{key} = {key_value}`` from
        *source* into *dest*, using the columns the two tables share minus
        *exclude*, in *source* definition order. *dest* / *source* are
        schema-qualified (``"main.articles"`` / ``"source.articles"``). Used
        by the two-tier pipeline to keep the RESULTS store's lean ``articles``
        row present before a result-table write references it. No-op-safe to
        repeat (``INSERT OR IGNORE``)."""
        cache_key = (dest, source, tuple(exclude))
        cols = self._lean_cols_cache.get(cache_key)
        if cols is None:
            dest_schema, dest_table = _split_qualified(dest)
            src_schema, src_table = _split_qualified(source)
            dest_cols = set(self.table_columns(dest_table, schema=dest_schema))
            excluded = set(exclude)
            cols = [
                c
                for c in self.table_columns(src_table, schema=src_schema)
                if c in dest_cols and c not in excluded
            ]
            self._lean_cols_cache[cache_key] = cols
        sql = self._dialect.insert_or_ignore_select(
            dest, cols, source, f"{key} = {self._dialect.placeholder}"
        )
        self._conn.execute(sql, (key_value,))

    # -- statement execution ------------------------------------------------

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> sqlite3.Cursor:
        return self._conn.executemany(sql, seq_of_params)

    def executescript(self, script: str) -> sqlite3.Cursor:
        return self._conn.executescript(script)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run a block atomically: commits on clean exit, rolls back and
        re-raises on any exception."""
        try:
            yield
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    @property
    def raw(self) -> sqlite3.Connection:
        """Escape hatch to the underlying ``sqlite3.Connection``, for the
        rare case a domain's ``queries.py`` needs something not wrapped
        above (e.g. ``conn.row_factory`` introspection). Prefer the wrapped
        methods everywhere else."""
        return self._conn
