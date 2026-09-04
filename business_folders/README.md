# business_folders/

Staging area for domain code extracted out of `portfolio_common` in the
v1.0.0 DB-engine split. Each subfolder here is owned by exactly one of the
Portfolio Thesis repos and is meant to be copied into that repo's own `src/`
and then **deleted from here** once adopted — this directory is not part of
the installed `portfolio-common` package (it lives outside `src/`, so
`hatchling` never packages it).

| Folder | Owning repo | What it holds |
|---|---|---|
| `data_mining/` | `portfolio-data-mining` | The urls.db pipeline connection factory + DDL, the S&P 500 universe helpers (`portfolio.py`, `universe_history.py`), `UpstreamDataError`. |
| `financial_analysis/` | `portfolio-financial-analysis` | The `kg_schema` analysis-DB contract (DDL, migrations, coverage, provenance, rundate, universe membership/source, views, shared CLI). |
| `news_nlp/` | `portfolio-nlp` | The news-NLP results-DB layer: schema, two-tier SOURCE/RESULTS connection machinery, query/write/correction helpers, sector-summary composition, taxonomy. |

Each folder has its own `README.md` with the exact adoption steps and its
own `tests/` (moved from `portfolio-common`'s test suite, adapted to the new
`Database`-based API) proving the extracted code still works. All three are
built on `portfolio_common.db.Database`/`in_clause`/`Allowlist` (the package
that stays in `src/portfolio_common/`) rather than raw `sqlite3` — that
dependency doesn't go away when a folder is adopted; the target repo keeps
`portfolio-common` as a dependency for the engine, it just stops depending on
it for this business code.

See each owning repo's own `docs/portfolio-common-v1-migration-plan.md`
(pushed there as part of this change) for the full per-repo plan, and
`portfolio-common`'s `CHANGELOG.md` for why this split happened.
