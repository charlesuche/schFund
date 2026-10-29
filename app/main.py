"""FastAPI app: the JSON API (/api/...) and the public HTML pages.

Run: uvicorn app.main:app --reload
"""

import hashlib
import logging
import os
import re
import smtplib
from datetime import date
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from app import mailer, queries
from app.db import get_connection
from app.providers import flag_for, provider_for
from app.status import live_status

APP_DIR = Path(__file__).resolve().parent
SITE_NAME = "Scholarship Platform"
PAGE_SIZE = 20

STATIC_DIR = APP_DIR / "static"
log = logging.getLogger(__name__)

# Browsers may keep a versioned file (?v=<hash>) for a year: a changed file
# gets a new hash, so a new URL. Unversioned files are re-checked after an hour.
LONG_CACHE = "public, max-age=31536000, immutable"
SHORT_CACHE = "public, max-age=3600"


class CachedStaticFiles(StaticFiles):
    """StaticFiles that also sends Cache-Control headers."""

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            versioned = b"v=" in scope.get("query_string", b"")
            # The font is referenced from inside the CSS, so it has no ?v=; it never changes.
            if versioned or path.startswith("fonts/"):
                response.headers["Cache-Control"] = LONG_CACHE
            else:
                response.headers["Cache-Control"] = SHORT_CACHE
        return response


