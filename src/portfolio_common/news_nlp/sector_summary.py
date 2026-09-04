"""The ``sector_summary`` stage: fetch the week's c_summary'd articles, compose
a deterministic (non-generative) roll-up plus a structured ``facts_json``
payload, and persist one row per (GICS sub-industry, closed calendar week).

The only text ever handed to a model here is ``build_sector_intro_seed``'s one
aggregate-stats sentence -- no ticker, company name, or c_summary substring --
which is what makes cross-company / cross-topic blending structurally
impossible in this stage.
"""

from __future__ import annotations

import json
import re
import sqlite3

from portfolio_common.news_nlp.queries import now_iso
from portfolio_common.news_nlp.schema import SECTOR_SUMMARY_FORMAT_VERSION
from portfolio_common.news_nlp.taxonomy import CATEGORY_LABELS, OTHER_LABEL

# Monday-start ISO week containing a given date, via SQLite's 'weekday N'
# modifier (0=Sunday): shift forward to the next Sunday (a no-op if the date
# already is one), then step back 6 days to land on that week's Monday.
_WEEK_START_EXPR = "date({col}, 'weekday 0', '-6 days')"
_WEEK_END_EXPR = "date({col}, 'weekday 0')"


def fetch_pending_sector_weeks(
    conn: sqlite3.Connection, limit: int | None = None
) -> list[sqlite3.Row]:
    """Return (gics_sector, gics_sub_industry, week_start, week_end) tuples
    ready for sector_summary generation: closed weeks (week_end already in
    the past, so a partial week is never summarized and later regenerated)
    with at least one c_summary'd article, not yet in sector_summary.
    Weeks are bucketed off pub_date, falling back to fetched_at when
    pub_date is NULL.
    """
    date_col = "COALESCE(a.pub_date, a.fetched_at)"
    week_start_expr = _WEEK_START_EXPR.format(col=date_col)
    week_end_expr = _WEEK_END_EXPR.format(col=date_col)
    # S608: week_start_expr/week_end_expr come from the hardcoded
    # _WEEK_START_EXPR/_WEEK_END_EXPR templates, not caller input.
    sql = f"""
        SELECT
            a.gics_sector AS gics_sector,
            a.gics_sub_industry AS gics_sub_industry,
            {week_start_expr} AS week_start,
            {week_end_expr} AS week_end
        FROM article_summary asum
        JOIN articles a ON a.id = asum.article_id
        WHERE a.gics_sector IS NOT NULL AND a.gics_sub_industry IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM sector_summary ss
              WHERE ss.gics_sector = a.gics_sector
                AND ss.gics_sub_industry = a.gics_sub_industry
                AND ss.week_start = {week_start_expr}
                AND ss.format_version = ?
          )
        GROUP BY a.gics_sector, a.gics_sub_industry, week_start
        HAVING week_end < date('now')
        ORDER BY week_start, a.gics_sector, a.gics_sub_industry
    """  # noqa: S608
    # A row at an older format_version doesn't satisfy the NOT EXISTS check,
    # so it's treated as still-pending here -- the next sector_summary run
    # naturally regenerates and overwrites it via INSERT OR REPLACE.
    params: list = [SECTOR_SUMMARY_FORMAT_VERSION]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def fetch_company_summaries_for_sector_week(
    conn: sqlite3.Connection, gics_sector: str, gics_sub_industry: str, week_start: str
) -> list[sqlite3.Row]:
    """Return the article_summary rows (with company/ticker/category/sentiment)
    contributing to one (gics_sector, gics_sub_industry, week_start)
    sector_summary. INNER JOINs to article_category and article_sentiment:
    an article whose c_summary exists but has no article_category row (e.g.
    historical data predating the category stage becoming mandatory, or a
    direct/partial stage invocation) is excluded entirely rather than
    bucketed as "uncategorized" -- a deliberate scope decision, not an
    oversight. The article_sentiment JOIN never drops a row in practice:
    c_summary generation itself already requires a sentiment row to exist
    (see fetch_pending_company_summaries's INNER JOIN), and sentiment rows
    are never deleted afterwards.
    """
    date_col = "COALESCE(a.pub_date, a.fetched_at)"
    week_start_expr = _WEEK_START_EXPR.format(col=date_col)
    # S608: week_start_expr comes from the hardcoded _WEEK_START_EXPR
    # template, not caller input; gics_sector/sub_industry/week_start below
    # are bound as query params.
    sql = f"""
        SELECT asum.article_id, asum.summary_text, a.ticker, a.company,
               c.label AS category_label, s.label AS sentiment_label
        FROM article_summary asum
        JOIN articles a ON a.id = asum.article_id
        JOIN article_category c ON c.article_id = a.id
        JOIN article_sentiment s ON s.article_id = a.id
        WHERE a.gics_sector = ? AND a.gics_sub_industry = ?
          AND {week_start_expr} = ?
        ORDER BY c.label, a.company, asum.article_id
    """  # noqa: S608
    return conn.execute(sql, (gics_sector, gics_sub_industry, week_start)).fetchall()


