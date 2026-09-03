"""Shared building blocks for the Portfolio Thesis repos.

- `db` / `schema`: one SQLite connection factory + the canonical pipeline
  DDL for the shared `urls.db` (`discovered_urls` -> `articles`).
- `portfolio`: the live S&P 500 universe (Wikipedia scrape + in-process cache).
- `universe_history`: point-in-time (`as_of`) membership, backed by its own
  `universe.db`.
- `errors`: the shared `UpstreamDataError` type.
"""

from portfolio_common.db import connect, enable_foreign_keys, resolve_db_path
from portfolio_common.errors import UpstreamDataError
from portfolio_common.schema import SCHEMA_VERSION, apply_schema, run_migrations

__all__ = [
    "SCHEMA_VERSION",
    "UpstreamDataError",
    "apply_schema",
    "connect",
    "enable_foreign_keys",
    "resolve_db_path",
    "run_migrations",
]
