"""Launch features: sitemap, robots.txt, canonical links, structured data,
trust pages, the problem report form, compression, cache headers, page size."""

import gzip
import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import mailer
from app.main import LONG_CACHE, SHORT_CACHE, app, get_db_url, get_today

REPO_ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 10, 28)
SITE = "https://scholarships.example.org"


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


@pytest.fixture(autouse=True)
def site_url(monkeypatch):
    monkeypatch.setenv("SITE_URL", SITE)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)


# ---------------------------------------------------------------- sitemap and robots


def test_sitemap_lists_every_record_with_last_verified(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    xml = response.text
    for slug, record in all_records().items():
        assert f"<url><loc>{SITE}/scholarships/{slug}</loc><lastmod>{record['last_verified']}</lastmod></url>" in xml


def test_sitemap_lists_home_and_trust_pages(client):
    xml = client.get("/sitemap.xml").text
    for path in ["/", "/how-we-verify", "/report-a-problem", "/privacy"]:
        assert f"<loc>{SITE}{path}</loc>" in xml
    assert xml.count("<url>") == len(all_records()) + 4


def test_robots_points_to_sitemap_and_keeps_api_out(client):
    text = client.get("/robots.txt").text
    assert f"Sitemap: {SITE}/sitemap.xml" in text
    assert "Disallow: /api/" in text


# ---------------------------------------------------------------- canonical and structured data


def canonical(html: str) -> str | None:
    match = re.search(r'<link rel="canonical" href="([^"]+)">', html)
    return match.group(1) if match else None


def test_canonical_links(client):
    assert canonical(client.get("/scholarships/nawa-banach-2026").text) == f"{SITE}/scholarships/nawa-banach-2026"
    assert canonical(client.get("/").text) == f"{SITE}/"
    assert canonical(client.get("/scholarships").text) == f"{SITE}/"
    assert canonical(client.get("/scholarships?page=2").text) == f"{SITE}/scholarships?page=2"
    assert canonical(client.get("/privacy").text) == f"{SITE}/privacy"


def test_filtered_lists_are_not_indexed(client):
    assert 'name="robots" content="noindex' not in client.get("/scholarships").text
    assert 'name="robots" content="noindex' in client.get("/scholarships?country=Italy").text
    assert 'name="robots" content="noindex' in client.get("/scholarships?q=DAAD").text


def test_404_is_not_indexed(client):
    response = client.get("/scholarships/nope")
    assert response.status_code == 404
    assert 'name="robots" content="noindex' in response.text
    assert canonical(response.text) is None


def test_detail_has_monetary_grant_from_record_fields_only(client):
    html = client.get("/scholarships/nawa-banach-2026").text
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    data = json.loads(match.group(1))
    record = all_records()["nawa-banach-2026"]
    assert data["@type"] == "MonetaryGrant"
    assert data["name"] == record["scholarship_title"]
    assert data["funder"] == {"@type": "Organization", "name": record["provider_organization"]}
    assert data["url"] == f"{SITE}/scholarships/nawa-banach-2026"
    # No amount: schema.org can't say "per month", so it would mislead.
    assert "amount" not in data


def test_structured_data_cannot_break_out_of_the_script_tag(client):
    # tojson escapes < > & so a title can never close the <script> early.
    html = client.get("/scholarships/nawa-banach-2026").text
    script = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    assert "<" not in script


# ---------------------------------------------------------------- trust pages


@pytest.mark.parametrize("path, heading", [
    ("/how-we-verify", "How we verify scholarships"),
    ("/privacy", "Privacy"),
    ("/report-a-problem", "Report a problem"),
])
def test_trust_pages_load_and_are_linked_from_every_page(client, path, heading):
    response = client.get(path)
    assert response.status_code == 200
    assert f"<h1>{heading}</h1>" in response.text
    assert f'href="{path}"' in client.get("/").text


def test_privacy_says_no_cookies_and_names_processors(client):
    html = client.get("/privacy").text
    assert "No cookies" in html
    for name in ["Render", "Neon", "Brevo"]:
        assert name in html


def test_privacy_shows_contact_email_only_when_set(client, monkeypatch):
    assert "mailto:" not in client.get("/privacy").text
    monkeypatch.setenv("CONTACT_EMAIL", "privacy@example.org")
    assert 'href="mailto:privacy@example.org"' in client.get("/privacy").text


def test_pages_set_no_cookies(client):
    for path in ["/", "/scholarships/nawa-banach-2026", "/report-a-problem"]:
        assert "set-cookie" not in client.get(path).headers


def test_no_third_party_resources(client):
    # Fonts and everything else come from our own server (see the Privacy page).
    html = client.get("/").text
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html


def test_detail_page_links_to_report_with_page_filled_in(client):
    html = client.get("/scholarships/nawa-banach-2026").text
    assert 'href="/report-a-problem?page=/scholarships/nawa-banach-2026"' in html
    form = client.get("/report-a-problem", params={"page": "/scholarships/nawa-banach-2026"}).text
    assert 'value="/scholarships/nawa-banach-2026"' in form


# ---------------------------------------------------------------- report form


@pytest.fixture
def sent(monkeypatch) -> list[dict]:
    """Capture reports instead of sending email."""
    reports = []

    def fake_send(page, message, reply_email):
        reports.append({"page": page, "message": message, "email": reply_email})

    monkeypatch.setattr(mailer, "send_problem_report", fake_send)
    return reports


def post_report(client, **fields):
    return client.post("/report-a-problem", data=fields)


def test_report_is_emailed(client, sent):
    response = post_report(client, page="/scholarships/nawa-banach-2026", message="Deadline moved to 15 May.",
                           email="student@example.com", website="")
    assert response.status_code == 200
    assert "Thank you" in response.text
    assert sent == [{"page": "/scholarships/nawa-banach-2026", "message": "Deadline moved to 15 May.",
                     "email": "student@example.com"}]


def test_report_without_email_is_fine(client, sent):
    post_report(client, message="Broken link")
    assert sent[0]["email"] is None


def test_honeypot_pretends_success_and_sends_nothing(client, sent):
    response = post_report(client, message="Buy cheap watches", website="http://spam.example")
    assert response.status_code == 200
    assert "Thank you" in response.text
    assert sent == []


def test_empty_message_is_rejected(client, sent):
    response = post_report(client, message="   ", email="a@b.co")
    assert response.status_code == 400
    assert "Please tell us what is wrong." in response.text
    assert 'value="a@b.co"' in response.text  # what they typed is kept
    assert sent == []


def test_too_long_message_is_rejected(client, sent):
    assert post_report(client, message="x" * 3001).status_code == 400
    assert sent == []


@pytest.mark.parametrize("bad", ["not-an-email", "a@b", "a@b.co\nBcc: x@y.z", "<a@b.co>"])
def test_bad_email_is_rejected(client, sent, bad):
    assert post_report(client, message="Hi", email=bad).status_code == 400
    assert sent == []


def test_outside_urls_are_dropped_from_page_field(client, sent):
    post_report(client, page="https://evil.example/phish", message="Hi")
    post_report(client, page="//evil.example", message="Hi")
    assert [report["page"] for report in sent] == ["", ""]


def test_mail_failure_shows_an_error_and_keeps_the_message(client, monkeypatch):
    for name in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "REPORT_TO"]:
        monkeypatch.delenv(name, raising=False)
    response = post_report(client, message="The deadline is wrong")
    assert response.status_code == 503
    assert "couldn&#39;t send your report" in response.text
    assert "The deadline is wrong" in response.text


