# Prompt 01 — Research the next batch of leads

Copy everything below the line into the agent chat (Agent mode).

---

Read `AGENTS.md` and `docs/extraction_prompt.md` first.

Then take the first 3 rows in `data/leads.csv` with status `new` and, for each one:

1. Research it from official sources. Read the official call PDF if one exists.
2. Check `data/records/` and `data/inbox/` so you don't duplicate an existing record.
3. Write the record to `data/inbox/<slug>.json`, following the schema exactly. Use `null` for anything you cannot confirm. Today's date is the `last_verified` date.
4. Update that lead's status in `data/leads.csv`.

When all 3 are done, run `python scripts/validate.py data/inbox` and fix every error.

Then give me the short report described in `AGENTS.md`. Stop after these 3 leads; do not start more.
