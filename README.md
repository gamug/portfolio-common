# portfolio-common

The shared database engine — swappable in one place — and injection-safe
query-building primitives shared across the **Portfolio Thesis** repos
(`portfolio-data-mining`, `portfolio-nlp`, `portfolio-financial-analysis`,
`portfolio-knowledge-graph`, `portfolio-reports`, `portfolio-app`).

As of **v1.0.0** this repo is deliberately narrow: it owns connection
lifecycle, pragma policy, ATTACH/DETACH, and dynamic-SQL safety — nothing
else. Business/domain code that used to live here (the news-pipeline urls.db
schema, the S&P 500 universe helpers, the `kg_schema` analysis-DB contract,
the `news_nlp` results-DB layer) has moved out to the repo that owns it; see
[Migrating from pre-1.0](#migrating-from-pre-10) below. **v1.1.0** adds one
narrow, deliberate exception — see `news_export` below. **v1.2.0** adds the
engine-agnostic seam (`Dialect`, `connect_url`, `Row`, `two_store`,
introspection helpers) so consumers never `import sqlite3` of their own — see
`CHANGELOG.md`.

| Module | What it provides |
|---|---|
| `portfolio_common.db.Database` | The one connection class. Open via `Database.connect_url(url, **kw)` — a filesystem path, a `file:` URI, or `sqlite:///path` (scheme dispatch; unknown `scheme://` raises). `Database.connect(path, *, read_only=, wal=, foreign_keys=, create_parents=, busy_timeout_ms=, check_same_thread=, uri=)` is the lower-level form. `.dialect` (see `dialect` below). `.attach` / `.detach` for a second schema (stale-WAL preflight on read-only attach). `.table_columns` / `.table_exists` / `.ensure_columns` / `.create_schema` / `.copy_row_lean` — runtime introspection + DDL, so consumers don't hand-write `PRAGMA`. `.execute()`, `.executemany()`, `.executescript()`, `.transaction()`, `.commit()`, `.rollback()`, `.close()`, `.raw`. Subclass it for domain-specific per-connection state. |
| `portfolio_common.db.Dialect` / `get_dialect()` | The per-engine SQL fragments a consumer's `queries.py` needs: `placeholder` / `placeholders(n)`, `insert` / `insert_or_ignore` / `upsert` / `insert_or_ignore_select`, `year_expr` / `year_month_expr` / `week_start_expr` / `week_end_expr` / `current_date_expr`, `group_concat`, `excludes_bare_digit`, `autoincrement_pk`. `SqliteDialect` emits the strings the consumers used inline before the seam. Pure string builder — identifier safety stays `Allowlist`'s job. |
| `portfolio_common.db.Row` / `RowLike` | The row type consumers annotate query results with (alias for `sqlite3.Row` today), and the mapping + positional + `dict(row)` access contract (`RowLike`) any future engine's row factory must meet. |
| `portfolio_common.db.two_store` | `connect_two_store(primary, secondary, *, alias="source", factory=, **kw)` + `TwoTierDatabase` (tracks `read_schema`) — writable primary + optional read-only attached secondary, the generic form of `portfolio-nlp`'s two-tier SOURCE/RESULTS pattern. |
| `portfolio_common.db.in_clause` | Builds a `(?, ?, ...)` placeholder group sized to the input, for `col IN (...)` clauses — always pair with the same values bound as parameters. |
| `portfolio_common.db.Allowlist` | A fixed set of names safe to interpolate into SQL text as identifiers (column, table, sort direction, ...); `.check(name)` returns the name or raises. The only two sanctioned ways to build dynamic SQL text in any repo built on this library — see the module docstring in `src/portfolio_common/db/safety.py`. |
| `portfolio_common.news_export` | `connect_readonly(source_db, results_db)` + `fetch_processed_articles(db, articles_rel, limit=)` — the read-only two-tier connect + join query for the news-NLP RESULTS store, shared by exactly the two repos that interoperate through it: `portfolio-nlp` (writes the schema, owns everything else about it in its own `src/news_nlp/`) and `portfolio-knowledge-graph` (only reads this join). Not a general invitation to add more `news_nlp` reads here — see the module docstring. |

## Use it from another repo

Add a git-pinned dependency (resolved by `uv` via `[tool.uv.sources]`):

```toml
# pyproject.toml
dependencies = ["portfolio-common"]

[tool.uv.sources]
portfolio-common = { git = "https://github.com/gamug/portfolio-common", tag = "v1.2.0" }
```

For local development against a checkout next to your repo, override the
source with an editable path:

```toml
[tool.uv.sources]
portfolio-common = { path = "../portfolio-common", editable = true }
```

## `business_folders/`

`business_folders/<repo>/` holds domain code staged for relocation into the
repo that owns it — `financial_analysis` (→ `portfolio-financial-analysis`),
`news_nlp` (→ `portfolio-nlp`), `data_mining` (→ `portfolio-data-mining`).
It is **not** part of the installed `portfolio-common` package (it lives
outside `src/`, so `hatchling` never packages it) — it exists only until each
owning repo has pulled its folder in and this repo's copy is deleted. See
`business_folders/README.md` and each subfolder's own `README.md` for the
adoption steps, and the `docs/portfolio-common-v1-migration-plan.md` this
refactor pushed to each of the four consumer repos.

Every query in every `business_folders/*` domain lives in one ordered,
documented place (a `queries.py` or `queries/` package, per domain) — a
module-level docstring table of contents lists every query function with a
one-line purpose, so "what can this domain do to the database" is always one
file away, and orchestration/business logic never embeds SQL text directly.

## `news_export` — the one deliberate exception

`business_folders/news_nlp/` (the full news-NLP domain: schema, write-side
pipeline helpers, corrections, taxonomy, `sector_summary`) moved out to
`portfolio-nlp`'s own `src/news_nlp/` per the rule above — one owner, no
exceptions. `portfolio_common.news_export` is a different case: it's the read
join two *separate* repos need (`portfolio-nlp` writes it,
`portfolio-knowledge-graph` only reads it), so instead of either repo owning
a copy the other depends on, or `portfolio-knowledge-graph` carrying a
hand-duplicated copy of `portfolio-nlp`'s query (drifting out of sync with it
was the actual cost that motivated adding this), the one join both consumers
need lives here, where both already depend on `portfolio_common.db` for the
connection engine regardless. This is the only such exception on purpose —
see the module docstring in `src/portfolio_common/news_export.py` before
adding a second one.

## Migrating from pre-1.0

v1.0.0 is a clean break — there is no backward-compatible shim for
`portfolio_common.db.connect`, `.kg_schema`, `.news_nlp`, `.portfolio`,
`.universe_history`, or `.errors`. Each consumer repo has its own
`docs/portfolio-common-v1-migration-plan.md` (pushed there as part of this
change) describing exactly what to pull in from `business_folders/` and how
to adopt `Database`/`in_clause`/`Allowlist` for its own SQL. See
`CHANGELOG.md` for the full rationale.

## Develop

```bash
uv sync
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
uv run pytest
uv run ruff check .
uv run mypy --config-file=.code_quality/mypy.ini src
```
