# business_folders/data_mining

Staging area for the **data_mining** business domain, extracted out of
`portfolio-common` (see the repo root `README.md`/`CHANGELOG.md` for the
overall `business_folders/` migration). Owned by `portfolio-data-mining`.
Nothing else in this ecosystem imports the symbols below.

## What's here

- `data_mining/db.py`, `data_mining/schema.py` -- the `data/urls.db`
  connection factory and canonical DDL, thin wrappers around
  `portfolio_common.db.Database`.
- `data_mining/portfolio.py` -- the live tracked S&P 500 universe (Wikipedia
  scrape + in-process cache): `list_universe`, `resolve_symbol`, `is_tracked`.
- `data_mining/universe_history.py` / `data_mining/queries.py` -- point-in-time
  (`as_of`) S&P 500 membership backed by `data/universe.db`; `queries.py`
  holds the DB-touching functions, `universe_history.py` the Wikipedia
  parsing/reconstruction and the public `backfill_from_changes` /
  `record_snapshot` / `query_as_of` / `resolve_as_of` operations.
- `data_mining/errors.py` -- `UpstreamDataError`, the shared upstream-failure
  exception type.

## Landing this in `portfolio-data-mining`

When this folder is physically relocated into `portfolio-data-mining`, the
`data_mining/` package here becomes that repo's own importable package --
suggest `src/data_mining/`, but that's the target repo maintainer's call.

Confirmed current consumers (grep'd from `portfolio-data-mining`), whose
imports change on landing:

- `cli/pricing_cli.py` and `apps/pricing_api.py` import
  `portfolio_common.portfolio.list_universe` / `.resolve_symbol`,
  `portfolio_common.universe_history.backfill_from_changes` /
  `.record_snapshot`, and `portfolio_common.errors.UpstreamDataError`.

Those two files' imports (`portfolio_common.X` -> `data_mining.X`) are
exactly what needs to change when this lands there.
