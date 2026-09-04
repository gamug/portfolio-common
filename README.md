# portfolio-common

Shared building blocks for the **Portfolio Thesis** repos
(`portfolio-data-mining`, `portfolio-nlp`, `portfolio-financial-analysis`,
`portfolio-knowledge-graph`, `portfolio-reports`, `portfolio-app`). One
source of truth for the code every repo would otherwise re-implement against
the shared SQLite databases.

| Module | What it provides |
|---|---|
| `portfolio_common.db` | `connect(db_path, *, wal=, foreign_keys=, check_same_thread=, uri=, factory=)` — the single SQLite connection factory (row factory + `busy_timeout` always; `wal=True` adds `journal_mode=WAL` + `synchronous=NORMAL` for the writer; `foreign_keys=True` for readers that enforce the FK; `uri=`/`factory=` for the `news_nlp` two-tier ATTACH path). Plus `resolve_db_path()` (`$DATABASE_URL`) and `enable_foreign_keys()`. |
| `portfolio_common.schema` | Canonical DDL for the news pipeline DB (`discovered_urls`, `discovery_progress`, `articles`), `SCHEMA_VERSION` (stamped via `PRAGMA user_version`), `apply_schema()`, and forward-only, idempotent `run_migrations()`. |
| `portfolio_common.news_nlp` | The news-NLP **results** DB layer, shared with `portfolio-nlp`: the five result-table `SCHEMA` + `init_schema()`, the two-tier SOURCE/RESULTS connection machinery (`connect()`, `connect_pipeline()`, `attach_source()`, `require_source_text()` — read-only `ATTACH` of the crawl DB), `env` path resolution (`$DATABASE_URL` / `$SOURCE_DATABASE_URL`), the pipeline read/write helpers, `sector_summary` composition, the FastAPI query helpers, `corrections`, and the 10-category `taxonomy`. See `docs/news-nlp-db-topology.md`. |
| `portfolio_common.portfolio` | The live S&P 500 universe — Wikipedia scrape + in-process cache. `list_universe()`, `resolve_symbol()`, `is_tracked()`. |
| `portfolio_common.universe_history` | Point-in-time (`as_of`) membership, backed by its own `universe.db` (`$UNIVERSE_DB_PATH`). `backfill_from_changes()`, `record_snapshot()`, `query_as_of()`, `resolve_as_of()`. |
| `portfolio_common.errors` | `UpstreamDataError` — the shared upstream-provider failure type. |

## Use it from another repo

Add a git-pinned dependency (resolved by `uv` via `[tool.uv.sources]`):

```toml
# pyproject.toml
dependencies = ["portfolio-common"]

[tool.uv.sources]
portfolio-common = { git = "https://github.com/gamug/portfolio-common", tag = "v0.3.0" }
```

For local development against a checkout next to your repo, override the
source with an editable path:

```toml
[tool.uv.sources]
portfolio-common = { path = "../portfolio-common", editable = true }
```

## Versioning

SemVer on the schema contract: additive DDL (new nullable column / table /
index) is a **minor** bump, a rename/drop/type change is **major**. Every
schema change ships a matching idempotent step in `run_migrations()` and
bumps `SCHEMA_VERSION`, so a consumer pinned to an older tag can still open
a database a newer writer has migrated.

## Develop

```bash
uv sync
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
uv run pytest
uv run ruff check .
uv run mypy --config-file=.code_quality/mypy.ini src
```
