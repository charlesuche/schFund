# Scholarship Platform

Verified, detailed scholarship data for students, with help preparing applications.

**Current phase:** database and backend (Phase 2), with data collection continuing. See `AGENTS.md` for how agents work in this repo.

## One-time setup

1. Install Python 3.11+ and Git.
2. Open this folder in Cursor or VS Code.
3. In the terminal:

   ```
   python -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python scripts/validate.py
   ```

   The last command should print `All checks passed`.

## Database (Phase 2)

The database is a copy of `data/records/`. You can delete it and rebuild it at any time.

1. Install Docker Desktop and start it.
2. Copy the settings file (once): `cp .env.example .env`
   If another PostgreSQL already uses port 5432 on your computer (e.g. Homebrew), set `DB_PORT` to a free port (e.g. 55432) and use the same port in both URLs in `.env`.
3. Start PostgreSQL:

   ```
   docker compose up -d
   ```

4. Create the test database (once, used by `pytest`):

   ```
   docker compose exec db createdb -U scholar scholarships_test
   ```

5. Load the records:

   ```
   python scripts/load_records.py --reset
   ```

   It prints how many records were inserted, updated, unchanged and deleted. `--reset` drops and recreates the table first; without it, the loader only applies changes. If any record fails validation, nothing is loaded.

6. Run the tests:

   ```
   pytest
   ```

7. Run the API:

   ```
   uvicorn app.main:app --reload
   ```

   Then open http://127.0.0.1:8000/ for the public search page, http://127.0.0.1:8000/scholarships/nawa-banach-2026 for an example detail page, http://127.0.0.1:8000/api/scholarships for the JSON API (try `?nationality=Nigeria`), or http://127.0.0.1:8000/docs for every endpoint and filter.

Stop the database with `docker compose down` (your data stays in a Docker volume).

## Daily workflow

1. Add scholarships to research in `data/leads.csv` (status `new`).
2. Send the agent a prompt from `prompts/` (start with `prompts/01_research_leads.md`).
3. The agent writes drafts to `data/inbox/` and runs the validator.
4. You review each draft. Use Git's diff view to see exactly what changed.
5. Approve a draft by moving it to `data/records/`, run `python scripts/load_records.py` to update the database, then commit:

   ```
   git add -A
   git commit -m "Add <scholarship name>"
   ```

## Which agent reads which file

| Tool | Reads |
|---|---|
| Cursor | `AGENTS.md` and `.cursor/rules/project.mdc` |
| VS Code + GitHub Copilot | `AGENTS.md` and `.github/copilot-instructions.md` |
| VS Code + Claude Code | `CLAUDE.md` (points to `AGENTS.md`) |

The agent needs web access for research. In Cursor use Agent mode (web search is built in). In Copilot, use Agent mode with the fetch tool enabled.

## Folder layout

```
AGENTS.md                      Rules for every agent
docs/extraction_prompt.md      Extraction rules and schema (v2.2)
docs/phase2_plan.md            Phase 2 design decisions
schema/scholarship.schema.json JSON Schema used by the validator
data/leads.csv                 Research queue
data/inbox/                    Agent drafts, waiting for review
data/records/                  Approved records
scripts/validate.py            Schema and logic checks
scripts/load_records.py        Copies data/records/ into PostgreSQL
db/schema.sql                  The scholarships table
app/                           Backend: main.py (API + pages), queries.py (SQL), status.py (live status), db.py,
                               templates/ (Jinja2 pages), static/styles.css
tests/                         pytest tests
prompts/                       Prompts to send to agents
docker-compose.yml             PostgreSQL + pgvector
```
