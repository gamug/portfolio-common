# portfolio-common

The single SQLite connection engine and injection-safe query-building
primitives shared across the **Portfolio Thesis** repos
(`portfolio-data-mining`, `portfolio-nlp`, `portfolio-financial-analysis`,
`portfolio-knowledge-graph`, `portfolio-reports`, `portfolio-app`).

As of **v1.0.0** this repo is deliberately narrow: it owns connection
lifecycle, pragma policy, ATTACH/DETACH, and dynamic-SQL safety — nothing
else. Business/domain code that used to live here (the news-pipeline urls.db
schema, the S&P 500 universe helpers, the `kg_schema` analysis-DB contract,
the `news_nlp` results-DB layer) has moved out to the repo that owns it; see
[Migrating from pre-1.0](#migrating-from-pre-10) below.

| Module | What it provides |
|---|---|
| `portfolio_common.db.Database` | The one SQLite connection class. `Database.connect(path, *, read_only=, wal=, foreign_keys=, create_parents=, busy_timeout_ms=, check_same_thread=, uri=)` — row factory + `busy_timeout` always (read/write mode); `read_only=True` opens `file:{path}?mode=ro`; `wal=True` for a writer; `foreign_keys=True` for FK enforcement. `.attach(path, alias, *, read_only=)` / `.detach(alias)` for a second schema (includes a stale-WAL preflight check on read-only attach). `.execute()`, `.executemany()`, `.executescript()`, `.transaction()`, `.commit()`, `.rollback()`, `.close()`, `.raw` (escape hatch to the underlying `sqlite3.Connection`). Subclass it for domain-specific per-connection state — see how each `business_folders/*` domain does this. |
| `portfolio_common.db.in_clause` | Builds a `(?, ?, ...)` placeholder group sized to the input, for `col IN (...)` clauses — always pair with the same values bound as parameters. |
| `portfolio_common.db.Allowlist` | A fixed set of names safe to interpolate into SQL text as identifiers (column, table, sort direction, ...); `.check(name)` returns the name or raises. The only two sanctioned ways to build dynamic SQL text in any repo built on this library — see the module docstring in `src/portfolio_common/db/safety.py`. |

## Use it from another repo

Add a git-pinned dependency (resolved by `uv` via `[tool.uv.sources]`):

```toml
# pyproject.toml
dependencies = ["portfolio-common"]

[tool.uv.sources]
portfolio-common = { git = "https://github.com/gamug/portfolio-common", tag = "v1.0.0" }
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
