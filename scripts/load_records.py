"""Copy data/records/ into the scholarships table.

Usage:
    python scripts/load_records.py            # upsert all records
    python scripts/load_records.py --reset    # drop and recreate the table first

The table is created automatically if it does not exist yet.

Every record is validated first. If any record fails, nothing is loaded.
Otherwise, in one transaction: insert new records, update changed ones, and
delete rows whose file no longer exists. Running it twice changes nothing.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from psycopg.types.json import Jsonb

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import validate  # noqa: E402  (scripts/ is on sys.path when run as a script)
from app.db import get_connection  # noqa: E402

RECORDS_DIR = REPO_ROOT / "data" / "records"
SCHEMA_SQL = REPO_ROOT / "db" / "schema.sql"

# Only change a row when its record changed, so a second run updates nothing
# and loaded_at keeps the time of the last real change.
UPSERT_SQL = """
INSERT INTO scholarships (
    slug, title, provider, levels, host_countries, nationalities, funding_type,
    opening_date, deadline_date, stored_status, last_verified, confidence,
    search_text, data
) VALUES (
    %(slug)s, %(title)s, %(provider)s, %(levels)s, %(host_countries)s, %(nationalities)s,
    %(funding_type)s, %(opening_date)s, %(deadline_date)s, %(stored_status)s,
    %(last_verified)s, %(confidence)s, to_tsvector('simple', %(search_text)s), %(data)s
)
ON CONFLICT (slug) DO UPDATE SET
    title = EXCLUDED.title,
    provider = EXCLUDED.provider,
    levels = EXCLUDED.levels,
    host_countries = EXCLUDED.host_countries,
    nationalities = EXCLUDED.nationalities,
    funding_type = EXCLUDED.funding_type,
    opening_date = EXCLUDED.opening_date,
    deadline_date = EXCLUDED.deadline_date,
    stored_status = EXCLUDED.stored_status,
    last_verified = EXCLUDED.last_verified,
    confidence = EXCLUDED.confidence,
    search_text = EXCLUDED.search_text,
    data = EXCLUDED.data,
    loaded_at = now()
WHERE scholarships.data IS DISTINCT FROM EXCLUDED.data
RETURNING (xmax = 0) AS inserted
"""


class InvalidRecordsError(Exception):
    """Raised when at least one record fails validation; nothing is loaded."""


def read_valid_records(records_dir: Path) -> dict[str, dict]:
    """Validate every file and return {slug: record}. Raise if any file fails."""
    validator = validate.load_validator()
    records: dict[str, dict] = {}
    problems: list[str] = []

    for path in sorted(records_dir.glob("*.json")):
        record, errors, _warnings = validate.check_file(path, validator)
        for message in errors:
            problems.append(f"{path.name}: {message}")
        if record is not None and not errors:
            records[path.stem] = record

    if problems:
        raise InvalidRecordsError("\n".join(problems))
    return records


def to_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def to_row(slug: str, record: dict) -> dict:
    """Pick the columns the website filters and sorts on; keep the rest in data."""
    timeline = record["application_timeline"]
    search_parts = [record["scholarship_title"], record["provider_organization"]]
    search_parts += record["degree_fields"]
    search_parts += record["host_countries"]
    return {
        "slug": slug,
        "title": record["scholarship_title"],
        "provider": record["provider_organization"],
        "levels": record["academic_level"],
        "host_countries": record["host_countries"],
        "nationalities": record["eligible_nationalities"],
        "funding_type": record["financial_coverage"]["funding_type"],
        "opening_date": to_date(timeline["opening_date"]),
        "deadline_date": to_date(timeline["deadline_date"]),
        "stored_status": record["status"],
        "last_verified": to_date(record["last_verified"]),
        "confidence": record["verification_status"]["confidence_score"],
        "search_text": " ".join(search_parts),
        "data": Jsonb(record),
    }


def load_records(conn, records_dir: Path = RECORDS_DIR, reset: bool = False) -> dict[str, int]:
    """Load all records in one transaction. Returns counts of what changed."""
    # Validate before touching the database, so a bad record can't even
    # trigger a reset that empties the table.
    records = read_valid_records(records_dir)
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "deleted": 0}

    with conn.transaction():
        with conn.cursor() as cur:
            # A brand-new database (e.g. the first deploy) has no table yet.
            cur.execute("SELECT to_regclass('scholarships') IS NULL")
            table_missing = cur.fetchone()[0]
            if reset or table_missing:
                cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))

            for slug, record in records.items():
                cur.execute(UPSERT_SQL, to_row(slug, record))
                result = cur.fetchone()
                if result is None:
                    counts["unchanged"] += 1
                elif result[0]:
                    counts["inserted"] += 1
                else:
                    counts["updated"] += 1

            cur.execute(
                "DELETE FROM scholarships WHERE NOT (slug = ANY(%s)) RETURNING slug",
                (list(records.keys()),),
            )
            counts["deleted"] = len(cur.fetchall())

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Load data/records/ into PostgreSQL.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the table first")
    args = parser.parse_args()

    try:
        with get_connection() as conn:
            counts = load_records(conn, reset=args.reset)
    except InvalidRecordsError as exc:
        print("Nothing loaded. Fix these records first:")
        print(exc)
        return 1

    print(
        f"Inserted {counts['inserted']}, updated {counts['updated']}, "
        f"unchanged {counts['unchanged']}, deleted {counts['deleted']}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
