"""Two-tier SOURCE / RESULTS connection machinery for the news-NLP pipeline.

* RESULTS store -- selected by ``$DATABASE_URL`` (:func:`env.results_db_path`),
  opened read/write as schema ``main``. Holds the five result tables plus a lean
  ``articles`` subset (every column except ``body_text``). Everything the FastAPI
  query/correction endpoints read comes from here.
* SOURCE store -- selected by ``$SOURCE_DATABASE_URL`` (:func:`env.source_db_path`),
  opened read-only (``file:...?mode=ro``) and ATTACHed as schema ``source``.
  Holds ``articles`` including ``body_text``, written by the upstream crawler.
  Required by the text-reading pipeline stages; never written. Not needed for
  serving or the ``sector_summary`` stage.

``connect()`` opens a plain single-file connection (serving, tests, single-file
runs). ``connect_pipeline()`` opens the RESULTS store and, unless SOURCE resolves
to the same path, ATTACHes SOURCE read-only. The three ``body_text`` readers
qualify ``articles`` with ``conn.articles_rel`` (``"source"`` when attached, else
``"main"``); the pipeline's write helpers upsert a lean ``main.articles`` row so
the RESULTS store stays foreign-key-consistent.

See ``portfolio-common/docs/news-nlp-db-topology.md``.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import cast

from portfolio_common import db as _common_db
from portfolio_common.news_nlp import env

_NO_SOURCE_MSG = (
    "SOURCE_DATABASE_URL is not set. The text-reading pipeline stages "
    "(sentiment, NER, category, c_summary) require a read-only source database "
    "that has articles.body_text (e.g. urls.db). Set SOURCE_DATABASE_URL. "
    "Serving/query endpoints and the sector_summary stage do not need it. "
    "See portfolio-common/docs/news-nlp-db-topology.md."
)
_NO_SOURCE_TEXT_MSG = (
    "SOURCE database has no usable article text: articles.body_text is missing "
    "or entirely empty. Point SOURCE_DATABASE_URL at the crawl database "
    "(e.g. urls.db), not the results store. "
    "See portfolio-common/docs/news-nlp-db-topology.md."
)


class _Connection(sqlite3.Connection):
    """sqlite3.Connection that remembers which schema the `body_text` readers
    should qualify `articles` with -- ``"source"`` once a read-only SOURCE DB is
    ATTACHed by attach_source(), else ``"main"`` (single-file / serving). Base
    sqlite3.Connection rejects instance attributes, hence the subclass."""

    articles_rel: str = "main"
    # `articles` columns to copy SOURCE -> RESULTS (see attach_source); None
    # until a SOURCE DB is attached.
    lean_article_cols: list[str] | None = None


def _articles_rel(conn: sqlite3.Connection) -> str:
    """The schema the `body_text` readers qualify `articles` with: ``"source"``
    when a read-only SOURCE DB is attached, else ``"main"``. Only ever
    ``"main"`` / ``"source"`` -- safe to interpolate into SQL."""
    return getattr(conn, "articles_rel", "main")


def connect(db_path: str | os.PathLike[str] | None = None) -> _Connection:
    """Open one plain SQLite file read/write (serving, tests, single-file runs).
    ``db_path`` defaults to :func:`env.results_db_path`. For a pipeline run that
    needs the SOURCE DB attached, use connect_pipeline().

    Delegates to :func:`portfolio_common.db.connect` (row factory, busy_timeout,
    ``PRAGMA foreign_keys = ON``); ``uri=True`` so an ``ATTACH ...?mode=ro`` on
    this connection is honored, ``factory=_Connection`` for the ``articles_rel``
    state.
    """
    path = Path(db_path) if db_path is not None else env.results_db_path()
    conn = _common_db.connect(
        f"file:{path.as_posix()}",
        uri=True,
        foreign_keys=True,
        factory=_Connection,
    )
    return cast("_Connection", conn)


def connect_pipeline(
    results_db: str | os.PathLike[str] | None = None,
    source_db: str | os.PathLike[str] | None = None,
) -> _Connection:
    """Open the RESULTS store read/write and, unless SOURCE resolves to the same
    path, ATTACH the SOURCE store read-only as schema `source`.

    Paths are read from the environment in the body (not bound as defaults) so
    tests that set ``$DATABASE_URL`` / ``$SOURCE_DATABASE_URL`` -- or pass
    explicit overrides -- take effect. Raises RuntimeError if no SOURCE is
    configured -- the text-reading stages cannot run without one.
    """
    results = env.results_db_path(results_db)
    source = env.source_db_path(source_db)
    if source is None:
        raise RuntimeError(_NO_SOURCE_MSG)
    conn = connect(results)
    if source.resolve() != results.resolve():
        attach_source(conn, source)
    return conn


def _compute_lean_article_columns(conn: sqlite3.Connection) -> list[str]:
    """`articles` columns present in both the attached SOURCE and RESULTS
    schemas, minus `body_text`, in SOURCE column order."""
    source_cols = [row[1] for row in conn.execute("PRAGMA source.table_info(articles)")]
    main_cols = {row[1] for row in conn.execute("PRAGMA main.table_info(articles)")}
    return [c for c in source_cols if c != "body_text" and c in main_cols]


def attach_source(conn: _Connection, source: str | os.PathLike[str]) -> None:
    """ATTACH `source` read-only as schema `source`; flip `articles_rel` and
    cache the lean column list for _ensure_article_row."""
    conn.execute("ATTACH DATABASE ? AS source", (f"file:{Path(source).as_posix()}?mode=ro",))
    conn.articles_rel = "source"
    conn.lean_article_cols = _compute_lean_article_columns(conn)


def detach_source(conn: _Connection) -> None:
    """Undo attach_source(). Safe to call when nothing is attached."""
    if conn.articles_rel == "source":
        conn.execute("DETACH DATABASE source")
        conn.articles_rel = "main"
        conn.lean_article_cols = None


def _ensure_article_row(conn: sqlite3.Connection, article_id: int) -> None:
    """Copy the lean `articles` row (no `body_text`) for `article_id` from
    SOURCE into RESULTS if it isn't there yet, so a result-table write for it
    satisfies the `REFERENCES articles(id)` foreign key. No-op unless a SOURCE
    DB is attached (single-file runs already have the full `articles` table)."""
    if _articles_rel(conn) != "source":
        return
    lean_cols = getattr(conn, "lean_article_cols", None) or _compute_lean_article_columns(conn)
    cols = ", ".join(lean_cols)
    conn.execute(
        f"INSERT OR IGNORE INTO main.articles ({cols}) "  # noqa: S608
        f"SELECT {cols} FROM source.articles WHERE id = ?",
        (article_id,),
    )


def require_source_text(conn: sqlite3.Connection) -> None:
    """Fail fast (before any model loads) if the `articles` table the
    `body_text` readers will hit has no usable text -- the common
    misconfiguration of pointing a text stage at the results store. Structural
    check ("does this DB hold article text at all"), not "is anything pending":
    a fully caught-up pipeline still passes."""
    schema = _articles_rel(conn)
    cols = {row[1] for row in conn.execute(f"PRAGMA {schema}.table_info(articles)")}
    if "body_text" not in cols:
        raise RuntimeError(_NO_SOURCE_TEXT_MSG)
    row = conn.execute(
        f"SELECT 1 FROM {schema}.articles "  # noqa: S608
        "WHERE body_text IS NOT NULL AND TRIM(body_text) != '' LIMIT 1"
    ).fetchone()
    if row is None:
        raise RuntimeError(_NO_SOURCE_TEXT_MSG)
