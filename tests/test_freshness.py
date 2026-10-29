"""Tests for scripts/check_freshness.py. No live network: pages come from tests/fixtures/freshness/."""

import hashlib
import json
from datetime import date
from pathlib import Path

import httpx

import check_freshness as cf

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "freshness"
TODAY = date(2026, 10, 29)
SITE = "https://example.org"


def make_record(**overrides) -> dict:
    """A small record with only the fields the freshness check reads."""
    record = {
        "status": "closed",
        "last_verified": "2026-10-20",
        "official_apply_url": f"{SITE}/apply",
        "application_timeline": {
            "opening_date": "2026-01-10",
            "deadline_date": "2026-03-31",
            "next_cycle_expected": None,
        },
        "source_urls": [{"url": f"{SITE}/scholarship", "title": "Call", "type": "official", "used_for": "All"}],
    }
    record.update(overrides)
    return record


def write_records(folder: Path, records: dict[str, dict]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for slug, record in records.items():
        (folder / f"{slug}.json").write_text(json.dumps(record), encoding="utf-8")
    return folder


def mock_client(pages: dict[str, tuple[str, str]], robots: str = "") -> httpx.Client:
    """Client that serves saved files. pages: path -> (fixture file, content type).

    A path mapped to "DOWN" raises a connection error, like a site that is offline.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if path not in pages:
            return httpx.Response(404, text="not found")
        name, content_type = pages[path]
        if name == "DOWN":
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, content=(FIXTURES / name).read_bytes(), headers={"content-type": content_type})

    return httpx.Client(transport=httpx.MockTransport(handler))


def run_once(tmp_path: Path, records: dict[str, dict], pages: dict, robots: str = ""):
    records_dir = write_records(tmp_path / "records", records)
    return cf.run(
        records_dir=records_dir,
        hashes_path=tmp_path / "source_hashes.json",
        reports_dir=tmp_path / "reports",
        today=TODAY,
        client=mock_client(pages, robots),
        delay=0,
    )


def reasons_for(flags, slug: str) -> list[str]:
    return [flag.reason for flag in flags if flag.slug == slug]


# ---------------------------------------------------------------- source change check

HTML = "text/html; charset=utf-8"


def test_first_run_saves_hash_without_flagging(tmp_path):
    _, flags = run_once(tmp_path, {"a": make_record()}, {"/scholarship": ("page_v1.html", HTML)})
    assert flags == []
    hashes = json.loads((tmp_path / "source_hashes.json").read_text())
    assert hashes[f"{SITE}/scholarship"]["checked_on"] == TODAY.isoformat()


def test_unchanged_page_is_not_flagged_even_if_menu_and_footer_dates_change(tmp_path):
    run_once(tmp_path, {"a": make_record()}, {"/scholarship": ("page_v1.html", HTML)})
    _, flags = run_once(tmp_path, {"a": make_record()}, {"/scholarship": ("page_v1_new_chrome.html", HTML)})
    assert flags == []


def test_changed_page_is_flagged_for_recheck(tmp_path):
    run_once(tmp_path, {"a": make_record()}, {"/scholarship": ("page_v1.html", HTML)})
    report, flags = run_once(tmp_path, {"a": make_record()}, {"/scholarship": ("page_v2.html", HTML)})
    assert [(f.group, f.url) for f in flags] == [(cf.RECHECK, f"{SITE}/scholarship")]
    assert "source changed" in flags[0].reason
    text = report.read_text()
    recheck_section = text.split("## Re-check now")[1].split("## Watch")[0]
    assert f"`a`: source changed" in recheck_section
    assert f"[source]({SITE}/scholarship)" in recheck_section


def test_unreachable_page_is_watch_not_changed_and_keeps_old_hash(tmp_path):
    run_once(tmp_path, {"a": make_record()}, {"/scholarship": ("page_v1.html", HTML)})
    before = json.loads((tmp_path / "source_hashes.json").read_text())

    _, flags = run_once(tmp_path, {"a": make_record()}, {"/scholarship": ("DOWN", HTML)})
    assert [f.group for f in flags] == [cf.WATCH]
    assert flags[0].reason.startswith("unreachable")
    assert json.loads((tmp_path / "source_hashes.json").read_text()) == before

    # Back online and unchanged: still not "changed".
    _, flags = run_once(tmp_path, {"a": make_record()}, {"/scholarship": ("page_v1.html", HTML)})
    assert flags == []


def test_http_error_is_unreachable(tmp_path):
    _, flags = run_once(tmp_path, {"a": make_record()}, {})  # every page 404s
    assert reasons_for(flags, "a") == ["unreachable: HTTP 404"]


def test_pdf_source_hashes_extracted_text_not_bytes(tmp_path):
    pdf_record = make_record(source_urls=[{"url": f"{SITE}/call.pdf", "title": "Call", "type": "official", "used_for": "All"}])
    _, flags = run_once(tmp_path, {"a": pdf_record}, {"/call.pdf": ("call.pdf", "application/pdf")})
    assert flags == []

    pdf_bytes = (FIXTURES / "call.pdf").read_bytes()
    saved = json.loads((tmp_path / "source_hashes.json").read_text())[f"{SITE}/call.pdf"]["hash"]
    assert saved == cf.text_hash("Example Scholarship call 2027\nDeadline: 30 April 2027")
    assert saved != hashlib.sha256(pdf_bytes).hexdigest()


def test_robots_txt_is_respected(tmp_path):
    robots = f"User-agent: {cf.ROBOTS_AGENT}\nDisallow: /scholarship\n"
    _, flags = run_once(tmp_path, {"a": make_record()}, {"/scholarship": ("page_v1.html", HTML)}, robots)
    assert reasons_for(flags, "a") == ["unreachable: blocked by robots.txt"]


def test_shared_source_is_fetched_once(tmp_path):
    fetched = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=(FIXTURES / "page_v1.html").read_bytes(), headers={"content-type": HTML})

    records_dir = write_records(tmp_path / "records", {"a": make_record(), "b": make_record()})
    cf.run(records_dir=records_dir, hashes_path=tmp_path / "h.json", reports_dir=tmp_path / "r",
           today=TODAY, client=httpx.Client(transport=httpx.MockTransport(handler)), delay=0)
    assert fetched.count("/scholarship") == 1


def test_only_official_sources_are_fetched(tmp_path):
    record = make_record(source_urls=[
        {"url": f"{SITE}/scholarship", "title": "Call", "type": "official", "used_for": "All"},
        {"url": f"{SITE}/blog", "title": "Blog", "type": "secondary", "used_for": "Lead"},
    ])
    _, flags = run_once(tmp_path, {"a": record}, {"/scholarship": ("page_v1.html", HTML)})
    assert flags == []  # the blog URL would 404 if it were fetched


# ---------------------------------------------------------------- date rules


def test_sixty_day_rule():
    old = make_record(last_verified="2026-08-29")  # 61 days before TODAY
    edge = make_record(last_verified="2026-08-30")  # exactly 60 days: not flagged
    assert reasons_for(cf.date_flags("old", old, TODAY), "old") == ["last verified 2026-08-29 (61 days ago)"]
    assert cf.date_flags("edge", edge, TODAY) == []


def test_new_cycle_rule():
    timeline = {"opening_date": "2026-01-10", "deadline_date": "2026-03-31"}
    due = make_record(application_timeline={**timeline, "next_cycle_expected": "2026-10"})
    later = make_record(application_timeline={**timeline, "next_cycle_expected": "2026-11"})
    flags = cf.date_flags("due", due, TODAY)
    assert [(f.group, f.url) for f in flags] == [(cf.RECHECK, f"{SITE}/apply")]
    assert "new cycle due" in flags[0].reason
    assert cf.date_flags("later", later, TODAY) == []


def test_new_cycle_needs_a_passed_deadline():
    record = make_record(application_timeline={
        "opening_date": "2026-10-01", "deadline_date": "2026-12-01", "next_cycle_expected": "2026-10",
    })
    assert cf.date_flags("open", record, TODAY) == []


def test_unknown_live_status_is_watch():
    record = make_record(status="unknown", application_timeline={
        "opening_date": None, "deadline_date": None, "next_cycle_expected": None,
    })
    flags = cf.date_flags("u", record, TODAY)
    assert [(f.group, f.reason) for f in flags] == [(cf.WATCH, "status unknown")]


def test_stored_unknown_but_dates_decide_is_not_flagged():
    # The deadline has passed, so the live status is "closed", not "unknown".
    assert cf.date_flags("c", make_record(status="unknown"), TODAY) == []


# ---------------------------------------------------------------- whole run


def test_no_network_runs_only_date_rules(tmp_path):
    records_dir = write_records(tmp_path / "records", {"old": make_record(last_verified="2026-01-01")})

    def fail(request):
        raise AssertionError("network used with --no-network")

    report, flags = cf.run(records_dir=records_dir, hashes_path=tmp_path / "h.json", reports_dir=tmp_path / "r",
                           today=TODAY, network=False, client=httpx.Client(transport=httpx.MockTransport(fail)))
    assert [f.slug for f in flags] == ["old"]
    assert not (tmp_path / "h.json").exists()
    assert report.name == "freshness_2026-10-29.md"
    assert "not checked" in report.read_text()


def test_report_has_both_sections_and_one_line_per_record(tmp_path):
    record = make_record(status="unknown", last_verified="2026-01-01", application_timeline={
        "opening_date": None, "deadline_date": None, "next_cycle_expected": None,
    })
    report, _ = run_once(tmp_path, {"two-reasons": record}, {})
    text = report.read_text()
    assert "## Re-check now\n\nNothing." in text
    watch = text.split("## Watch")[1]
    lines = [line for line in watch.splitlines() if line.startswith("- ")]
    assert len(lines) == 1
    assert "last verified 2026-01-01" in lines[0] and "status unknown" in lines[0] and "unreachable" in lines[0]


def test_real_records_are_never_modified(tmp_path):
    """Run the date rules on the real data/records/ and check every file is byte-for-byte the same."""
    def snapshot() -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(cf.RECORDS_DIR.glob("*.json"))}

    before = snapshot()
    cf.run(hashes_path=tmp_path / "h.json", reports_dir=tmp_path / "r", today=TODAY, network=False)
    assert snapshot() == before


def test_robots_403_means_stay_out(tmp_path):
    """Bot protection often answers robots.txt with 403. We stay out and say why."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(403, text="Just a moment...")
        raise AssertionError("page fetched although robots.txt refused us")

    records_dir = write_records(tmp_path / "records", {"a": make_record()})
    _, flags = cf.run(records_dir=records_dir, hashes_path=tmp_path / "h.json", reports_dir=tmp_path / "r",
                      today=TODAY, client=httpx.Client(transport=httpx.MockTransport(handler)), delay=0)
    assert reasons_for(flags, "a") == ["unreachable: site refuses automated access (robots.txt gave HTTP 403)"]


def test_same_reason_from_two_sources_is_written_once(tmp_path):
    record = make_record(source_urls=[
        {"url": f"{SITE}/one", "title": "One", "type": "official", "used_for": "All"},
        {"url": f"{SITE}/two", "title": "Two", "type": "official", "used_for": "All"},
    ])
    report, _ = run_once(tmp_path, {"a": record}, {})
    line = [l for l in report.read_text().splitlines() if l.startswith("- `a`")][0]
    assert line.count("unreachable: HTTP 404") == 1
    assert f"[source]({SITE}/one)" in line and f"[source]({SITE}/two)" in line
