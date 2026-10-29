-- The scholarships table. data/records/ is the source of truth: this table is
-- only a copy, so this file simply drops and recreates it (no migrations).
-- Rebuild with: python scripts/load_records.py --reset

DROP TABLE IF EXISTS scholarships;

CREATE TABLE scholarships (
    slug            text primary key,           -- file name without .json
    title           text not null,
    provider        text not null,
    levels          text[] not null,            -- for the Level filter
    host_countries  text[] not null,            -- for the Country filter
    nationalities   text[] not null,            -- for the Nigeria filter
    funding_type    text not null,
    opening_date    date,
    deadline_date   date,
    stored_status   text not null,              -- status as of last_verified
    last_verified   date not null,
    confidence      numeric(3,2) not null,
    search_text     tsvector,                   -- title + provider + fields + countries
    data            jsonb not null,             -- the full record, used to render pages
    loaded_at       timestamptz not null default now()
);

-- GIN indexes make "array contains" (levels @> '{Master}') and full-text search fast.
CREATE INDEX scholarships_levels_idx         ON scholarships USING gin (levels);
CREATE INDEX scholarships_host_countries_idx ON scholarships USING gin (host_countries);
CREATE INDEX scholarships_nationalities_idx  ON scholarships USING gin (nationalities);
CREATE INDEX scholarships_search_text_idx    ON scholarships USING gin (search_text);

-- The listing is sorted by deadline by default.
CREATE INDEX scholarships_deadline_date_idx  ON scholarships (deadline_date);
