# Prompt 02 — Re-check existing records

Use this when cycles roll over or a record is low-confidence.

---

Read `AGENTS.md` and `docs/extraction_prompt.md` first.

For each file in `data/records/` with `confidence_score` below 0.8 (or the files I name here: ___):

1. Re-check every field against the official source, especially dates, amounts and eligibility.
2. If anything changed or a new cycle has been announced, write the updated record to `data/inbox/<same-slug>.json` (do not edit `data/records/`).
3. Set `last_verified` to today and recompute `status` and `urgent_deadline`.

Run `python scripts/validate.py data/inbox`, fix all errors, then report what changed per record in plain English.
