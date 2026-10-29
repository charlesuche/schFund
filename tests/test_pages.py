"""Tests for the public HTML pages, against the test database."""

import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from app.main import app, get_db_url, get_today

REPO_ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 10, 28)


def record(slug: str) -> dict:
    path = REPO_ROOT / "data" / "records" / f"{slug}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def all_slugs() -> list[str]:
    result = []
    for path in sorted((REPO_ROOT / "data" / "records").glob("*.json")):
        result.append(path.stem)
    return result


@pytest.fixture(scope="module")
def client(loaded_db):
    app.dependency_overrides[get_db_url] = lambda: loaded_db
    app.dependency_overrides[get_today] = lambda: TODAY
    yield TestClient(app)
    app.dependency_overrides.clear()


def sweden_slugs_open_to_nigeria() -> list[str]:
    result = []
    for slug in all_slugs():
        r = record(slug)
        names = r["eligible_nationalities"]
        open_to_nigeria = "Nigeria" in names or any(n == "All" or n.startswith("All ") for n in names)
        if "Sweden" in r["host_countries"] and open_to_nigeria:
            result.append(slug)
    return result


def page_title(html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, re.S)
    return match.group(1).strip()


# --- search page -----------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/scholarships"])
def test_search_page_returns_200(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert f"{len(all_slugs())} scholarships" in response.text


def test_search_page_lists_every_record(client):
    # Results are paged, so collect the links from every page.
    html = ""
    page = 1
    while True:
        response = client.get("/scholarships", params={"page": page})
        html += response.text
        if "Next</a>" not in response.text:
            break
        page += 1
    for slug in all_slugs():
        assert f'href="/scholarships/{slug}"' in html


def test_closed_scholarship_shows_closed(client):
    html = client.get("/scholarships", params={"q": "Banach"}).text
    assert ">Closed<" in html


def test_open_scholarship_shows_days_left(client):
    html = client.get("/scholarships", params={"status": "open", "q": "Toscana"}).text
    assert "1 scholarship" in html
    assert ">Open<" in html
    assert "19 days left" in html


def test_filters_work_as_plain_get_parameters(client):
    html = client.get("/scholarships", params={"country": "Sweden", "nationality": "Nigeria"}).text
    sweden_for_nigeria = sweden_slugs_open_to_nigeria()
    assert f"{len(sweden_for_nigeria)} scholarships" in html
    assert "si-global-professionals-2027" in html
    assert "nawa-banach-2026" not in html


def test_filter_counts_come_from_the_database(client):
    html = client.get("/scholarships").text
    # The country group shows Sweden with its count from the records.
    sweden = len([s for s in all_slugs() if "Sweden" in record(s)["host_countries"]])
    assert re.search(rf'value="Sweden"[^>]*>\s*<span>Sweden</span>\s*<span class="count">{sweden}</span>', html)


def test_invalid_filter_values_are_ignored(client):
    response = client.get("/scholarships", params={"level": "Diploma", "status": "maybe"})
    assert response.status_code == 200
    assert f"{len(all_slugs())} scholarships" in response.text


def test_no_results_message(client):
    html = client.get("/scholarships", params={"country": "Atlantis"}).text
    assert "0 scholarships" in html
    assert "No scholarships match these filters." in html


def test_user_input_is_escaped(client):
    html = client.get("/scholarships", params={"q": "<script>alert(1)</script>"}).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --- detail page -----------------------------------------------------------

@pytest.mark.parametrize("slug", all_slugs())
def test_every_detail_page_returns_200_with_title_and_verified_line(client, slug):
    response = client.get(f"/scholarships/{slug}")
    assert response.status_code == 200
    html = response.text
    r = record(slug)
    assert page_title(html).startswith(str(escape(r["scholarship_title"])))
    assert '<meta name="description" content="' in html
    assert "Verified on " in html
    for source in r["source_urls"]:
        assert str(escape(source["url"])) in html


def test_detail_titles_are_unique(client):
    titles = set()
    for slug in all_slugs():
        titles.add(page_title(client.get(f"/scholarships/{slug}").text))
    assert len(titles) == len(all_slugs())


def test_detail_shows_source_titles_and_verified_date(client):
    html = client.get("/scholarships/nawa-banach-2026").text
    assert "NAWA: Banach 2026 call for applications (PDF)" in html
    assert "Verified on 28 Oct 2026" in html


def test_closed_detail_shows_closed(client):
    html = client.get("/scholarships/nawa-banach-2026").text
    assert ">Closed<" in html


def test_scored_section_shown_only_when_record_has_criteria(client):
    banach = client.get("/scholarships/nawa-banach-2026").text
    assert "How you're scored" in banach or "How you&#39;re scored" in banach
    assert "At least 70 of 110 points" in banach

    siena = client.get("/scholarships/unisi-excellence-2026").text
    assert record("unisi-excellence-2026")["selection_criteria"]["criteria"] == []
    assert "scored" not in siena


def test_documents_section_hidden_when_record_has_none(client):
    assert record("unisi-excellence-2026")["required_documents"] == []
    assert "Documents you'll need" not in client.get("/scholarships/unisi-excellence-2026").text
    assert "Documents you'll need" in client.get("/scholarships/nawa-banach-2026").text


def test_optional_document_is_marked(client):
    html = client.get("/scholarships/nawa-banach-2026").text
    assert "Recommendation letter from a Polish diplomatic mission" in html
    assert ">Optional<" in html


def test_stored_open_detail_shows_closed_after_deadline(client):
    app.dependency_overrides[get_today] = lambda: date(2026, 11, 20)
    try:
        html = client.get("/scholarships/dsu-toscana-phd-2026").text
    finally:
        app.dependency_overrides[get_today] = lambda: TODAY
    assert ">Closed<" in html
    assert ">Open<" not in html


# --- 404 -------------------------------------------------------------------

def test_unknown_slug_returns_friendly_404(client):
    response = client.get("/scholarships/no-such-scholarship")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "Browse all scholarships" in response.text


def test_unknown_page_returns_friendly_404(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "Browse all scholarships" in response.text


def test_api_404_stays_json(client):
    response = client.get("/api/scholarships/no-such-scholarship")
    assert response.status_code == 404
    assert response.json() == {"detail": "Scholarship not found"}


def test_stylesheet_is_served_with_tokens(client):
    response = client.get("/static/styles.css")
    assert response.status_code == 200
    assert "--primary: #0B6B45" in response.text
    assert "@media (max-width: 767px)" in response.text


def test_sort_links_keep_filters_and_work_without_javascript(client):
    html = client.get("/scholarships", params={"country": "Italy", "sort": "title"}).text
    assert 'href="/scholarships?country=Italy&amp;sort=deadline"' in html
    assert 'href="/scholarships?country=Italy&amp;sort=title" aria-current="true"' in html