app = FastAPI(title="Scholarship Platform API")
# Compresses HTML, CSS, SVG and JSON for slow mobile data. Tiny responses are
# sent as they are, since compressing them saves nothing.
app.add_middleware(GZipMiddleware, minimum_size=500)
app.mount("/static", CachedStaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")

_static_versions: dict[str, str] = {}


def static_url(path: str) -> str:
    """/static/<path>?v=<short hash of the file>, so caches update when the file changes."""
    if path not in _static_versions:
        file = STATIC_DIR / path
        digest = hashlib.sha256(file.read_bytes()).hexdigest()[:10] if file.is_file() else "0"
        _static_versions[path] = digest
    return f"/static/{path}?v={_static_versions[path]}"


def site_url(request: Request) -> str:
    """Public address of the site, used for canonical links and the sitemap.

    SITE_URL is set on the server (e.g. https://example.org). Render also
    gives the onrender.com address; locally we fall back to the request's host.
    """
    url = os.environ.get("SITE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or str(request.base_url)
    return url.rstrip("/")


# Allowed filter values. FastAPI answers 422 for anything else.
class Level(str, Enum):
    bachelor = "Bachelor"
    master = "Master"
    phd = "PhD"
    postdoc = "Postdoc"


class Status(str, Enum):
    open = "open"
    closed = "closed"
    upcoming = "upcoming"
    unknown = "unknown"


class Funding(str, Enum):
    fully = "Fully Funded"
    partially = "Partially Funded"
    tuition = "Tuition Only"
    stipend = "Stipend Only"


class Sort(str, Enum):
    deadline = "deadline"
    title = "title"


def get_db_url() -> str | None:
    # A dependency, so tests can point the app at the test database.
    return os.environ.get("DATABASE_URL")


def get_db(url: str | None = Depends(get_db_url)):
    """One connection per request. Simple; add a pool when traffic needs it."""
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    conn = get_connection(url)
    try:
        yield conn
    finally:
        conn.close()


def get_today() -> date:
    # A dependency, so tests can replace "today" with a fixed date.
    return date.today()


PERIOD_WORDS = {"month": "/ month", "year": "/ year", "total": "in total", "one-off": "one-off"}


def format_amount(amount: float) -> str:
    return f"{amount:,.0f}"


def money_summary(stipend: dict | None) -> str | None:
    """A short line like 'EUR 1,445–8,605 / year', or None if no amount is known."""
    if not stipend:
        return None
    low, high = stipend.get("amount_min"), stipend.get("amount_max")
    if low is None and high is None:
        return None
    if low is None or high is None or low == high:
        amount = format_amount(low if low is not None else high)
    else:
        amount = f"{format_amount(low)}–{format_amount(high)}"
    text = f"{stipend.get('currency') or ''} {amount}".strip()
    period = PERIOD_WORDS.get(stipend.get("period"))
    if period:
        text += f" {period}"
    return text


def list_item(row: dict, today: date) -> dict:
    live = live_status(row["opening_date"], row["deadline_date"], row["stored_status"], today)
    return {
        "slug": row["slug"],
        "title": row["title"],
        "provider": row["provider"],
        "levels": row["levels"],
        "countries": row["host_countries"],
        "funding_type": row["funding_type"],
        "status": live["status"],
        "deadline_date": row["deadline_date"],
        "days_left": live["days_left"],
        "urgent": live["urgent"],
        "money": money_summary(row["stipend"]),
        "provider_logo": row["provider_logo"],
    }


@app.get("/api/scholarships")
def list_scholarships(
    q: str | None = Query(None, max_length=200),
    level: Level | None = None,
    country: str | None = Query(None, max_length=100),
    nationality: str | None = Query(None, max_length=100),
    status: Status | None = None,
    funding: Funding | None = None,
    sort: Sort = Sort.deadline,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn=Depends(get_db),
    today: date = Depends(get_today),
):
    filters = queries.Filters(
        q=q,
        level=level.value if level else None,
        country=country,
        nationality=nationality,
        status=status.value if status else None,
        funding=funding.value if funding else None,
    )
    rows, total = queries.list_scholarships(conn, filters, today, sort.value, limit, offset)

    items = []
    for row in rows:
        items.append(list_item(row, today))

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filter_counts": queries.filter_counts(conn, filters, today),
    }


@app.get("/api/scholarships/{slug}")
def get_scholarship(slug: str, conn=Depends(get_db), today: date = Depends(get_today)):
    row = queries.get_scholarship(conn, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    live = live_status(row["opening_date"], row["deadline_date"], row["stored_status"], today)
    return {
        "slug": row["slug"],
        "status": live["status"],
        "days_left": live["days_left"],
        "urgent": live["urgent"],
        "stored_status": row["stored_status"],
        "record": row["data"],
    }


@app.get("/api/health")
def health(url: str | None = Depends(get_db_url)):
    # Not using get_db: a failed connection should give 503, not a 500 error.
    if not url:
        return JSONResponse(status_code=503, content={"database": "unreachable"})
    try:
        with get_connection(url) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError:
        return JSONResponse(status_code=503, content={"database": "unreachable"})
    # The deploy workflow waits until this shows the commit it just deployed.
    return {"database": "ok", "commit": os.environ.get("RENDER_GIT_COMMIT")}


# --- Public HTML pages ------------------------------------------------------

STATUS_LABELS = {"open": "Open", "closed": "Closed", "upcoming": "Next call expected", "unknown": "Dates being checked"}

# Display names from the Figma design. Filter values in URLs stay the stored ones.
LABELS = {
    "status": {"open": "Open now", "closed": "Closed", "upcoming": "Next call expected", "unknown": "Dates being checked"},
    "level": {"Bachelor": "Bachelor's", "Master": "Master's", "PhD": "PhD", "Postdoc": "Postdoc / research stay"},
    "funding": {
        "Fully Funded": "Fully funded",
        "Partially Funded": "Partially funded",
        "Tuition Only": "Tuition only",
        "Stipend Only": "Stipend only",
    },
}


def format_date(value) -> str:
    """'2026-05-08' or a date -> '8 May 2026'."""
    if value is None:
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return f"{value.day} {value:%b %Y}"


def format_number(value) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return f"{value:,.0f}"
    # 71.4 -> "71.4", 1445.08 -> "1,445.08": up to two decimals, no trailing zeros.
    return f"{value:,.2f}".rstrip("0")


def format_month(value: str | None) -> str:
    """'2027-01' -> 'Jan 2027'. Anything else is shown as written in the record."""
    if not value:
        return ""
    try:
        year, month = value.split("-")
        return f"{date(int(year), int(month), 1):%b %Y}"
    except ValueError:
        return value


def level_names(levels: list[str]) -> str:
    names = []
    for level in levels:
        names.append(LABELS["level"].get(level, level))
    return ", ".join(names)


def days_left_text(days_left: int | None) -> str:
    if days_left is None:
        return ""
    if days_left == 0:
        return "Closes today"
    if days_left == 1:
        return "1 day left"
    return f"{days_left} days left"


templates.env.filters["date"] = format_date
templates.env.filters["number"] = format_number
templates.env.filters["days_left"] = days_left_text
templates.env.filters["month"] = format_month
templates.env.filters["levels"] = level_names
templates.env.globals["status_labels"] = STATUS_LABELS
templates.env.globals["labels"] = LABELS
templates.env.filters["provider"] = provider_for
templates.env.filters["flag"] = flag_for
templates.env.globals["site_name"] = SITE_NAME
templates.env.globals["static_url"] = static_url


def allowed(value: str | None, choices: type[Enum]) -> str | None:
    """Keep a filter value only if it is one of the allowed ones.

    The API answers 422 for bad values; a web page just ignores them, so an
    old or hand-edited link still shows results instead of an error.
    """
    for choice in choices:
        if value == choice.value:
            return value
    return None


def clean_text(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value[:max_length]


@app.get("/", response_class=HTMLResponse)
@app.get("/scholarships", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str | None = None,
    level: str | None = None,
    country: str | None = None,
    nationality: str | None = None,
    status: str | None = None,
    funding: str | None = None,
    sort: str | None = None,
    page: int = Query(1, ge=1, le=1000),
    conn=Depends(get_db),
    today: date = Depends(get_today),
):
    filters = queries.Filters(
        q=clean_text(q, 200),
        level=allowed(level, Level),
        country=clean_text(country, 100),
        nationality=clean_text(nationality, 100),
        status=allowed(status, Status),
        funding=allowed(funding, Funding),
    )
    sort_value = allowed(sort, Sort) or Sort.deadline.value
    offset = (page - 1) * PAGE_SIZE

    rows, total = queries.list_scholarships(conn, filters, today, sort_value, PAGE_SIZE, offset)
    items = []
    for row in rows:
        item = list_item(row, today)
        # Page-only extras for the card's date line; the API items stay as they are.
        item["opening_date"] = row["opening_date"]
        item["next_cycle_expected"] = row["next_cycle_expected"]
        item["next_cycle_confidence"] = row["next_cycle_confidence"]
        items.append(item)

    # Site-wide numbers for the hero tiles, from the database (not the current filters).
    all_counts = queries.filter_counts(conn, queries.Filters(), today)
    stats = {
        "total": sum(all_counts["status"].values()),
        "open": all_counts["status"].get("open", 0),
        "fully_funded": all_counts["funding"].get("Fully Funded", 0),
    }

    # "Closing soon" spotlight: the open scholarship with the soonest deadline
    # among the current results. Only on the first page, and only when one is open.
    spotlight = None
    if page == 1 and filters.status in (None, "open"):
        open_filters = queries.Filters(**{**filters.__dict__, "status": "open"})
        open_rows, _ = queries.list_scholarships(conn, open_filters, today, "deadline", 1, 0)
        if open_rows:
            first = queries.get_scholarship(conn, open_rows[0]["slug"])
            spotlight = list_item(open_rows[0], today)
            spotlight["deadline_time"] = first["data"]["application_timeline"]["deadline_time"]

    # Query strings for the previous/next and sort links keep every current filter.
    filter_params = {}
    for key, value in [("q", filters.q), ("level", filters.level), ("country", filters.country),
                       ("nationality", filters.nationality), ("status", filters.status),
                       ("funding", filters.funding)]:
        if value:
            filter_params[key] = value
    base_params = {**filter_params, "sort": sort_value}
    prev_url = None
    next_url = None
    if page > 1:
        prev_url = request.url.path + "?" + urlencode({**base_params, "page": page - 1})
    if offset + PAGE_SIZE < total:
        next_url = request.url.path + "?" + urlencode({**base_params, "page": page + 1})
    # Plain links instead of a dropdown, so sorting works without JavaScript.
    sort_urls = {}
    for choice in Sort:
        sort_urls[choice.value] = request.url.path + "?" + urlencode({**filter_params, "sort": choice.value})

    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "filters": filters,
            "sort": sort_value,
            "items": items,
            "total": total,
            "page": page,
            "page_count": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
            "prev_url": prev_url,
            "next_url": next_url,
            "sort_urls": sort_urls,
            "counts": queries.filter_counts(conn, filters, today),
            "has_filters": len(filter_params) > 0,
            "stats": stats,
            "spotlight": spotlight,
            # Filtered and searched views repeat the same scholarships, so only
            # the plain list is offered to search engines.
            "canonical": site_url(request) + ("/" if page == 1 else f"/scholarships?page={page}"),
            "noindex": len(filter_params) > 0,
        },
    )


def meta_description(record: dict, deadline: str) -> str:
    """Built only from the record's own fields."""
    parts = [record["provider_organization"]]
    levels = ", ".join(record["academic_level"])
    countries = ", ".join(record["host_countries"])
    parts.append(f"{levels} scholarship in {countries}")
    parts.append(record["financial_coverage"]["funding_type"])
    if deadline:
        parts.append(f"Deadline {deadline}")
    text = ". ".join(parts) + "."
    if len(text) > 160:
        text = text[:157].rstrip() + "..."
    return text


def structured_data(record: dict, url: str, description: str) -> dict:
    """schema.org MonetaryGrant for the detail page, from the record's own fields only.

    MonetaryGrant is the schema.org type for money given by a funder, which is
    what a scholarship is. The amount is left out on purpose: MonetaryAmount
    has no "per month" or "per year", so a monthly stipend would look like a
    one-off sum.
    """
    return {
        "@context": "https://schema.org",
        "@type": "MonetaryGrant",
        "name": record["scholarship_title"],
        "description": description,
        "url": url,
        "funder": {"@type": "Organization", "name": record["provider_organization"]},
    }


@app.get("/scholarships/{slug}", response_class=HTMLResponse)
def detail_page(request: Request, slug: str, conn=Depends(get_db), today: date = Depends(get_today)):
    row = queries.get_scholarship(conn, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    record = row["data"]
    live = live_status(row["opening_date"], row["deadline_date"], row["stored_status"], today)
    deadline_text = format_date(record["application_timeline"]["deadline_date"])

    # The score bars are drawn as a share of the total points available.
    score_total = 0
    for criterion in record["selection_criteria"]["criteria"]:
        if criterion.get("max_points") is not None:
            score_total += criterion["max_points"]

    canonical = f"{site_url(request)}/scholarships/{slug}"
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "canonical": canonical,
            "structured_data": structured_data(record, canonical, meta_description(record, deadline_text)),
            "slug": slug,
            "r": record,
            "live": live,
            "money": money_summary(record["financial_coverage"]["stipend"]),
            "description": meta_description(record, deadline_text),
            "nigeria_listed": "Nigeria" in record["eligible_nationalities"],
            "score_total": score_total,
        },
    )


