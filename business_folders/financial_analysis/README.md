# financial_analysis (staging)

Staging area for the `kg_schema` domain -- extracted out of
`portfolio_common.kg_schema`, owned by `portfolio-financial-analysis`. It becomes
`src/kg_schema/` there, replacing the current git-dependency import. DB-touching
functions now take a `portfolio_common.db.Database` instead of a raw
`sqlite3.Connection`; intra-package imports are relative (`from . import ...`) so
the package works unmodified whether it's imported as top-level `kg_schema` (here)
or nested however the target repo ends up structuring `src/`.

## Layout

Every SQL query in the domain lives in one ordered, documented `queries.py`
(with a module-docstring table of contents), matching the convention used
in `business_folders/data_mining` and `business_folders/news_nlp`:

- `queries.py` -- all of it: `universe.db` reads (`connect_ro`, `members_asof`,
  `symbols_asof`, `resolve_asset_ids` -- absorbed from the former
  `universe_source.py`), the data-coverage query layer (`check_coverage`,
  `persist_coverage` -- absorbed from `coverage.py`), `schema_version` CRUD
  (`ensure`, `current_version`, `record` -- absorbed from the former
  `version.py`), and `universe_membership.reconcile` (absorbed from the former
  `universe_membership.py`).
- `coverage.py` -- now pure business logic only: the `SymbolCoverage` /
  `CoverageReport` dataclasses and their roll-up properties (`covered`,
  `missing`, `fraction`, ...), no SQL.
- `ddl.py`, `views.py`, `migrations.py` -- schema definition/migration, kept
  separate from `queries.py` (DDL and versioned rebuilds are a different
  concern from row-level reads/writes, same split `news_nlp` uses between
  `schema.py` and `queries.py`).
- `provenance.py`, `rundate.py`, `env.py` -- pure business logic / config, no
  DB access.
- `db.py` -- the thin `Database`-wrapping connection factory (`connect`,
  `connect_ro`).
- `cli.py` -- shared `migrate`/`coverage` CLI orchestration, calling the
  above; no SQL of its own.

Verified end to end (not just import-clean): `ensure()`, `run_migrate`,
`run_coverage`, `current_version`, and `reconcile` all exercised against real
temp SQLite files after the consolidation.

When this lands in `portfolio-financial-analysis`, 28 of its own `src/` files import
`portfolio_common.kg_schema` -- not just the 7 `db.py`/`news_db.py` modules; also
every agent's `cli.py`/`config.py`/`pipeline.py`, `cycle/orchestrator.py`,
`cycle/data.py`, `quant/{evaluate,persist,returns,actions}.py` and
`api/{db,config,routers/universe}.py` -- plus 7 test files. All need
`from portfolio_common import kg_schema` / `from portfolio_common.kg_schema import X`
rewritten to `import kg_schema` / `from kg_schema import X`.

This is also the domain with the most ad hoc `sqlite3`/dynamic-SQL call sites left
in `portfolio-financial-analysis` itself: `quant/db.py`, `pricing_agent/db.py`,
`fundamental_agent/db.py`, `cycle/data.py`. Migrating those onto
`portfolio_common.db.Database` / `in_clause` / `Allowlist` is out of scope here --
a follow-up for the migration plan.
