# Phase 2 plan — database and backend

## Goal

Serve the public website (search/listing and scholarship detail pages) from the approved records, with a JSON API the Flutter app can use later.

## Principles

1. **`data/records/` is the single source of truth.** The database is a copy. It can be deleted and rebuilt from the files at any time with one command.
2. **Simple and explicit over clever.** Plain SQL with psycopg 3, no ORM. Small functions. Code a student can read and explain.
3. **Status is computed live.** A record's `status` and `urgent_deadline` are true *as of `last_verified`*. The website must work them out from the dates and *today's* date, otherwise a page would still say "open" weeks after the deadline passed. The stored values are only used when the dates can't decide (e.g. `unknown`).

## Design decisions

### Database: one table, columns for filtering + the full record as JSONB

```
scholarships
  slug              text primary key        -- file name without .json
  title             text not null
  provider          text not null
  levels            text[] not null         -- for the Level filter
  host_countries    text[] not null         -- for the Country filter
  nationalities     text[] not null         -- for the Nigeria filter
  funding_type      text not null
  opening_date      date
  deadline_date     date
  stored_status     text not null           -- status as of last_verified
  last_verified     date not null
  confidence        numeric(3,2) not null
  search_text       tsvector                -- title + provider + fields + countries
  data              jsonb not null          -- the full record, used to render pages
  loaded_at         timestamptz not null default now()
```

Why: filtering and sorting need real columns; showing a page needs the whole record. One table is easy to understand and rebuild. Split into more tables only when a real need appears.

No migrations tool yet: because the database is rebuilt from files, `db/schema.sql` simply drops and recreates the table.

### Loader: `scripts/load_records.py`

1. Run the same checks as `scripts/validate.py` on `data/records/`. If any record fails, load nothing and exit with an error.
2. Inside one transaction: upsert every record by slug, then delete rows whose file no longer exists.
3. Print how many were inserted, updated and deleted.

Running it twice in a row must change nothing (idempotent).

### API (FastAPI, prefix `/api`)

- `GET /api/scholarships` — query params: `q`, `level`, `country`, `nationality`, `status` (open, closed, upcoming, unknown — live status), `funding`, `sort` (`deadline` default, `title`), `limit`, `offset`. Returns list items (slug, title, provider, levels, countries, funding_type, live status, deadline_date, days_left, a short money summary) plus `total` and filter counts.
- `GET /api/scholarships/{slug}` — the full record plus live `status`, `days_left`, `urgent`.
- `GET /api/health` — database reachable or not.

### Public pages (Jinja2, server-rendered)

- `/` and `/scholarships` — search/listing page (Figma frame "05 Web – Search & listing").
- `/scholarships/{slug}` — detail page (Figma frame "06 Web – Scholarship detail").
- Plain HTML + one CSS file. No JavaScript framework. Pages must work with JavaScript turned off and on a phone screen.
- Each detail page has a unique `<title>`, meta description, and the "Verified on" date visible.
- Filter counts come from the database, never hard-coded.

Design source: Figma file "Scholarship Platform – Screens" (colour tokens in the "Tokens" collection, font Plus Jakarta Sans).

### Folder layout added in Phase 2

```
app/
  main.py            FastAPI app, routes
  db.py              connection helper
  queries.py         SQL queries as plain functions
  status.py          live status / days-left logic
  templates/         Jinja2 templates
  static/styles.css
db/schema.sql
scripts/load_records.py
tests/
```

## Order of work

| Prompt | Builds | Done when |
|---|---|---|
| 03 | Schema v2.2 | Validator passes on all records in the new format |
| 04 | Table + loader | `load_records.py` loads 11 records; rerun changes nothing; tests pass |
| 05 | JSON API | Endpoints return correct live status and filter counts; tests pass |
| 06 | Public pages | Both pages render from the database and match the Figma frames closely |
