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
two-tier SOURCE/RESULTS attach tracking in ``business_folders/news_nlp``)
subclasses :class:`Database` itself and gets ordinary Python attributes for
free -- no ``sqlite3.Connection`` subclassing trick required.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

__all__ = ["Database"]

_CONNECT_TIMEOUT_S = 30.0
DEFAULT_BUSY_TIMEOUT_MS = 30_000

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


class Database:
    """One SQLite connection, opened and configured through :meth:`connect`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- connecting -------------------------------------------------------

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
        ``business_folders/news_nlp``'s ``articles_rel`` state)."""
        if not _IDENTIFIER_RE.match(alias):
            raise ValueError(f"invalid DETACH alias: {alias!r}")
        self._conn.execute(f"DETACH DATABASE {alias}")

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
