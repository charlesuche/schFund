# AGENTS.md — Scholarship Platform

Instructions for any AI coding agent working in this repo (Cursor, VS Code Copilot, Claude Code, Codex). Read this file fully before doing anything.

## What this project is

A scholarship platform for undergraduate, master's and PhD scholarships worldwide. Main users at launch: **Nigerian students**, then other Africans. The site lists only legitimate scholarships, with very detailed, verified information and help preparing applications.

The value of the platform is **trustworthy data**. A wrong deadline or an invented requirement can cost a student a scholarship. Accuracy beats speed, always.

## Current phase: Phase 1 — data collection

Right now we are only building the scholarship dataset. No website, API or database code yet unless the human asks for it.

Planned stack for later phases (do not start these unasked):
- Backend: Python + FastAPI
- Database: PostgreSQL with pgvector (see `docker-compose.yml`)
- Public pages: server-rendered HTML (Jinja) for search engines
- App: Flutter
- Chatbot: retrieval (RAG) over verified records only

## Folder layout

```
docs/extraction_prompt.md     The extraction rules and schema. Follow it exactly.
schema/scholarship.schema.json  Machine-checkable version of the schema.
data/leads.csv                Scholarships waiting to be researched.
data/inbox/                   YOUR drafts go here, one file per scholarship.
data/records/                 Human-approved records. Do NOT edit unless asked.
scripts/validate.py           Checks records against the schema and rules.
prompts/                      Task prompts the human sends to agents.
```

## Workflow for data tasks

1. Read `docs/extraction_prompt.md` before researching anything.
2. Research each scholarship from **official sources first** (the provider's own website and its official call PDF). Read the full call PDF where one exists; landing pages often leave out documents, GPA rules and deadlines.
3. Write each scholarship as **one JSON object** in `data/inbox/<slug>.json`.
4. Run `python scripts/validate.py data/inbox` and fix every error before finishing.
5. Update the lead's `status` in `data/leads.csv` to `drafted` (or `excluded` / `blocked`, with a reason in `notes`).
6. Finish with a short report (see "How to report").

The human reviews files in `data/inbox/` and moves approved ones to `data/records/`. Never move files into `data/records/` yourself.

### Slug rules

- Lowercase, words joined with hyphens, provider then award then cycle start year.
- Example: `nawa-banach-2026.json`, `univr-international-masters-2026.json`, `dsu-toscana-phd-2026.json`.
- Before creating a file, check `data/records/` and `data/inbox/` for an existing record of the same scholarship. Update it instead of making a duplicate.

### Hard rules

- **Never invent a value.** If no source supports a field, use `null` and say so in `verification_notes`.
- Official source beats any blog or aggregator. Record disagreements in `verification_notes`.
- Every record needs at least one `source_urls` entry; records with `confidence_score` of 0.8 or higher need at least one **official** source.
- Store money in the original currency. Do not convert.
- Do not paste long text from websites into records. Write facts in your own short words.
- If a site blocks you or needs a login, mark the lead `blocked` in `data/leads.csv`. Do not try to get around it.
- Do not fill application forms, create accounts or pay anything.

## How to report

At the end of a task, reply with:
- Files created or changed.
- For each record: status (open/closed/upcoming/unknown), deadline, confidence score.
- Fields left `null` that a human should check.
- Anything surprising (e.g. sources disagreeing, a lead that turned out to be a scam).

Use plain, simple English. Keep it short.

## Coding style (for later phases)

- Simple, explicit code a student can read and defend. Prefer plain `for` loops over clever one-liners.
- Comments in plain English explaining *why*, not *what*.
- Small functions, clear names, type hints in Python.
- Ask before adding a new dependency.

## Commands

```
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/validate.py         # checks data/records and data/inbox
python scripts/validate.py data/inbox
```
