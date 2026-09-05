"""Two-store connections: a writable *primary* database plus an optional
read-only *secondary* attached into the same connection.

This is the generic form of the two-tier SOURCE/RESULTS pattern
``portfolio-nlp`` runs (results store read/write as ``main``; the crawl DB
attached read-only as ``source``; the ``articles`` table read from whichever
schema currently holds it). Keeping the ``"main"`` / attached-alias literals
and the same-file short-circuit here -- rather than spelled out in each
consumer -- means a future engine that reaches a second store differently
(a second connection, ``postgres_fdw``, a schema in the same database) is one
change here.

The attach mechanism is SQLite ``ATTACH ... ?mode=ro`` and therefore
local-file only; :func:`connect_two_store` takes filesystem paths, and the
same-target check is ``Path.resolve()`` equality.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from portfolio_common.db.dialect import Dialect
from portfolio_common.db.engine import Database

__all__ = ["TwoTierDatabase", "connect_two_store"]


class TwoTierDatabase(Database):
    """A :class:`~portfolio_common.db.engine.Database` that tracks which
    schema a "shared" table currently lives in: :attr:`primary_schema`
    (``"main"``) normally, the attached alias once :meth:`attach_readonly`
    runs. Subclass it to add domain state (``portfolio-nlp``'s
    ``NewsNlpDatabase`` adds nothing but a friendlier ``articles_rel``
    alias)."""

    primary_schema: str = "main"

    def __init__(self, conn: sqlite3.Connection, *, dialect: Dialect | None = None) -> None:
        super().__init__(conn, dialect=dialect)
        self._read_schema: str = self.primary_schema

    @property
    def read_schema(self) -> str:
        """The schema the shared table is currently read from -- the
        attached alias while a secondary store is attached, else
        :attr:`primary_schema`."""
        return self._read_schema

    def attach_readonly(self, alias: str, path: str | os.PathLike[str]) -> None:
        """ATTACH *path* read-only as *alias* (with the stale-WAL preflight
        from :meth:`Database.attach`) and route reads of the shared table to
        it."""
        self.attach(path, alias, read_only=True)
        self._read_schema = alias

    def detach(self, alias: str) -> None:
        super().detach(alias)
        if self._read_schema == alias:
            self._read_schema = self.primary_schema


def connect_two_store[D: TwoTierDatabase](
    primary: str | os.PathLike[str],
    secondary: str | os.PathLike[str] | None,
    *,
    alias: str = "source",
    factory: type[D] = TwoTierDatabase,  # type: ignore[assignment]
    **connect_kwargs: Any,
) -> tuple[D, str]:
    """Open *primary* read/write; unless *secondary* is ``None`` or resolves
    to the same file, ATTACH it read-only as *alias*.

    Returns ``(db, read_schema)`` -- ``read_schema`` is *alias* when the
    secondary was attached, else ``"main"``. ``**connect_kwargs`` pass
    through to :meth:`Database.connect_url` (e.g. ``foreign_keys=True``).
    """
    primary_path = Path(primary)
    db = factory.connect_url(primary_path, **connect_kwargs)
    if secondary is None:
        return db, db.primary_schema
    secondary_path = Path(secondary)
    if secondary_path.resolve() == primary_path.resolve():
        return db, db.primary_schema
    db.attach_readonly(alias, secondary_path)
    return db, alias
