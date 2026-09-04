# news_nlp (staging)

This is a **staging area**, not a place this package lives permanently. It
holds the `news_nlp` domain -- extracted out of `portfolio-common`'s
`src/portfolio_common/news_nlp/` -- pending physical relocation into
`portfolio-nlp`, the repo that owns it, as its own `src/news_nlp/`.

Once dropped in, `news_nlp` is imported directly (`import news_nlp`, already
how the code under `news_nlp/` and its tests import it here) rather than as
`portfolio_common.news_nlp`. That means `portfolio-nlp`'s own `src/pipeline.py`
and `apps/news_nlp_api.py` -- its confirmed current consumers of this
package -- need their `from portfolio_common.news_nlp import ...` /
`from portfolio_common import news_nlp` imports updated to the plain
`news_nlp` form once this folder lands there. It keeps depending on
`portfolio_common.db` (`Database`, `Allowlist`, `in_clause`) as an ordinary
package dependency -- that part doesn't change.

`portfolio-knowledge-graph`'s `src/etl/news_to_rdf.py` also imports
`connect_pipeline` / `fetch_processed_articles` from this package (see
`docs/db-topology.md`'s "External consumers" section) -- a secondary
consumer, not `portfolio-nlp` itself. It will need its own dependency
decision once `news_nlp` moves (e.g. depend on `portfolio-nlp` for it, or a
published `news_nlp` package) -- that decision is a follow-up, not solved by
this extraction.

## Layout

- `news_nlp/` -- the importable package.
- `tests/` -- its test suite (`import news_nlp`, not `portfolio_common.news_nlp`).
- `docs/db-topology.md` -- the two-tier SOURCE/RESULTS database contract.

## Running the tests

From this directory, using the `portfolio-common` venv:

```
uv run --project ../.. python -m pytest tests -q
```

with `PYTHONPATH=.:../../src` set (or equivalent), so `import news_nlp`
resolves to `news_nlp/` here and `import portfolio_common` resolves to
`../../src/portfolio_common`.