def fetch_sector_week_entity_stats(
    conn: sqlite3.Connection,
    gics_sector: str,
    gics_sub_industry: str,
    week_start: str,
    top: int = 10,
) -> list[dict]:
    """Top mentioned entities for one (sector, sub_industry, week) group,
    scoped to the same c_summary'd articles fetch_company_summaries_for_sector_week
    draws from (same week-bucketing, joined through article_summary). Same
    qualifying-entity filter (score>0.8, non-numeric) used by
    fetch_pending_company_summaries."""
    date_col = "COALESCE(a.pub_date, a.fetched_at)"
    week_start_expr = _WEEK_START_EXPR.format(col=date_col)
    # S608: week_start_expr is from the hardcoded _WEEK_START_EXPR template;
    # gics_sector/sub_industry/week_start/top below are all bound as params.
    sql = f"""
        SELECT e.text, e.entity_type, COUNT(*) AS count
        FROM article_entities e
        JOIN articles a ON a.id = e.article_id
        JOIN article_summary asum ON asum.article_id = a.id
        WHERE a.gics_sector = ? AND a.gics_sub_industry = ?
          AND {week_start_expr} = ?
          AND e.score > 0.8 AND e.text NOT GLOB '[0-9]'
        GROUP BY e.text, e.entity_type
        ORDER BY count DESC
        LIMIT ?
    """  # noqa: S608
    params = (gics_sector, gics_sub_industry, week_start, top)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# Category display names/ordering for compose_sector_summary and
# build_sector_intro_seed, sourced from the canonical taxonomy (not a second
# hardcoded copy of it) -- taxonomy order, with 'other' forced last since
# it's not itself an NLI candidate label (see taxonomy.py).
_CATEGORY_DISPLAY_NAMES = {slug: display for slug, display, _ in CATEGORY_LABELS} | {
    OTHER_LABEL: "Other"
}
_CATEGORY_ORDER = [slug for slug, _, _ in CATEGORY_LABELS] + [OTHER_LABEL]


def _group_rows_by_category(rows: list[sqlite3.Row]) -> list[tuple[str, list[sqlite3.Row]]]:
    """Group rows by category_label in taxonomy order. Categories with no
    contributing rows are omitted rather than emitted as empty sections."""
    by_label: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by_label.setdefault(r["category_label"], []).append(r)
    return [(slug, by_label[slug]) for slug in _CATEGORY_ORDER if slug in by_label]


def _sentiment_counts(rows: list[sqlite3.Row]) -> dict[str, int]:
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for r in rows:
        counts[r["sentiment_label"]] = counts.get(r["sentiment_label"], 0) + 1
    return counts


def _sentiment_pct(counts: dict[str, int], total: int) -> dict[str, int]:
    if total == 0:
        return dict.fromkeys(counts, 0)
    return {label: round(100 * n / total) for label, n in counts.items()}


