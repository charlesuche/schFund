"""provider_logo: the record's logo is shown when its file exists, else the monogram tile."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import load_records
from app import providers
from app.db import get_connection
from app.main import app, get_db_url, get_today

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORDS = REPO_ROOT / "data" / "records"
LOGO = {"file": "nawa.svg", "source_url": "https://nawa.gov.pl/press", "added_on": "2026-10-29"}


@pytest.fixture(scope="module")
def logo_db(test_db_url, tmp_path_factory):
    """Test database with a copy of two real records; only the copy gets a logo."""
    folder = tmp_path_factory.mktemp("records")
    record = json.loads((RECORDS / "nawa-banach-2026.json").read_text(encoding="utf-8"))
    record["provider_logo"] = LOGO
    (folder / "nawa-banach-2026.json").write_text(json.dumps(record), encoding="utf-8")
    shutil.copy(RECORDS / "daad-epos-bonn-global-health-2027.json", folder)

    # The validator checks the logo file exists, so give it one to find.
    logos = tmp_path_factory.mktemp("logos")
    (logos / "nawa.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    mp = pytest.MonkeyPatch()
    mp.setattr(load_records.validate, "LOGOS_DIR", logos)
    with get_connection(test_db_url) as conn:
        load_records.load_records(conn, records_dir=folder, reset=True)
    mp.undo()
    yield test_db_url


@pytest.fixture
def client(logo_db, tmp_path, monkeypatch):
    app.dependency_overrides[get_db_url] = lambda: logo_db
    app.dependency_overrides[get_today] = lambda: date(2026, 10, 28)
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_static_dir(monkeypatch, folder: Path, with_logo: bool) -> None:
    (folder / "logos").mkdir()
    if with_logo:
        (folder / "logos" / "nawa.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    monkeypatch.setattr(providers, "STATIC_DIR", folder)


def test_logo_shown_on_detail_page_when_file_exists(client, tmp_path, monkeypatch):
    use_static_dir(monkeypatch, tmp_path, with_logo=True)
    html = client.get("/scholarships/nawa-banach-2026").text
    assert "/static/logos/nawa.svg" in html
    assert 'alt="NAWA logo"' in html
    assert ">NAWA</span>" not in html


def test_logo_shown_on_listing_card(client, tmp_path, monkeypatch):
    use_static_dir(monkeypatch, tmp_path, with_logo=True)
    html = client.get("/scholarships").text
    assert html.count("/static/logos/nawa.svg") == 1
    # The record without provider_logo keeps its monogram.
    assert ">DAAD</span>" in html


def test_monogram_when_logo_file_is_missing(client, tmp_path, monkeypatch):
    use_static_dir(monkeypatch, tmp_path, with_logo=False)
    html = client.get("/scholarships/nawa-banach-2026").text
    assert "provider-mark--logo" not in html
    assert ">NAWA</span>" in html


def test_monogram_when_record_has_no_logo(client, tmp_path, monkeypatch):
    use_static_dir(monkeypatch, tmp_path, with_logo=True)
    html = client.get("/scholarships/daad-epos-bonn-global-health-2027").text
    assert "provider-mark--logo" not in html
    assert ">DAAD</span>" in html


def test_api_list_includes_provider_logo(client):
    items = {item["slug"]: item for item in client.get("/api/scholarships").json()["items"]}
    assert items["nawa-banach-2026"]["provider_logo"] == LOGO
    assert items["daad-epos-bonn-global-health-2027"]["provider_logo"] is None
