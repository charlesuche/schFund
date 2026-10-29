"""Live status: what a record's status is today, not on the day it was checked.

A record's stored status is only true as of last_verified. Pages must not say
"open" after the deadline has passed, so the status is worked out again from
the dates every time it is shown.

The same rules exist in SQL (LIVE_STATUS_SQL in queries.py) so the database
can filter and count by live status. tests/test_status.py checks they agree.
"""

from datetime import date

URGENT_DAYS = 30


def live_status(
    opening_date: date | None,
    deadline_date: date | None,
    stored_status: str,
    today: date,
) -> dict:
    """Return {"status", "days_left", "urgent"} as of today.

    today is passed in (never read here) so tests can pick any date.
    days_left is None when there is no deadline or it has passed.
    """
    if deadline_date is not None and deadline_date < today:
        status = "closed"
    elif opening_date is not None and deadline_date is not None and opening_date <= today:
        # deadline_date >= today here, because the first branch did not match.
        status = "open"
    elif opening_date is not None and opening_date > today:
        status = "upcoming"
    else:
        # The dates can't decide (e.g. no opening date), so trust the record.
        status = stored_status

    days_left = None
    if deadline_date is not None and deadline_date >= today:
        days_left = (deadline_date - today).days

    urgent = status == "open" and days_left is not None and days_left <= URGENT_DAYS

    return {"status": status, "days_left": days_left, "urgent": urgent}