def compose_sector_summary(
    gics_sector: str,
    gics_sub_industry: str,
    week_start: str,
    week_end: str,
    intro_text: str,
    rows: list[sqlite3.Row],
    entity_stats: list[dict],
) -> str:
    """Deterministic, non-generative composition of the sector_summary body:
    a header, the model-generated `intro_text` (built purely from aggregate
    stats -- see build_sector_intro_seed, the only text ever handed to a
    model in this pipeline stage), an overview stats block, then one section
    per NLP category present among `rows` (taxonomy order), each listing its
    contributing companies' c_summary text verbatim, attributed to its own
    ticker. No company's text is ever blended with another's, and no text
    ever crosses a category-section boundary -- this is what makes
    cross-company/cross-topic blending structurally impossible here (the
    original "frankenstein" bug's root cause), not a property of model
    behavior."""
    total_articles = len(rows)
    num_companies = len({r["company"] for r in rows})
    sentiment_pct = _sentiment_pct(_sentiment_counts(rows), total_articles)
    entities_line = (
        ", ".join(f"{e['text']} ({e['count']})" for e in entity_stats) if entity_stats else "none"
    )

    lines = [
        f"SECTOR: {gics_sector} / {gics_sub_industry}",
        f"WEEK: {week_start} to {week_end}",
        "",
        intro_text,
        "",
        f"OVERVIEW: {total_articles} article(s) across {num_companies} "
        f"compan{'y' if num_companies == 1 else 'ies'} -- "
        f"{sentiment_pct['positive']}% positive, {sentiment_pct['negative']}% negative, "
        f"{sentiment_pct['neutral']}% neutral sentiment.",
        f"TOP ENTITIES: {entities_line}",
    ]

    for slug, category_rows in _group_rows_by_category(rows):
        lines.append("")
        lines.append(f"{_CATEGORY_DISPLAY_NAMES[slug].upper()} ({len(category_rows)} article(s)):")
        lines.extend(
            f"- {r['ticker']} ({r['company']}): {r['summary_text']}" for r in category_rows
        )

    return "\n".join(lines)


def clean_generated_text(text: str) -> str:
    """Whitespace-normalize a model-generated snippet and drop a trailing
    sentence fragment left when generation got cut off at max_length (a
    partial clause with no closing '.', '!', or '?'). Applied to
    build_sector_intro_seed's model output before it's stored as its own
    `intro_text` column -- cosmetic issues that were easy to miss when that
    sentence only ever appeared inline as one line inside the larger
    composed `summary_text` body are surfaced directly now that the sentence
    is also surfaced standalone."""
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized or normalized[-1] in ".!?":
        return normalized
    cut = max(normalized.rfind(ch) for ch in ".!?")
    return normalized[: cut + 1] if cut != -1 else normalized


def build_sector_facts(
    gics_sector: str,
    gics_sub_industry: str,
    week_start: str,
    week_end: str,
    rows: list[sqlite3.Row],
    entity_stats: list[dict],
) -> dict:
    """Structured, non-narrative counterpart to compose_sector_summary's
    prose: the same aggregate stats (sentiment/category/entity breakdowns)
    plus one attributed record per contributing row, each tagged with its
    own ticker/company -- meant for programmatic consumers (e.g.
    knowledge-graph ingestion) that want grounded facts without parsing
    prose or an intro sentence. Same no-cross-company-blending guarantee as
    compose_sector_summary: every `companies` entry's `summary` is one row's
    own c_summary text, never merged with another row's."""
    total_articles = len(rows)
    num_companies = len({r["company"] for r in rows})
    sentiment_counts = _sentiment_counts(rows)
    sentiment_pct = _sentiment_pct(sentiment_counts, total_articles)

    categories = [
        {
            "label": slug,
            "display_name": _CATEGORY_DISPLAY_NAMES[slug],
            "num_articles": len(category_rows),
            "tickers": sorted({r["ticker"] for r in category_rows}),
        }
        for slug, category_rows in _group_rows_by_category(rows)
    ]

    companies = [
        {
            "article_id": r["article_id"],
            "ticker": r["ticker"],
            "company": r["company"],
            "category": r["category_label"],
            "sentiment": r["sentiment_label"],
            "summary": r["summary_text"],
        }
        for r in rows
    ]

    return {
        "gics_sector": gics_sector,
        "gics_sub_industry": gics_sub_industry,
        "week_start": week_start,
        "week_end": week_end,
        "num_articles": total_articles,
        "num_companies": num_companies,
        "sentiment": {"counts": sentiment_counts, "pct": sentiment_pct},
        "categories": categories,
        "top_entities": entity_stats,
        "companies": companies,
    }


