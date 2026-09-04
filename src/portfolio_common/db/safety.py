"""Injection-prevention primitives for building dynamic SQL text.

Two rules, and only two, are sanctioned anywhere in this project's ecosystem
for building a SQL string dynamically:

1. Every VALUE goes in as a bound ``?`` parameter. Never format, concatenate,
   or interpolate a value into SQL text, for any reason.
2. Every IDENTIFIER (column, table, alias, sort direction, ...) that must
   appear in SQL text is checked against a fixed :class:`Allowlist` first.

There is no third way to build dynamic SQL text in this codebase. Use
:func:`in_clause` for ``IN (...)`` placeholder groups and :class:`Allowlist`
for any other dynamic identifier -- both make the "is this safe to
interpolate" judgment call once, in one tested place, instead of a
hand-written ``# noqa: S608`` justification comment at every call site.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

__all__ = ["Allowlist", "in_clause"]


def in_clause(values: Sequence[Any]) -> str:
    """A ``(?, ?, ...)`` placeholder group sized to ``len(values)``, for a
    ``col IN (...)`` clause.

    Always pair the returned string with *values* itself as the bound
    parameters -- never format the values into the SQL text::

        placeholders = in_clause(tickers)
        conn.execute(
            f"SELECT * FROM assets WHERE ticker IN {placeholders}",  # noqa: S608
            tickers,
        )

    Raises :class:`ValueError` on an empty sequence -- an empty ``IN ()`` is
    invalid SQL and almost always a caller bug (e.g. an unfiltered list),
    not an intentionally empty-result query. Callers that legitimately want
    "no rows" for an empty input should short-circuit before calling this.
    """
    if not values:
        raise ValueError("in_clause() requires at least one value")
    return "(" + ",".join("?" * len(values)) + ")"


class Allowlist:
    """A fixed set of names safe to interpolate into SQL text as identifiers.

    Construct once per set of legal names (e.g. the columns a caller may sort
    by, or the ``SET`` targets a correction endpoint may touch), then call
    :meth:`check` on every caller-supplied name before it reaches an
    f-string::

        _ORDER_COLUMNS = Allowlist("discovered_at", "ticker", "status")

        def list_urls(db: Database, *, order_by: str = "discovered_at") -> list[dict]:
            column = _ORDER_COLUMNS.check(order_by)
            cur = db.execute(f"SELECT * FROM discovered_urls ORDER BY {column}")  # noqa: S608
            return [dict(row) for row in cur]

    :meth:`check` returns *name* unchanged on success; raises
    :class:`ValueError` (never silently drops or substitutes a default) when
    *name* is not in the set. The caller decides how to surface that (a 400
    response, an ``argparse`` error, a plain exception) -- this class only
    refuses to let unrecognized text reach SQL.
    """

    def __init__(self, *names: str) -> None:
        self._names = frozenset(names)

    def check(self, name: str) -> str:
        if name not in self._names:
            raise ValueError(f"{name!r} is not one of the allowed names: {sorted(self._names)}")
        return name

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(sorted(self._names))
