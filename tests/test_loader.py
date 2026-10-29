"""Tests for scripts/load_records.py. They need a separate test database.

They use the test_db_url fixture from conftest.py (TEST_DATABASE_URL). The
tests drop and recreate the scholarships table there.
"""

import json
import shutil
from pathlib import Path

import pytest

import load_records
from app.db import get_connection

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_RECORDS = REPO_ROOT / "data" / "records"


def record_count() -> int:
    return len(list(REAL_RECORDS.glob("*.json")))


@pytest.fixture
def conn(test_db_url):
    connection = get_connection(test_db_url)
    # Start every test from an empty table.
    with connection.cursor() as cur:
        cur.execute(load_records.SCHEMA_SQL.read_text(encoding="utf-8"))
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def records_dir(tmp_path: Path) -> Path:
    """A private copy of data/records/ that a test can change freely."""
    folder = tmp_path / "records"
    shutil.copytree(REAL_RECORDS, folder)
    return folder


def slugs_in_table(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT slug FROM scholarships")
        rows = cur.fetchall()
    slugs = set()
    for row in rows:
        slugs.add(row[0])
    return slugs


def test_all_records_load(conn, records_dir):
    counts = load_records.load_records(conn, records_dir)

    assert counts == {"inserted": record_count(), "updated": 0, "unchanged": 0, "deleted": 0}
    expected = set()
    for path in records_dir.glob("*.json"):
        expected.add(path.stem)
    assert slugs_in_table(conn) == expected


def test_columns_match_the_record(conn, records_dir):
    load_records.load_records(conn, records_dir)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT title, levels, deadline_date::text, confidence::float, data "
            "FROM scholarships WHERE slug = 'nawa-banach-2026'"
        )
        title, levels, deadline, confidence, data = cur.fetchone()
    record = json.loads((records_dir / "nawa-banach-2026.json").read_text(encoding="utf-8"))
    assert title == record["scholarship_title"]
    assert levels == record["academic_level"]
    assert deadline == record["application_timeline"]["deadline_date"]
    assert confidence == record["verification_status"]["confidence_score"]
    assert data == record


def test_search_text_finds_by_country(conn, records_dir):
    load_records.load_records(conn, records_dir)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT slug FROM scholarships "
            "WHERE search_text @@ plainto_tsquery('simple', 'Poland')"
        )
        rows = cur.fetchall()
    assert ("nawa-banach-2026",) in rows


def test_second_run_changes_nothing(conn, records_dir):
    load_records.load_records(conn, records_dir)
    with conn.cursor() as cur:
        cur.execute("SELECT slug, loaded_at FROM scholarships ORDER BY slug")
        before = cur.fetchall()

    counts = load_records.load_records(conn, records_dir)

    assert counts == {"inserted": 0, "updated": 0, "unchanged": record_count(), "deleted": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT slug, loaded_at FROM scholarships ORDER BY slug")
        after = cur.fetchall()
    assert after == before


def test_changed_record_is_updated(conn, records_dir):
    load_records.load_records(conn, records_dir)
    path = records_dir / "unisi-excellence-2026.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["verification_status"]["confidence_score"] = 0.5
    path.write_text(json.dumps(record), encoding="utf-8")

    counts = load_records.load_records(conn, records_dir)

    assert counts["updated"] == 1
    assert counts["unchanged"] == record_count() - 1


def test_removed_file_row_is_deleted(conn, records_dir):
    load_records.load_records(conn, records_dir)
    (records_dir / "unisi-excellence-2026.json").unlink()

    counts = load_records.load_records(conn, records_dir)

    assert counts["deleted"] == 1
    assert "unisi-excellence-2026" not in slugs_in_table(conn)


def test_invalid_record_stops_the_whole_load(conn, records_dir):
    load_records.load_records(conn, records_dir)
    before = slugs_in_table(conn)

    # One broken record plus one removal: neither may reach the database.
    broken_path = records_dir / "nawa-banach-2026.json"
    broken = json.loads(broken_path.read_text(encoding="utf-8"))
    broken["status"] = "maybe"
    broken_path.write_text(json.dumps(broken), encoding="utf-8")
    (records_dir / "unisi-excellence-2026.json").unlink()

    with pytest.raises(load_records.InvalidRecordsError, match="nawa-banach-2026.json"):
        load_records.load_records(conn, records_dir)

    assert slugs_in_table(conn) == before


def test_invalid_record_does_not_reset_the_table(conn, records_dir):
    load_records.load_records(conn, records_dir)
    before = slugs_in_table(conn)
    (records_dir / "bad.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(load_records.InvalidRecordsError):
        load_records.load_records(conn, records_dir, reset=True)

    assert slugs_in_table(conn) == before


def test_first_load_into_an_empty_database_creates_the_table(conn, records_dir):
    # Like the first deploy to a new database: no table, no --reset.
    with conn.cursor() as cur:
        cur.execute("DROP TABLE scholarships")
    conn.commit()

    counts = load_records.load_records(conn, records_dir)
    assert counts["inserted"] == record_count()