def build_sector_intro_seed(
    gics_sector: str,
    gics_sub_industry: str,
    week_start: str,
    week_end: str,
    rows: list[sqlite3.Row],
) -> str:
    """The *only* text ever handed to the summarization model for the
    sector-level intro sentence: one small templated sentence built purely
    from aggregate numbers derived from `rows`. Deliberately contains no
    ticker, company name, or c_summary substring -- entity mentions are
    deliberately left out too, since NER-extracted entities are frequently
    the company names themselves, which would silently reintroduce the same
    risk this function exists to eliminate. That's what makes cross-company
    blending structurally impossible here, not model behavior (see the
    now-removed build_sector_summary_input, the original source of the
    "frankenstein" bug)."""
    total_articles = len(rows)
    num_companies = len({r["company"] for r in rows})
    sentiment_pct = _sentiment_pct(_sentiment_counts(rows), total_articles)

    category_counts = {
        slug: len(category_rows) for slug, category_rows in _group_rows_by_category(rows)
    }
    top_slugs = sorted(category_counts, key=category_counts.__getitem__, reverse=True)[:2]
    topics = (
        " and ".join(_CATEGORY_DISPLAY_NAMES[slug].lower() for slug in top_slugs) or "general news"
    )

    return (
        f"This week, the {gics_sub_industry} sub-industry within {gics_sector} saw "
        f"{total_articles} article(s) across {num_companies} "
        f"compan{'y' if num_companies == 1 else 'ies'}, primarily about {topics}. "
        f"Sentiment was {sentiment_pct['positive']}% positive, {sentiment_pct['negative']}% "
        f"negative, and {sentiment_pct['neutral']}% neutral."
    )


def write_sector_summary(
    conn: sqlite3.Connection,
    gics_sector: str,
    gics_sub_industry: str,
    week_start: str,
    week_end: str,
    summary_text: str,
    num_articles: int,
    num_companies: int,
    model_name: str,
    facts: dict | None = None,
    intro_text: str = "",
    format_version: int = SECTOR_SUMMARY_FORMAT_VERSION,
) -> None:
    """`facts`/`intro_text` default to an empty dict/string -- matching the
    facts_json/intro_text columns' own schema defaults -- so callers that
    only care about the prose `summary_text` (e.g. older tests) don't need
    to pass them. See build_sector_facts and clean_generated_text."""
    conn.execute(
        """INSERT OR REPLACE INTO sector_summary
           (gics_sector, gics_sub_industry, week_start, week_end, summary_text,
            num_articles, num_companies, model_name, facts_json, intro_text,
            format_version, processed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            gics_sector,
            gics_sub_industry,
            week_start,
            week_end,
            summary_text,
            num_articles,
            num_companies,
            model_name,
            json.dumps(facts if facts is not None else {}),
            intro_text,
            format_version,
            now_iso(),
        ),
    )


def list_sector_summaries(
    conn: sqlite3.Connection,
    sector: str | None = None,
    sub_industry: str | None = None,
    week_start: str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM sector_summary WHERE 1=1"
    params: list = []
    if sector:
        sql += " AND gics_sector = ?"
        params.append(sector)
    if sub_industry:
        sql += " AND gics_sub_industry = ?"
        params.append(sub_industry)
    if week_start:
        sql += " AND week_start = ?"
        params.append(week_start)
    sql += " ORDER BY week_start DESC, gics_sector, gics_sub_industry"
    results = [dict(r) for r in conn.execute(sql, params).fetchall()]
    # facts_json is stored as a TEXT column (see write_sector_summary's
    # json.dumps) -- decode it back to a real object here so API consumers
    # get a nested JSON value, not a JSON string they'd have to parse a
    # second time themselves.
    for r in results:
        r["facts_json"] = json.loads(r["facts_json"])
    return results
