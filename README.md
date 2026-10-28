# Scholarship Platform

Verified, detailed scholarship data for Nigerian and African students, with help preparing applications.

**Current phase:** building the scholarship dataset (Phase 1). See `AGENTS.md` for how agents work in this repo.

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
4. Optional, for later phases: install Docker and run `docker compose up -d` to start PostgreSQL with pgvector.

## Daily workflow

1. Add scholarships to research in `data/leads.csv` (status `new`).
2. Send the agent a prompt from `prompts/` (start with `prompts/01_research_leads.md`).
3. The agent writes drafts to `data/inbox/` and runs the validator.
4. You review each draft. Use Git's diff view to see exactly what changed.
5. Approve a draft by moving it to `data/records/`, then commit:

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
docs/extraction_prompt.md      Extraction rules and schema (v2.1)
schema/scholarship.schema.json JSON Schema used by the validator
data/leads.csv                 Research queue
data/inbox/                    Agent drafts, waiting for review
data/records/                  Approved records
scripts/validate.py            Schema and logic checks
prompts/                       Prompts to send to agents
docker-compose.yml             PostgreSQL + pgvector (later)
```