# --- Search engines ---------------------------------------------------------


def xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@app.get("/sitemap.xml")
def sitemap(request: Request, conn=Depends(get_db)):
    """Every public page, built from the database so new records appear on the next load."""
    base = site_url(request)
    urls = [(f"{base}/", None)]
    for path in INFO_PAGES:
        urls.append((f"{base}{path}", None))
    for row in queries.sitemap_rows(conn):
        urls.append((f"{base}/scholarships/{row['slug']}", row["last_verified"].isoformat()))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in urls:
        entry = f"  <url><loc>{xml_escape(loc)}</loc>"
        if lastmod:
            entry += f"<lastmod>{lastmod}</lastmod>"
        lines.append(entry + "</url>")
    lines.append("</urlset>")
    return Response("\n".join(lines) + "\n", media_type="application/xml")


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request):
    # The JSON API is for the app, not for search results.
    return f"User-agent: *\nDisallow: /api/\n\nSitemap: {site_url(request)}/sitemap.xml\n"


# --- Trust pages -------------------------------------------------------------

INFO_PAGES = {
    "/how-we-verify": "how_we_verify.html",
    "/report-a-problem": "report.html",
    "/privacy": "privacy.html",
}


@app.get("/how-we-verify", response_class=HTMLResponse)
def how_we_verify_page(request: Request):
    return templates.TemplateResponse(request, "how_we_verify.html", {"canonical": site_url(request) + "/how-we-verify"})


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    context = {"canonical": site_url(request) + "/privacy", "contact_email": os.environ.get("CONTACT_EMAIL")}
    return templates.TemplateResponse(request, "privacy.html", context)


