"""SQL queries as plain functions.

User input only ever reaches the database as query parameters (%(name)s).
The SQL text itself is built only from the fixed fragments in this file.
"""

from dataclasses import dataclass
from datetime import date

from psycopg.rows import dict_row

# Same rules as app/status.py, so the database can filter, count and page by
# the status a visitor sees today. tests/test_status.py checks they agree.
LIVE_STATUS_SQL = """
CASE
    WHEN deadline_date < %(today)s THEN 'closed'
    WHEN opening_date <= %(today)s AND deadline_date >= %(today)s THEN 'open'
    WHEN opening_date > %(today)s THEN 'upcoming'
    ELSE stored_status
END
"""

# A record open to everyone says "All", sometimes with a note such as
# "All non-EU citizens living abroad" or "All (based on residence: ...)".
# Those count for every nationality; the note is shown on the detail page.
NATIONALITY_SQL = """
EXISTS (
    SELECT 1 FROM unnest(nationalities) AS n
    WHERE n = %(nationality)s OR n = 'All' OR n LIKE 'All %%'
)
"""

# Titles sort case-insensitively in plain character order, so the order is
# the same on every server whatever its locale settings. slug breaks ties.
ORDER_BY = {
    "deadline": 'deadline_date ASC NULLS LAST, lower(title) COLLATE "C", slug',
    "title": 'lower(title) COLLATE "C", slug',
}


@dataclass
class Filters:
    q: str | None = None
    level: str | None = None
    country: str | None = None
    nationality: str | None = None
    status: str | None = None
    funding: str | None = None


def build_conditions(filters: Filters, today: date, skip: str | None = None) -> tuple[list[str], dict]:
    """Turn filters into WHERE conditions and their parameters.

    skip leaves one filter out. Filter counts use this, so the "Level" counts
    show what you would get by changing the level, given every other filter.
    """
    conditions: list[str] = []
    params: dict = {"today": today}

    if filters.q and skip != "q":
        conditions.append("search_text @@ plainto_tsquery('simple', %(q)s)")
        params["q"] = filters.q
    if filters.level and skip != "level":
        conditions.append("levels @> ARRAY[%(level)s]::text[]")
        params["level"] = filters.level
    if filters.country and skip != "country":
        conditions.append("host_countries @> ARRAY[%(country)s]::text[]")
        params["country"] = filters.country
    if filters.nationality and skip != "nationality":
        conditions.append(NATIONALITY_SQL)
        params["nationality"] = filters.nationality
    if filters.status and skip != "status":
        conditions.append(f"({LIVE_STATUS_SQL}) = %(status)s")
        params["status"] = filters.status
    if filters.funding and skip != "funding":
        conditions.append("funding_type = %(funding)s")
        params["funding"] = filters.funding

    return conditions, params


def where_clause(conditions: list[str]) -> str:
    if not conditions:
        return ""
    return "WHERE " + " AND ".join(conditions)


def list_scholarships(conn, filters: Filters, today: date, sort: str, limit: int, offset: int) -> tuple[list[dict], int]:
    """Return (rows for one page, total matching rows)."""
    conditions, params = build_conditions(filters, today)
    where = where_clause(conditions)
    params["limit"] = limit
    params["offset"] = offset

    page_sql = f"""
        SELECT slug, title, provider, levels, host_countries, funding_type,
               opening_date, deadline_date, stored_status,
               data -> 'financial_coverage' -> 'stipend' AS stipend,
               data -> 'application_timeline' ->> 'next_cycle_expected' AS next_cycle_expected,
               data -> 'application_timeline' ->> 'next_cycle_confidence' AS next_cycle_confidence,
               data -> 'provider_logo' AS provider_logo
        FROM scholarships
        {where}
        ORDER BY {ORDER_BY[sort]}
        LIMIT %(limit)s OFFSET %(offset)s
    """
    count_sql = f"SELECT count(*) AS total FROM scholarships {where}"

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(page_sql, params)
        rows = cur.fetchall()
        cur.execute(count_sql, params)
        total = cur.fetchone()["total"]
    return rows, total


def count_values(conn, value_sql: str, filters: Filters, today: date, skip: str) -> dict[str, int]:
    """Count rows per value of one column (value_sql), ignoring that filter."""
    conditions, params = build_conditions(filters, today, skip=skip)
    sql = f"""
        SELECT value, count(*) AS n
        FROM (SELECT {value_sql} AS value FROM scholarships {where_clause(conditions)}) AS v
        GROUP BY value
        ORDER BY value
    """
    counts: dict[str, int] = {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        for row in cur.fetchall():
            counts[row["value"]] = row["n"]
    return counts


def count_nationality(conn, nationality: str, filters: Filters, today: date) -> int:
    """How many results the nationality filter would give, with every other filter applied."""
    conditions, params = build_conditions(filters, today, skip="nationality")
    conditions.append(NATIONALITY_SQL)
    params["nationality"] = nationality
    sql = f"SELECT count(*) AS n FROM scholarships {where_clause(conditions)}"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchone()["n"]


def filter_counts(conn, filters: Filters, today: date) -> dict:
    """Counts shown next to each option in the filter sidebar."""
    return {
        "level": count_values(conn, "unnest(levels)", filters, today, skip="level"),
        "country": count_values(conn, "unnest(host_countries)", filters, today, skip="country"),
        "status": count_values(conn, LIVE_STATUS_SQL, filters, today, skip="status"),
        "funding": count_values(conn, "funding_type", filters, today, skip="funding"),
        "nationality": {"Nigeria": count_nationality(conn, "Nigeria", filters, today)},
    }


def get_scholarship(conn, slug: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT slug, opening_date, deadline_date, stored_status, data "
            "FROM scholarships WHERE slug = %(slug)s",
            {"slug": slug},
        )
        return cur.fetchone()


def sitemap_rows(conn) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT slug, last_verified FROM scholarships ORDER BY slug")
        return cur.fetchall()


def all_rows_for_status_check(conn, today: date) -> list[dict]:
    """Every row with its SQL live status. Used by tests to compare with status.py."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT slug, opening_date, deadline_date, stored_status, {LIVE_STATUS_SQL} AS live "
            "FROM scholarships ORDER BY slug",
            {"today": today},
        )
        return cur.fetchall()
