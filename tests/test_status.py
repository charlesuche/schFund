"""Tests for app/status.py, and that the SQL version in queries.py agrees."""

from datetime import date, timedelta

import pytest

from app import queries
from app.db import get_connection
from app.status import live_status

TODAY = date(2026, 10, 28)


def days(n: int) -> date:
    return TODAY + timedelta(days=n)


def test_deadline_before_today_is_closed():
    result = live_status(days(-60), days(-1), "open", TODAY)
    assert result == {"status": "closed", "days_left": None, "urgent": False}


def test_stored_open_becomes_closed_after_deadline():
    # Without an opening date too: a passed deadline always means closed.
    result = live_status(None, days(-1), "open", TODAY)
    assert result["status"] == "closed"


def test_between_opening_and_deadline_is_open():
    result = live_status(days(-10), days(45), "upcoming", TODAY)
    assert result == {"status": "open", "days_left": 45, "urgent": False}


def test_deadline_exactly_today_is_open_and_urgent():
    result = live_status(days(-10), TODAY, "open", TODAY)
    assert result == {"status": "open", "days_left": 0, "urgent": True}


def test_opening_exactly_today_is_open():
    result = live_status(TODAY, days(10), "upcoming", TODAY)
    assert result["status"] == "open"


def test_30_days_left_is_urgent():
    result = live_status(days(-10), days(30), "open", TODAY)
    assert result == {"status": "open", "days_left": 30, "urgent": True}


def test_31_days_left_is_not_urgent():
    result = live_status(days(-10), days(31), "open", TODAY)
    assert result == {"status": "open", "days_left": 31, "urgent": False}


def test_opening_after_today_is_upcoming():
    result = live_status(days(5), days(40), "unknown", TODAY)
    assert result == {"status": "upcoming", "days_left": 40, "urgent": False}


def test_no_dates_keeps_stored_status():
    result = live_status(None, None, "unknown", TODAY)
    assert result == {"status": "unknown", "days_left": None, "urgent": False}


def test_future_deadline_without_opening_keeps_stored_status():
    result = live_status(None, days(10), "open", TODAY)
    assert result == {"status": "open", "days_left": 10, "urgent": True}


@pytest.mark.parametrize(
    "today",
    [date(2026, 1, 1), date(2026, 5, 26), date(2026, 10, 28), date(2026, 11, 16),
     date(2026, 11, 17), date(2027, 2, 8), date(2027, 3, 1)],
)
def test_sql_live_status_matches_python(loaded_db, today):
    with get_connection(loaded_db) as conn:
        rows = queries.all_rows_for_status_check(conn, today)
    assert rows
    for row in rows:
        expected = live_status(row["opening_date"], row["deadline_date"], row["stored_status"], today)
        assert row["live"] == expected["status"], row["slug"]