REPORT_MAX_MESSAGE = 3000
# Good enough to catch typos; we never send to this address, only reply to it.
EMAIL_PATTERN = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")


def report_page(request: Request, values: dict, error: str | None = None, sent: bool = False, status_code: int = 200):
    context = {
        "canonical": site_url(request) + "/report-a-problem",
        "values": values,
        "error": error,
        "sent": sent,
        "max_message": REPORT_MAX_MESSAGE,
    }
    return templates.TemplateResponse(request, "report.html", context, status_code=status_code)


def clean_page_path(value: str | None) -> str:
    """Only a path on this site (e.g. /scholarships/nawa-banach-2026), never a full outside URL."""
    value = (value or "").strip()[:300]
    if value.startswith("/") and not value.startswith("//"):
        return value
    return ""


@app.get("/report-a-problem", response_class=HTMLResponse)
def report_form(request: Request, page: str | None = None):
    return report_page(request, {"page": clean_page_path(page), "message": "", "email": ""})


@app.post("/report-a-problem", response_class=HTMLResponse)
async def report_submit(request: Request):
    # A plain form post, read with the standard library (no extra package).
    body = (await request.body()).decode("utf-8", errors="replace")
    form = {key: values[0] for key, values in parse_qs(body, max_num_fields=10).items()}
    values = {
        "page": clean_page_path(form.get("page")),
        "message": (form.get("message") or "").strip(),
        "email": (form.get("email") or "").strip(),
    }

    # Honeypot: people never see the "website" field, simple spam bots fill it.
    # Pretend it worked so the bot learns nothing, and send nothing.
    if form.get("website"):
        return report_page(request, {}, sent=True)

    if not values["message"]:
        return report_page(request, values, "Please tell us what is wrong.", status_code=400)
    if len(values["message"]) > REPORT_MAX_MESSAGE:
        return report_page(request, values, f"Please keep it under {REPORT_MAX_MESSAGE} characters.", status_code=400)
    if values["email"] and not EMAIL_PATTERN.match(values["email"]):
        return report_page(request, values, "That email address doesn't look right. You can also leave it empty.", status_code=400)

    try:
        mailer.send_problem_report(values["page"], values["message"], values["email"] or None)
    except (mailer.MailNotConfigured, smtplib.SMTPException, OSError) as error:
        log.error("Problem report could not be sent: %s", error)
        return report_page(request, values, "Sorry, we couldn't send your report just now. Please try again later.",
                           status_code=503)
    return report_page(request, {}, sent=True)


@app.exception_handler(StarletteHTTPException)
async def not_found_page(request: Request, exc: StarletteHTTPException):
    """Friendly HTML 404 for pages; the API keeps its JSON errors."""
    if exc.status_code == 404 and not request.url.path.startswith("/api/"):
        return templates.TemplateResponse(request, "404.html", {"noindex": True}, status_code=404)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
