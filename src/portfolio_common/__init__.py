"""portfolio-common: the shared database engine (swappable in one place)
and injection-safe query-building primitives for the Portfolio Thesis repos.

The engine is SQLite today. Consumers stay engine-agnostic by going through
:class:`~portfolio_common.db.engine.Database` (open via
:meth:`~portfolio_common.db.engine.Database.connect_url`), the per-engine SQL
fragments in :class:`~portfolio_common.db.dialect.Dialect` (``get_dialect()``),
and the :data:`~portfolio_common.db.engine.Row` type -- never ``import
sqlite3`` of their own. See ``CHANGELOG.md`` v1.2.0.

Business/domain code that used to live here (kg_schema, news_nlp, the
urls.db pipeline, the S&P 500 universe helpers) has moved to
``business_folders/`` in this repo, staged for relocation into the repo
that owns it. See ``business_folders/README.md`` and ``CHANGELOG.md``
(v1.0.0) for the migration.
"""

from __future__ import annotations

from portfolio_common.db import Allowlist, Database, Dialect, Row, get_dialect, in_clause

__all__ = ["Allowlist", "Database", "Dialect", "Row", "get_dialect", "in_clause"]
