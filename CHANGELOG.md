# Changelog

## v1.2.0 — engine-agnostic seam: consumers stop naming SQLite

Goal: the database engine is known in exactly one place — here. A future
engine swap becomes a new `Dialect` implementation plus a `connect_url`
scheme, with nothing in `portfolio-nlp` / `-knowledge-graph` /
`-financial-analysis` / `-data-mining` changing. SQLite stays the only real
backend; this release adds no second engine and changes no SQL semantics —
`SqliteDialect` emits the exact strings the consumers used inline.

### Added

- **`portfolio_common.db.dialect`** — `Dialect` (Protocol) + `SqliteDialect`
  + `get_dialect(name="sqlite")`. The per-engine SQL fragments consumers
  need: parameter marker / `placeholders(n)`, `insert` / `insert_or_ignore`
  / `upsert` (SQLite: `INSERT OR REPLACE`) / `insert_or_ignore_select`,
  `year_expr` / `year_month_expr` / `week_start_expr` / `week_end_expr`
  (Monday-start ISO week) / `current_date_expr` (UTC), `group_concat`,
  `excludes_bare_digit` (`NOT GLOB '[0-9]'`), `autoincrement_pk`. Pure
  string builder — identifier safety stays the caller's job via `Allowlist`.
- **`Database.connect_url(url, **kw)`** — opens a filesystem path, a `file:`
  URI, or a `sqlite:///path` URL (scheme dispatch; `"D:/x"` is a path, not a
  `d:` URL; unknown `scheme://` raises). Always `uri=True` so a later
  read-only `ATTACH` is honored. The one connect entry point a consumer's
  `connect()` should call.
- **`Database.table_columns` / `table_exists` / `ensure_columns` /
  `create_schema` / `copy_row_lean`** — runtime schema introspection and
  DDL, so consumers stop hand-writing `PRAGMA table_info` / `executescript`
  / cross-schema `INSERT ... SELECT`.
- **`portfolio_common.db.Row`** (alias for `sqlite3.Row`) + **`RowLike`**
  (Protocol) — the row type consumers annotate with, and the mapping +
  positional + `dict(row)` access contract any future engine's row factory
  must meet. This hybrid requirement is the main constraint the
  "swap in one place" promise puts on a non-SQLite engine.
- **`portfolio_common.db.two_store`** — `connect_two_store(primary,
  secondary, *, alias="source", factory=TwoTierDatabase, **connect_kwargs)`
  and `TwoTierDatabase` (tracks `read_schema`). The generic form of
  `portfolio-nlp`'s two-tier SOURCE/RESULTS attach; owns the `"main"` /
  attached-alias literals and the same-file short-circuit.

### Changed

- `news_export.connect_readonly` now delegates to `connect_two_store`
  (identical behaviour, same `(db, "source"|"main")` return; the object is
  now a `TwoTierDatabase`, still a `Database`).
  `news_export.fetch_processed_articles` return type is now `list[Row]` — no
  SQL change.
- Package docstrings no longer describe the engine as immutably SQLite.

### Compatibility

Additive. Every pre-1.2 public name, signature, and return shape is
preserved; `Row` is still `sqlite3.Row`. v1.0.0 / v1.1.0 consumers are
unaffected until they choose to adopt the seam.

## v1.1.0 — `news_export`: one shared read contract, not a re-merge

Adds `portfolio_common.news_export` (`connect_readonly` +
`fetch_processed_articles`): the read-only two-tier SOURCE/RESULTS connect
and the `articles` ⋈ `article_sentiment` ⋈ `article_category` join, for the
one case where v1.0.0's "one owner per domain" rule left two repos needing
the same code: `portfolio-nlp` (which owns writing that schema) and
`portfolio-knowledge-graph` (which only reads it, from `etl/news_to_rdf.py`).

Between v1.0.0 and this release, `portfolio-knowledge-graph` carried a local
copy of this exact query (`etl/queries.py`, added because `portfolio-nlp`
had no tagged release to depend on yet) — its own docstring flagged the real
cost: a second copy of the join that had to be hand-kept in sync with
`portfolio-nlp`'s `news_nlp.queries.fetch_processed_articles` if that schema
ever changed. Rather than resolve that by adding a repo-to-repo dependency
(`portfolio-knowledge-graph` on `portfolio-nlp`) or reintroducing the full
pre-1.0 `news_nlp` package here, this release carries only the read join
itself — the narrowest thing that is genuinely shared, not a re-merge of the
domain. `portfolio-nlp`'s `news_nlp.queries.fetch_processed_articles` and
`portfolio-knowledge-graph`'s `etl/news_to_rdf.py` both now call this module
directly; `etl/queries.py`'s local copy is deleted. `news_nlp`'s schema
ownership, corrections, taxonomy, and `sector_summary` composition are
untouched by this release and stay solely in `portfolio-nlp`.