# ---------------------------------------------------------------- mailer


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.calls.append("send")
        self.message = message


def test_mailer_sends_over_starttls_with_reply_to(monkeypatch):
    settings = {"SMTP_HOST": "smtp.example.org", "SMTP_USER": "u", "SMTP_PASSWORD": "p",
                "MAIL_FROM": "site@example.org", "REPORT_TO": "me@example.org"}
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    FakeSMTP.instances = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    mailer.send_problem_report("/privacy", "Typo in paragraph 2", "student@example.com")

    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example.org", 587)
    assert smtp.calls == ["starttls", ("login", "u", "p"), "send"]
    assert smtp.message["To"] == "me@example.org"
    assert smtp.message["Reply-To"] == "student@example.com"
    assert "Typo in paragraph 2" in smtp.message.get_content()


def test_mailer_refuses_without_settings(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with pytest.raises(mailer.MailNotConfigured):
        mailer.send_problem_report("", "Hi", None)


# ---------------------------------------------------------------- speed


def test_html_and_css_are_compressed(client):
    for path in ["/", "/static/styles.css"]:
        response = client.get(path, headers={"Accept-Encoding": "gzip"})
        assert response.headers.get("content-encoding") == "gzip", path


def test_static_cache_headers(client):
    css_link = re.search(r'href="(/static/styles\.css\?v=[0-9a-f]+)"', client.get("/").text).group(1)
    assert client.get(css_link).headers["cache-control"] == LONG_CACHE
    assert client.get("/static/styles.css").headers["cache-control"] == SHORT_CACHE
    assert client.get("/static/fonts/plus-jakarta-sans-latin.woff2").headers["cache-control"] == LONG_CACHE


def test_static_version_changes_with_the_file_contents():
    from app import main
    first = main.static_url("styles.css")
    assert re.fullmatch(r"/static/styles\.css\?v=[0-9a-f]{10}", first)
    assert main.static_url("styles.css") == first  # cached, not re-read per request


def page_weight(client, path: str) -> int:
    """HTML plus the CSS and font it needs, uncompressed (the worst case). Logos excluded."""
    html = client.get(path).text
    total = len(html.encode("utf-8"))
    total += len(client.get("/static/styles.css").content)
    total += len(client.get("/static/fonts/plus-jakarta-sans-latin.woff2").content)
    for src in set(re.findall(r'src="(/static/(?!logos/)[^"]+)"', html)):
        total += len(client.get(src).content)
    return total


@pytest.mark.parametrize("path", ["/", "/scholarships/nawa-banach-2026"])
def test_pages_stay_under_200_kb(client, path):
    assert page_weight(client, path) < 200_000
