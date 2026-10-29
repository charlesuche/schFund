"""Find approved records that may be out of date. Never changes a record.

Usage:
    python scripts/check_freshness.py               # date rules + source change check
    python scripts/check_freshness.py --no-network  # date rules only

Writes reports/freshness_<YYYY-MM-DD>.md and updates data/source_hashes.json.
The human then re-checks the flagged records (prompt 02) through data/inbox/.

Two kinds of checks:
1. Date rules (no network): a new cycle is due, last_verified is old, or the
   live status is "unknown".
2. Source change check: each official source page is fetched once, its main
   text is hashed, and the hash is compared with the one saved last run.
   A page that fails to load is "unreachable", never "changed".
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.status import live_status  # noqa: E402  (needs REPO_ROOT on the path)

RECORDS_DIR = REPO_ROOT / "data" / "records"
HASHES_PATH = REPO_ROOT / "data" / "source_hashes.json"
REPORTS_DIR = REPO_ROOT / "reports"

STALE_DAYS = 60
TIMEOUT_SECONDS = 20
# Pause between requests so we never hit a site in a burst.
DELAY_SECONDS = 1.0
ROBOTS_AGENT = "SchFundFreshnessCheck"
USER_AGENT = (
    f"{ROBOTS_AGENT}/1.0 (scholarship listing; checks each official page "
    "once a week to see if it changed; respects robots.txt)"
)

RECHECK = "Re-check now"
WATCH = "Watch"


@dataclass
class Flag:
    slug: str
    group: str  # RECHECK or WATCH
    reason: str
    url: str | None


# ---------------------------------------------------------------- records


def load_records(folder: Path) -> list[tuple[str, dict]]:
    """(slug, record) for every JSON file in the folder. Read-only."""
    records = []
    for path in sorted(folder.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            records.append((path.stem, json.load(f)))
    return records


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def official_urls(record: dict) -> list[str]:
    urls = []
    for source in record.get("source_urls", []):
        if source.get("type") == "official" and source["url"] not in urls:
            urls.append(source["url"])
    return urls


def main_link(record: dict) -> str | None:
    """The link shown next to a date-rule flag: the apply page, else the first official source."""
    if record.get("official_apply_url"):
        return record["official_apply_url"]
    urls = official_urls(record)
    return urls[0] if urls else None


# ---------------------------------------------------------------- date rules


def date_flags(slug: str, record: dict, today: date) -> list[Flag]:
    """Flags that need no network: new cycle due, old last_verified, unknown status."""
    flags = []
    timeline = record.get("application_timeline") or {}
    opening = parse_date(timeline.get("opening_date"))
    deadline = parse_date(timeline.get("deadline_date"))
    link = main_link(record)

    # next_cycle_expected is a month ("2027-01"). Comparing the strings works
    # because both are zero-padded YYYY-MM.
    next_cycle = timeline.get("next_cycle_expected")
    if deadline is not None and deadline < today and next_cycle and next_cycle <= today.strftime("%Y-%m"):
        flags.append(Flag(slug, RECHECK, f"new cycle due (deadline passed, next call expected {next_cycle})", link))

    verified = parse_date(record.get("last_verified"))
    if verified is not None and (today - verified).days > STALE_DAYS:
        days = (today - verified).days
        flags.append(Flag(slug, WATCH, f"last verified {verified.isoformat()} ({days} days ago)", link))

    status = live_status(opening, deadline, record.get("status", "unknown"), today)["status"]
    if status == "unknown":
        flags.append(Flag(slug, WATCH, "status unknown", link))

    return flags


# ---------------------------------------------------------------- text extraction

# Parts of a page that change without the scholarship changing.
SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside",
             "form", "svg", "iframe", "template", "button", "select"}
SKIP_ROLES = {"navigation", "banner", "contentinfo"}


class MainTextParser(HTMLParser):
    """Collects visible text, skipping navigation, scripts and footers.

    If the page has <main> (or <article>), only that text is kept, since the
    rest is usually menus and sidebars shared across the whole site.

    Real pages often leave tags like <li> or <p> unclosed, so we only count
    the one tag name we are inside (e.g. "footer"), not every tag.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_tag: str | None = None
        self.skip_nesting = 0
        self.main_tag: str | None = None
        self.main_nesting = 0
        self.all_text: list[str] = []
        self.main_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        role = dict(attrs).get("role") or ""
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_nesting += 1
            return
        if tag in SKIP_TAGS or role in SKIP_ROLES:
            self.skip_tag, self.skip_nesting = tag, 1
            return
        if self.main_tag:
            if tag == self.main_tag:
                self.main_nesting += 1
        elif tag in ("main", "article") or role == "main":
            self.main_tag, self.main_nesting = tag, 1

    def handle_endtag(self, tag: str) -> None:
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_nesting -= 1
                if self.skip_nesting == 0:
                    self.skip_tag = None
            return
        if self.main_tag and tag == self.main_tag:
            self.main_nesting -= 1
            if self.main_nesting == 0:
                self.main_tag = None

    def handle_data(self, data: str) -> None:
        if self.skip_tag:
            return
        self.all_text.append(data)
        if self.main_tag:
            self.main_text.append(data)


