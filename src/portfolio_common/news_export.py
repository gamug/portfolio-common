"""The shared read-only export contract for the news-NLP results store.

This is the one piece of the pre-1.0 ``portfolio_common.news_nlp`` package
that stayed here after the v1.0.0 DB-engine/``business_folders`` split,
because it is genuinely cross-repo rather than owned by a single domain:

* ``portfolio-nlp`` writes ``article_sentiment``/``article_category`` (and
  owns everything else about that schema -- init, corrections, taxonomy,
  ``sector_summary`` -- in its own ``src/news_nlp/``);
* ``portfolio-knowledge-graph`` only reads the join below, from
  ``etl/news_to_rdf.py``, to populate ``:NewsArticle``/``:ScoreSnapshot``.

Both already depend on :mod:`portfolio_common.db` for the connection engine,
so the one query and the read-only two-tier connect helper it needs live
here as the single source of truth, instead of a copy in each consumer
drifting out of sync with the other. See ``portfolio-nlp``'s
``docs/db-topology.md`` for the two-tier SOURCE/RESULTS contract this
connects to, and its ``docs/category-taxonomy.md`` for what ``cat_label``
values mean.

Everything else about the news_nlp domain -- schema init, the write-side
pipeline helpers, corrections, taxonomy, ``sector_summary`` composition --
stays owned solely by ``portfolio-nlp``'s ``src/news_nlp/``. This module
does not grow more than a third repo actually needs to read; add to it only
when a change genuinely serves more than one consumer, not as a place to
push arbitrary news_nlp reads.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from portfolio_common.db import Allowlist, Database

__all__ = ["connect_readonly", "fetch_processed_articles"]

# Only ever "main" (SOURCE and RESULTS resolve to the same file) or "source"
# (a read-only SOURCE DB is ATTACHed) -- the two branches of
# connect_readonly() below are the only place either literal is produced.
_ARTICLES_SCHEMA = Allowlist("main", "source")


def connect_readonly(
    source_db: str | os.PathLike[str], results_db: str | os.PathLike[str]
) -> tuple[Database, str]:
    """Open the RESULTS store and, unless SOURCE resolves to the same path,
    ATTACH the SOURCE store read-only as schema ``source``.

    Returns ``(db, articles_rel)`` -- the schema
    :func:`fetch_processed_articles` should qualify ``articles`` with
    (``"source"`` when attached, else ``"main"``). Read-only-shaped on
    purpose: unlike ``portfolio-nlp``'s own write-side ``news_nlp.db.
    connect_pipeline`` (which tracks ``articles_rel`` as connection state
    for its ``_ensure_article_row`` lean-upsert), a pure reader has nothing
    to track across calls -- the caller just threads the returned schema
    name into :func:`fetch_processed_articles`.
    """
    results_path = Path(results_db)
    source_path = Path(source_db)
    db = Database.connect(f"file:{results_path.as_posix()}", uri=True)
    if source_path.resolve() == results_path.resolve():
        return db, "main"
    db.attach(source_path, "source", read_only=True)
    return db, "source"


def fetch_processed_articles(
    db: Database, articles_rel: str, limit: int | None = None
) -> list[sqlite3.Row]:
    """Every successfully-fetched article that has both a sentiment and a
    category result, as one flat row per article: ``id, ticker, pub_date,
    fetched_at, body_text, positive, negative, sent_processed_at, cat_label,
    cat_score, cat_processed_at``.

    ``articles_rel`` is whatever :func:`connect_readonly` (or
    ``portfolio-nlp``'s own two-tier ``connect_pipeline``) returned --
    Allowlist-checked here too, so a caller can't reach this query with an
    arbitrary schema name.
    """
    schema = _ARTICLES_SCHEMA.check(articles_rel)
    # S608: `schema` is Allowlist-checked above; `limit` is bound as a
    # parameter, never interpolated.
    sql = f"""
        SELECT a.id AS id, a.ticker AS ticker, a.pub_date AS pub_date,
               a.fetched_at AS fetched_at, a.body_text AS body_text,
               s.positive AS positive, s.negative AS negative,
               s.processed_at AS sent_processed_at,
               c.label AS cat_label, c.score AS cat_score,
               c.processed_at AS cat_processed_at
        FROM {schema}.articles a
        JOIN article_sentiment s ON s.article_id = a.id
        JOIN article_category c ON c.article_id = a.id
        WHERE a.fetch_status = 'ok'
        ORDER BY a.id
    """  # noqa: S608
    params: list = []
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return db.execute(sql, params).fetchall()
