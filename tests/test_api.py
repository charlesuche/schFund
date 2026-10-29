"""Tests for the JSON API in app/main.py, against the test database.

"Today" is fixed so live status is predictable. Expected results are worked
out from the record files themselves, so the tests keep working as records
are added. On 2026-10-28 DSU Toscana PhD is open with 19 days left.
"""

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_db_url, get_today
from app.status import live_status

REPO_ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 10, 28)


def all_records() -> dict[str, dict]:
    records = {}
    for path in sorted((REPO_ROOT / "data" / "records").glob("*.json")):
        records[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return records


@pytest.fixture(scope="module")
def client(loaded_db):
    app.dependency_overrides[get_db_url] = lambda: loaded_db
    app.dependency_overrides[get_today] = lambda: TODAY
    yield TestClient(app)
    app.dependency_overrides.clear()


def live(record: dict) -> str:
    """Live status of a record file on TODAY, using the same rules as the app."""
    timeline = record["application_timeline"]
    opening = timeline["opening_date"]
    deadline = timeline["deadline_date"]
    result = live_status(
        date.fromisoformat(opening) if opening else None,
        date.fromisoformat(deadline) if deadline else None,
        record["status"],
        TODAY,
    )
    return result["status"]


def with_status(status: str) -> list[str]:
    result = []
    for slug, record in all_records().items():
        if live(record) == status:
            result.append(slug)
    return sorted(result)


def in_country(country: str) -> list[str]:
    result = []
    for slug, record in all_records().items():
        if country in record["host_countries"]:
            result.append(slug)
    return sorted(result)


def slugs(response) -> list[str]:
    assert response.status_code == 200, response.text
    result = []
    for item in response.json()["items"]:
        result.append(item["slug"])
    return result


def get_all(client, **params) -> list[str]:
    params["limit"] = 100
    return slugs(client.get("/api/scholarships", params=params))


# --- listing and filters ---------------------------------------------------

def test_list_returns_every_record(client):
    response = client.get("/api/scholarships", params={"limit": 100})
    body = response.json()
    assert body["total"] == len(all_records())
    assert sorted(slugs(response)) == sorted(all_records())


def test_list_item_shape(client):
    item = client.get("/api/scholarships", params={"q": "Banach"}).json()["items"][0]
    assert item == {
        "slug": "nawa-banach-2026",
        "title": all_records()["nawa-banach-2026"]["scholarship_title"],
        "provider": all_records()["nawa-banach-2026"]["provider_organization"],
        "levels": ["Master"],
        "countries": ["Poland"],
        "funding_type": "Fully Funded",
        "status": "closed",
        "deadline_date": "2026-05-08",
        "days_left": None,
        "urgent": False,
        "money": "PLN 2,500 / month",
        "provider_logo": None,
    }


def test_level_filter(client):
    expected = []
    for slug, record in all_records().items():
        if "PhD" in record["academic_level"]:
            expected.append(slug)
    assert sorted(get_all(client, level="PhD")) == sorted(expected)


def test_country_filter(client):
    assert get_all(client, country="Poland") == ["nawa-banach-2026"]
    assert sorted(get_all(client, country="Sweden")) == in_country("Sweden")
    assert "si-global-professionals-2027" in in_country("Sweden")


def test_nigeria_filter(client):
    found = get_all(client, nationality="Nigeria")
    # Listed by name.
    assert "nawa-banach-2026" in found
    assert "si-global-professionals-2027" in found
    # Open to all nationalities, with or without a note.
    assert "dsu-toscana-bsc-msc-2026" in found
    assert "unical-admission-2026" in found  # "All non-EU citizens living abroad"
    # Lists other countries but not Nigeria: not a match.
    assert "fao-hungary-2026" in found  # lists Nigeria by name
    assert "maastricht-nl-high-potential-2027" in found  # "All non-EU/EEA ..."

    expected = []
    for slug, record in all_records().items():
        nationalities = record["eligible_nationalities"]
        if "Nigeria" in nationalities or any(n == "All" or n.startswith("All ") for n in nationalities):
            expected.append(slug)
    assert sorted(found) == sorted(expected)


def test_nationality_filter_excludes_records_that_list_other_countries(client):
    found = get_all(client, nationality="Ghana")
    assert "nawa-banach-2026" not in found
    assert "si-global-professionals-2027" not in found


def test_status_filter_uses_live_status(client):
    for status in ["open", "closed", "upcoming", "unknown"]:
        assert sorted(get_all(client, status=status)) == with_status(status), status
    assert "dsu-toscana-phd-2026" in with_status("open")
    assert "kth-scholarship-2027" in with_status("upcoming")


def test_funding_filter(client):
    expected = []
    for slug, record in all_records().items():
        if record["financial_coverage"]["funding_type"] == "Partially Funded":
            expected.append(slug)
    assert sorted(get_all(client, funding="Partially Funded")) == sorted(expected)


def test_search(client):
    assert sorted(get_all(client, q="Swedish Institute")) == [
        "si-global-professionals-2027",
        "si-pioneering-women-stem-2027",
    ]


def test_filters_combine(client):
    found = get_all(client, nationality="Nigeria", level="Master", country="Italy")
    for slug in found:
        record = all_records()[slug]
        assert "Master" in record["academic_level"]
        assert "Italy" in record["host_countries"]
    assert "nawa-banach-2026" not in found


def test_filter_with_no_matches(client):
    body = client.get("/api/scholarships", params={"country": "Atlantis"}).json()
    assert body["items"] == []
    assert body["total"] == 0


# --- sorting and paging ----------------------------------------------------

def test_default_sort_is_deadline_with_missing_deadlines_last(client):
    items = client.get("/api/scholarships", params={"limit": 100}).json()["items"]
    deadlines = []
    for item in items:
        deadlines.append(item["deadline_date"])
    with_dates = [d for d in deadlines if d is not None]
    assert with_dates == sorted(with_dates)
    assert deadlines[: len(with_dates)] == with_dates


def test_sort_by_title(client):
    items = client.get("/api/scholarships", params={"sort": "title", "limit": 100}).json()["items"]
    titles = []
    for item in items:
        titles.append(item["title"])
    assert titles == sorted(titles, key=str.lower)


def test_limit_and_offset(client):
    everything = get_all(client)
    first = client.get("/api/scholarships", params={"limit": 5, "offset": 0}).json()
    second = client.get("/api/scholarships", params={"limit": 5, "offset": 5}).json()
    assert first["total"] == len(everything)
    assert slugs_of(first) + slugs_of(second) == everything[:10]


def slugs_of(body: dict) -> list[str]:
    result = []
    for item in body["items"]:
        result.append(item["slug"])
    return result


# --- filter counts ---------------------------------------------------------

def test_filter_counts(client):
    counts = client.get("/api/scholarships").json()["filter_counts"]
    total = len(all_records())
    assert sum(counts["status"].values()) == total
    assert sum(counts["funding"].values()) == total
    assert counts["status"]["open"] == len(with_status("open"))
    assert counts["status"]["upcoming"] == len(with_status("upcoming"))
    assert counts["country"]["Sweden"] == len(in_country("Sweden"))
    assert counts["nationality"]["Nigeria"] == len(get_all(client, nationality="Nigeria"))


def test_filter_counts_ignore_their_own_filter(client):
    # With level=PhD selected, the level counts still show the other levels,
    # but other counts only cover PhD records.
    counts = client.get("/api/scholarships", params={"level": "PhD"}).json()["filter_counts"]
    assert counts["level"]["Master"] > 0
    assert sum(counts["status"].values()) == len(get_all(client, level="PhD"))


# --- invalid input ---------------------------------------------------------

@pytest.mark.parametrize(
    "params",
    [
        {"level": "Diploma"},
        {"status": "maybe"},
        {"funding": "Free"},
        {"sort": "random"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ],
)
def test_invalid_filter_values_give_422(client, params):
    assert client.get("/api/scholarships", params=params).status_code == 422


def test_sql_injection_attempt_is_just_text(client):
    response = client.get("/api/scholarships", params={"country": "Italy'; DROP TABLE scholarships; --"})
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert client.get("/api/scholarships").json()["total"] == len(all_records())


# --- detail ----------------------------------------------------------------

def test_detail_returns_full_record_and_live_status(client):
    body = client.get("/api/scholarships/dsu-toscana-phd-2026").json()
    assert body["record"] == all_records()["dsu-toscana-phd-2026"]
    assert body["status"] == "open"
    assert body["days_left"] == 19
    assert body["urgent"] is True


def test_unknown_slug_gives_404(client):
    response = client.get("/api/scholarships/no-such-scholarship")
    assert response.status_code == 404


def test_stored_open_shows_closed_after_deadline(client):
    # DSU Toscana PhD was stored as "open" (deadline 2026-11-16).
    app.dependency_overrides[get_today] = lambda: date(2026, 11, 20)
    try:
        detail = client.get("/api/scholarships/dsu-toscana-phd-2026").json()
        closed = get_all(client, status="closed")
        still_open = get_all(client, status="open")
    finally:
        app.dependency_overrides[get_today] = lambda: TODAY

    assert detail["stored_status"] == "open"
    assert detail["status"] == "closed"
    assert detail["days_left"] is None
    assert detail["urgent"] is False
    assert "dsu-toscana-phd-2026" in closed
    assert "dsu-toscana-phd-2026" not in still_open


# --- health ----------------------------------------------------------------

def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    # commit is set by Render on the server and is None locally.
    assert response.json() == {"database": "ok", "commit": None}


def test_health_unreachable(client):
    previous = app.dependency_overrides[get_db_url]
    app.dependency_overrides[get_db_url] = lambda: "postgresql://nobody:wrong@localhost:1/none"
    try:
        response = client.get("/api/health")
    finally:
        app.dependency_overrides[get_db_url] = previous
    assert response.status_code == 503
    assert response.json() == {"database": "unreachable"}