# Short lines like "Last updated 12.03.2026" or "© 2026 University" change on
# their own; they would make every page look "changed".
VOLATILE_LINE = re.compile(
    r"(last (updated|modified|reviewed)|updated on|page updated|zuletzt|stand:|"
    r"ultimo aggiornamento|aggiornato il|senast (uppdaterad|ändrad)|©|copyright)",
    re.IGNORECASE,
)


def normalise(text: str) -> str:
    """One clean line per line of text, without volatile date lines."""
    lines = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if not line:
            continue
        if len(line) < 120 and VOLATILE_LINE.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def html_text(html: str) -> str:
    parser = MainTextParser()
    parser.feed(html)
    parser.close()
    chosen = parser.main_text if "".join(parser.main_text).strip() else parser.all_text
    return normalise("\n".join(chosen))


def pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return normalise("\n".join(pages))


def extract_text(content: bytes, content_type: str, encoding: str | None) -> str:
    """Main text of an HTML page or a PDF. Raises ValueError for other types."""
    content_type = content_type.lower()
    if "pdf" in content_type or content.startswith(b"%PDF"):
        return pdf_text(content)
    if "html" in content_type or "text/" in content_type or not content_type:
        return html_text(content.decode(encoding or "utf-8", errors="replace"))
    raise ValueError(f"unsupported content type {content_type}")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- fetching


