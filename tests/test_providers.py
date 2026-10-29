"""Tests for provider marks, flags and the new search-page blocks."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import providers
from app.main import app, get_db_url, get_today

TODAY = date(2026, 10, 28)


@pytest.fixture(scope="module")
def client(loaded_db):
    app.dependency_overrides[get_db_url] = lambda: loaded_db
    app.dependency_overrides[get_today] = lambda: TODAY
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_every_record_has_a_provider(loaded_db):
    from pathlib import Path
    for path in (Path(__file__).resolve().parent.parent / "data" / "records").glob("*.json"):
        assert providers.provider_for(path.stem) is not None, path.stem


def test_epos_courses_share_the_daad_mark():
    assert providers.provider_for("daad-epos-goettingen-development-economics-2027")["key"] == "daad"


def test_monogram_shown_until_a_logo_is_added(client):
    html = client.get("/scholarships/nawa-banach-2026").text
    assert "provider-mark--logo" not in html
    assert ">NAWA</span>" in html


def test_flag_for_first_host_country(client):
    html = client.get("/scholarships/nawa-banach-2026").text
    assert '/static/flags/pl.svg?v=' in html
    assert providers.flag_for("Atlantis") is None


def test_stats_and_spotlight(client):
    html = client.get("/scholarships").text
    assert "verified scholarships" in html
    # The open scholarship with the soonest deadline on 28 Oct 2026 closes 30 Oct.
    assert 'class="spotlight"' in html
    assert "days left" in html


def test_no_spotlight_when_filtering_closed(client):
    html = client.get("/scholarships", params={"status": "closed"}).text
    assert 'class="spotlight"' not in html
