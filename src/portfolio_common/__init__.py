"""Shared building blocks for the Portfolio Thesis repos.

- `db` / `schema`: one SQLite connection factory + the canonical pipeline
  DDL for the shared `urls.db` (`discovered_urls` -> `articles`).
- `portfolio`: the live S&P 500 universe (Wikipedia scrape + in-process cache).
- `universe_history`: point-in-time (`as_of`) membership, backed by its own
  `universe.db`.
- `errors`: the shared `UpstreamDataError` type.
- `kg_schema`: the analysis-workstream DB contract for `KG_FINANCIAL_DB` --
  additive DDL, non-additive migrations, the `schema_version` floor, the `v_*`
  read-contract views, `env` path resolution, point-in-time `universe.db` reads
  (`universe_source`), `coverage`, `provenance`, `rundate`, and its own
  `connect()` factory. Imported as `portfolio_common.kg_schema`.
- `news_nlp`: the news-NLP results-DB layer -- the five result-table schema, the
  two-tier SOURCE/RESULTS connection machinery (read-only `ATTACH` of the crawl
  DB), the pipeline read/write helpers, `sector_summary` composition, the FastAPI
  query helpers, the manual result-row corrections, and the 10-category taxonomy.
  Imported as `portfolio_common.news_nlp`.
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