Additive, no breaking changes: v1.0.0 consumers unaffected.

## v1.0.0 — DB engine + business_folders split (breaking)

**This is a clean break. There is no backward-compatible shim for any
pre-1.0 public function.**

### Why

`portfolio-common` used to mix two unrelated concerns: a generic SQLite
connection engine, and business/domain logic owned by specific downstream
repos. Engine mechanics were duplicated four times (`db.py.connect`,
`kg_schema/db.py.connect`/`connect_ro`, `news_nlp/db.py`'s two-tier
ATTACH machinery built on top of one of those, and a fourth ad hoc
`sqlite3.connect` recipe private to `universe_history._connect` that was
missing `busy_timeout`/WAL/FK entirely) — each with slightly different
defaults, making future database changes (a pragma policy change, or an
engine swap) something that had to be found and fixed in four places. And
because business code for three unrelated repos lived in one shared
library, a schema change for one repo's domain required touching a
dependency every other repo also pinned.

### What changed

- **Added** `portfolio_common.db.Database` — the single connection class,
  subsuming all four prior recipes behind one API (`connect`, `attach`/
  `detach`, `execute`/`executemany`/`executescript`, `transaction`,
  `commit`/`rollback`/`close`, `.raw` escape hatch). See
  `src/portfolio_common/db/engine.py`.
- **Added** `portfolio_common.db.in_clause` and `portfolio_common.db.Allowlist`
  — injection-prevention primitives replacing ~10 scattered hand-written
  `# noqa: S608` justification comments across the codebase with one
  reusable, unit-tested primitive each. See
  `src/portfolio_common/db/safety.py`.
- **Removed** `portfolio_common.db.connect`/`resolve_db_path`/
  `enable_foreign_keys`/`DEFAULT_DB_PATH`/`BUSY_TIMEOUT_MS`,
  `portfolio_common.schema`, `portfolio_common.portfolio`,
  `portfolio_common.universe_history`, `portfolio_common.errors`,
  `portfolio_common.kg_schema` (all of it), `portfolio_common.news_nlp` (all
  of it). Extracted, largely as-is but rewritten atop `Database`, to:
  - `business_folders/data_mining/` (owned by `portfolio-data-mining`) —
    `db.py`/`schema.py`/`portfolio.py`/`universe_history.py`/`errors.py`.
    Fixes a real behavior gap in the process: `universe_history`'s
    connection now gets the same `busy_timeout`/pragma policy as every
    other connection in the ecosystem, instead of none.
  - `business_folders/financial_analysis/` (owned by
    `portfolio-financial-analysis`) — all of `kg_schema/`.
  - `business_folders/news_nlp/` (owned by `portfolio-nlp`) — all of
    `news_nlp/`. The old `_Connection(sqlite3.Connection)` subclass (a
    workaround for `sqlite3.Connection` rejecting arbitrary instance
    attributes) is gone — `Database` wraps `sqlite3.Connection` by
    composition, so the two-tier SOURCE/RESULTS state
    (`articles_rel`/`lean_article_cols`) is now an ordinary Python
    attribute on a `Database` subclass.
- **`business_folders/`** is staging, not a permanent home: each folder is
  meant to be copied into the repo named in its own `README.md` and then
  deleted from here. It sits outside `src/`, so it was never part of the
  installed package.
- **Dependencies trimmed**: `httpx`, `beautifulsoup4`, `pandas` dropped —
  they were only needed by `portfolio.py`'s Wikipedia scrape, which moved to
  `business_folders/data_mining/`.
- Each of the four consumer repos received a
  `docs/portfolio-common-v1-migration-plan.md` (pushed directly, as part of
  this change) describing exactly what to pull in and how to adopt
  `Database`/`in_clause`/`Allowlist` for its own remaining ad hoc SQL.

### Upgrading

There is no incremental upgrade path — pinning your `portfolio-common` tag
to `v1.0.0` breaks every import of the removed modules immediately. See your
repo's `docs/portfolio-common-v1-migration-plan.md` for the exact steps.

## v0.4.0 and earlier

See git history — the changelog starts at v1.0.0.
