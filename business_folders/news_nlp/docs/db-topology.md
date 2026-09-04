# news_nlp database topology: the two-tier contract

`news_nlp` uses **two** SQLite databases with distinct roles, selected by two
environment variables and never conflated in code. Owned/consumed by
`portfolio-nlp`; operator recipes (which CLI/env to set for a run vs. serving)
live in that repo's `docs/db-topology.md`.

| | **SOURCE** | **RESULTS** |
|---|---|---|
| env var | `SOURCE_DATABASE_URL` | `DATABASE_URL` |
| resolver | `news_nlp.env.source_db_path()` | `news_nlp.env.results_db_path()` |
| default | none — **required** for the text-reading stages | `data/nlp.db` |
| opened | read-only (`file:…?mode=ro`), `ATTACH`ed as schema `source` | read/write, schema `main` |
| holds | `articles` **including `body_text`** (written by the upstream crawler) | the 5 result tables (`news_nlp.schema.SCHEMA`) + a lean `articles` subset (**no `body_text`**) |
| written | never | result rows, plus one lean `articles` row per processed article |

**Path resolution** (`news_nlp.env`): an **absolute** value is used as-is; a
**relative** value is left relative — resolved against the process's current
working directory when SQLite opens the file. Unset → `results_db_path()` falls
back to `data/nlp.db`, `source_db_path()` → `None`.

## How a pipeline run uses both

`news_nlp.db.connect_pipeline()`:

1. opens the RESULTS store read/write (`main`) as a `NewsNlpDatabase` (a
   `portfolio_common.db.Database` subclass) via `NewsNlpDatabase.connect(…,
   uri=True, foreign_keys=True)`;
2. unless `SOURCE_DATABASE_URL` resolves to the **same path** as `DATABASE_URL`,
   `ATTACH`es the SOURCE store read-only (`file:…?mode=ro`) as `source` and flips
   `db.articles_rel` to `"source"` (`attach_source`, which delegates the ATTACH
   itself -- including the stale-WAL preflight -- to
   `Database.attach(source, "source", read_only=True)`). The read-only ATTACH is
   only honored because the RESULTS connection was opened `uri=True`.
3. `news_nlp.db.require_source_text()` then fails fast (before any model loads) if
   that `articles` table has no `body_text` column or no non-empty `body_text`
   row — the common "pointed a text stage at the results store" mistake.

The three `body_text` readers (`fetch_pending_articles`,
`fetch_pending_category_articles`, `fetch_pending_company_summaries`) qualify
`articles` with `db._articles_rel(conn)` (Allowlist-checked against `"main"` /
`"source"` -- see `db.py`), so they read `source.articles` during a two-tier run
and `main.articles` otherwise. All result-table joins stay in
`main`. Every result-table write (`write_sentiment` / `write_category` /
`write_entities` / `write_company_summary`) first `db._ensure_article_row`
`INSERT OR IGNORE`s the lean `articles` row (metadata only) from `source` into
`main`, so the RESULTS store stays foreign-key-consistent on its own — no
separate migration step.

The `sector_summary` stage and every query/correction helper read only result
tables + `articles` metadata, never `body_text`, so they need **no** SOURCE — a
plain `news_nlp.db.connect()` is enough.

## External consumers

`list_articles` / `get_article_detail` / the `*_stats` functions are shaped for
`portfolio-nlp`'s own FastAPI endpoints (paginated, dict-per-call). A consumer
outside `portfolio-nlp` entirely that just wants every fully-processed article as
plain rows — e.g. a downstream knowledge-graph ETL — should use
`news_nlp.fetch_processed_articles(conn, limit=...)` instead of writing its own
join: `connect_pipeline(results_db=..., source_db=...)` then this one call hides
the SOURCE/RESULTS split the same way the pipeline's own readers do. Don't import
`news_nlp.db._articles_rel` (or any other underscore-prefixed name) directly from
outside this package to build a bespoke query — it's internal, not covered by this
package's version-compatibility guarantees; ask for (or add) a named export like
this one instead.

## Caveats

- **Stale WAL on the SOURCE.** A `mode=ro` open fails if the SOURCE was left with
  an uncheckpointed `-wal` file and no writer to recover it. Checkpoint it (or
  keep a live writer) before a run. Do not work around this with `immutable=1`.
- **`SOURCE_DATABASE_URL` is required** for the text-reading stages. Pointing a
  single `DATABASE_URL` at the crawl DB now errors until `SOURCE_DATABASE_URL` is
  set (or both vars point at the same file).
