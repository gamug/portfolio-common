# portfolio-common

Shared building blocks for the **Portfolio Thesis** repos
(`portfolio-data-mining`, `portfolio-nlp`, `portfolio-financial-analysis`,
`portfolio-knowledge-graph`, `portfolio-reports`, `portfolio-app`). One
source of truth for the code every repo would otherwise re-implement against
the shared SQLite databases.

| Module | What it provides |
|---|---|
| `portfolio_common.db` | `connect(db_path, *, wal=, foreign_keys=, check_same_thread=)` — the single SQLite connection factory (row factory + `busy_timeout` always; `wal=True` adds `journal_mode=WAL` + `synchronous=NORMAL` for the writer; `foreign_keys=True` for readers that enforce the FK). Plus `resolve_db_path()` (`$DATABASE_URL`) and `enable_foreign_keys()`. |
| `portfolio_common.schema` | Canonical DDL for the news pipeline DB (`discovered_urls`, `discovery_progress`, `articles`), `SCHEMA_VERSION` (stamped via `PRAGMA user_version`), `apply_schema()`, and forward-only, idempotent `run_migrations()`. |
| `portfolio_common.portfolio` | The live S&P 500 universe — Wikipedia scrape + in-process cache. `list_universe()`, `resolve_symbol()`, `is_tracked()`. |
| `portfolio_common.universe_history` | Point-in-time (`as_of`) membership, backed by its own `universe.db` (`$UNIVERSE_DB_PATH`). `backfill_from_changes()`, `record_snapshot()`, `query_as_of()`, `resolve_as_of()`. |
| `portfolio_common.errors` | `UpstreamDataError` — the shared upstream-provider failure type. |

## Use it from another repo

Add a git-pinned dependency (resolved by `uv` via `[tool.uv.sources]`):

```toml
# pyproject.toml
dependencies = ["portfolio-common"]

[tool.uv.sources]
portfolio-common = { git = "https://github.com/gamug/portfolio-common", tag = "v0.1.0" }
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