class RobotsCache:
    """robots.txt rules per site, fetched once per run."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.rules: dict[str, RobotFileParser | str] = {}

    def check(self, url: str) -> str | None:
        """None if we may fetch the URL, otherwise the reason we may not."""
        parts = urlsplit(url)
        site = f"{parts.scheme}://{parts.netloc}"
        if site not in self.rules:
            self.rules[site] = self._load(site)
        rules = self.rules[site]
        if isinstance(rules, str):
            return rules
        if not rules.can_fetch(ROBOTS_AGENT, url):
            return "blocked by robots.txt"
        return None

    def _load(self, site: str) -> RobotFileParser | str:
        parser = RobotFileParser()
        try:
            response = self.client.get(f"{site}/robots.txt")
        except httpx.HTTPError as error:
            return f"robots.txt could not be read ({type(error).__name__})"
        # Same meaning as Python's own RobotFileParser.read():
        # 401/403 = keep out, other 4xx = no rules, 5xx = try another week.
        if response.status_code in (401, 403):
            # Often a bot-protection page rather than a real robots.txt. We stay
            # out either way, but say what happened.
            return f"site refuses automated access (robots.txt gave HTTP {response.status_code})"
        elif 400 <= response.status_code < 500:
            parser.allow_all = True
        elif response.status_code >= 500:
            return f"robots.txt returned HTTP {response.status_code}"
        else:
            parser.parse(response.text.splitlines())
        return parser


@dataclass
class FetchResult:
    text_hash: str | None
    problem: str | None  # why the page could not be read, if it could not


def fetch_source(client: httpx.Client, robots: RobotsCache, url: str) -> FetchResult:
    """Fetch one URL once and hash its main text. Never retries."""
    refused = robots.check(url)
    if refused:
        return FetchResult(None, refused)
    try:
        response = client.get(url)
    except httpx.HTTPError as error:
        return FetchResult(None, f"could not connect ({type(error).__name__})")
    if response.status_code >= 400:
        return FetchResult(None, f"HTTP {response.status_code}")
    try:
        text = extract_text(response.content, response.headers.get("content-type", ""), response.encoding)
    except Exception as error:  # a broken PDF must not stop the whole run
        return FetchResult(None, f"could not read the page ({error})")
    if not text:
        # e.g. a scanned PDF or a page built only by JavaScript: nothing to compare.
        return FetchResult(None, "no text found on the page")
    return FetchResult(text_hash(text), None)


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
    )


@dataclass
class SourceSummary:
    checked: int = 0
    new: int = 0
    unchanged: int = 0
    changed: int = 0
    unreachable: int = 0


def source_flags(
    records: list[tuple[str, dict]],
    hashes: dict,
    client: httpx.Client,
    today: date,
    delay: float = DELAY_SECONDS,
) -> tuple[list[Flag], SourceSummary]:
    """Check every official source once and update `hashes` in place.

    Several records share the same source (e.g. one DAAD page), so each URL is
    fetched only once per run.
    """
    urls_to_slugs: dict[str, list[str]] = {}
    for slug, record in records:
        for url in official_urls(record):
            urls_to_slugs.setdefault(url, []).append(slug)

    robots = RobotsCache(client)
    flags = []
    summary = SourceSummary()
    for index, (url, slugs) in enumerate(urls_to_slugs.items()):
        if index and delay:
            time.sleep(delay)
        result = fetch_source(client, robots, url)
        summary.checked += 1

        if result.problem:
            # Keep the old hash so next week compares against the last good copy.
            summary.unreachable += 1
            for slug in slugs:
                flags.append(Flag(slug, WATCH, f"unreachable: {result.problem}", url))
            continue

        previous = hashes.get(url, {}).get("hash")
        if previous is None:
            summary.new += 1
        elif previous == result.text_hash:
            summary.unchanged += 1
        else:
            summary.changed += 1
            for slug in slugs:
                flags.append(Flag(slug, RECHECK, f"source changed (last seen {hashes[url]['checked_on']})", url))
        hashes[url] = {"hash": result.text_hash, "checked_on": today.isoformat()}

    return flags, summary


# ---------------------------------------------------------------- report


def load_hashes(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_hashes(path: Path, hashes: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(hashes.items())), f, indent=2)
        f.write("\n")


def report_lines(flags: list[Flag], group: str) -> list[str]:
    """One line per record: slug, its reasons, and the links behind them."""
    by_slug: dict[str, list[Flag]] = {}
    for flag in flags:
        if flag.group == group:
            by_slug.setdefault(flag.slug, []).append(flag)

    lines = []
    for slug in sorted(by_slug):
        reasons = []
        links = []
        for flag in by_slug[slug]:
            # Two sources failing the same way should read as one reason.
            if flag.reason not in reasons:
                reasons.append(flag.reason)
            if flag.url and flag.url not in links:
                links.append(flag.url)
        link_text = ", ".join(f"[source]({url})" for url in links) or "no source link"
        lines.append(f"- `{slug}`: {'; '.join(reasons)} ({link_text})")
    return lines


def write_report(
    flags: list[Flag],
    today: date,
    record_count: int,
    summary: SourceSummary | None,
    reports_dir: Path,
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"freshness_{today.isoformat()}.md"

    lines = [f"# Freshness check {today.isoformat()}", ""]
    lines.append(f"{record_count} approved records checked. {len(flagged_slugs(flags))} flagged.")
    if summary is None:
        lines.append("Source pages were not checked (run with --no-network).")
    else:
        lines.append(
            f"{summary.checked} official source pages fetched: {summary.unchanged} unchanged, "
            f"{summary.changed} changed, {summary.unreachable} unreachable, "
            f"{summary.new} seen for the first time (hash saved, nothing to compare yet)."
        )
    for group in (RECHECK, WATCH):
        lines += ["", f"## {group}", ""]
        group_lines = report_lines(flags, group)
        lines += group_lines or ["Nothing."]
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def flagged_slugs(flags: list[Flag]) -> set[str]:
    return {flag.slug for flag in flags}


# ---------------------------------------------------------------- main


def run(
    records_dir: Path = RECORDS_DIR,
    hashes_path: Path = HASHES_PATH,
    reports_dir: Path = REPORTS_DIR,
    today: date | None = None,
    network: bool = True,
    client: httpx.Client | None = None,
    delay: float = DELAY_SECONDS,
) -> tuple[Path, list[Flag]]:
    """Run all checks and write the report. Returns (report path, flags)."""
    today = today or date.today()
    records = load_records(records_dir)

    flags = []
    for slug, record in records:
        flags += date_flags(slug, record, today)

    summary = None
    if network:
        hashes = load_hashes(hashes_path)
        own_client = client is None
        client = client or make_client()
        try:
            new_flags, summary = source_flags(records, hashes, client, today, delay)
        finally:
            if own_client:
                client.close()
        flags += new_flags
        save_hashes(hashes_path, hashes)

    path = write_report(flags, today, len(records), summary, reports_dir)
    return path, flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-network", action="store_true", help="run only the date rules")
    args = parser.parse_args()

    path, flags = run(network=not args.no_network)
    count = len(flagged_slugs(flags))
    print(f"{count} records flagged. Report: {path.relative_to(REPO_ROOT)}")

    # Lets the GitHub workflow decide whether to open an issue.
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"flagged={count}\nreport={path.relative_to(REPO_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
