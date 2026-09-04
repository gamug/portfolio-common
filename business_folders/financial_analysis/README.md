# financial_analysis (staging)

Staging area for the `kg_schema` domain -- extracted out of
`portfolio_common.kg_schema`, owned by `portfolio-financial-analysis`. It becomes
`src/kg_schema/` there, replacing the current git-dependency import. DB-touching
functions now take a `portfolio_common.db.Database` instead of a raw
`sqlite3.Connection`; intra-package imports are relative (`from . import ...`) so
the package works unmodified whether it's imported as top-level `kg_schema` (here)
or nested however the target repo ends up structuring `src/`.

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
