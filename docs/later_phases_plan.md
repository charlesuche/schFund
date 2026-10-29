# Later phases plan — launch, freshness, accounts, app, chatbot

Read this before any task from prompts 07–11. Phase 2 (database, API, public pages) is finished.

## Order and why

| Phase | Builds | Prompt | Why this order |
|---|---|---|---|
| 3a | Freshness checks | 08 | A live site showing an outdated deadline is the worst failure this platform can have. Build the safety net before going public. |
| 3b | Launch the public website | 07 | The website is how students find us (Google). It starts building search traffic the day it is live, so launch early. |
| 4 | Accounts + deadline alerts | 09 | Alerts are the first reason to sign up. Needs careful data protection, so it comes after launch, not before. |
| 5 | Flutter app | 10 | The app is for returning users (saved scholarships, checklists). Build it once the website has users to return. |
| 6 | Chatbot | 11 | A chatbot is only as good as the records behind it. With few records it mostly says "I don't know". Build it when the dataset is large. |

Run 08 before 07. Data collection (prompt 01) keeps running alongside every phase.

**Launch threshold (recommendation):** go public when there are at least 30 approved records, including the big programmes Nigerian students search for most (e.g. Erasmus Mundus, DAAD, Stipendium Hungaricum, Commonwealth, MEXT, Chevening), and the freshness check runs on a schedule.

## Principles that still apply

1. `data/records/` stays the single source of truth. Nothing in later phases writes to it automatically. Every change still goes through `data/inbox/` and human review.
2. Simple, explicit code. No new framework or paid service without asking.
3. Never show a student something the records don't support.
4. Collect as little personal data as possible.

## Phase 3a — Freshness checks (prompt 08)

Goal: know which records may be out of date, without changing any record automatically.

- A script `scripts/check_freshness.py` that, for each approved record:
  1. **Date rules (no network):** flag records whose `deadline_date` has passed and whose `next_cycle_expected` month has arrived; records with `last_verified` older than 60 days; records with status `unknown`.
  2. **Source change check (network):** fetch each *official* source URL politely (one request per URL, identifying user agent, respect robots.txt, timeout, no retries in a loop), extract the main text, store a hash in `data/source_hashes.json`, and flag the record if the hash changed since last run. Pages that fail to load are flagged as "unreachable", not as changed.
- Output: `reports/freshness_<date>.md` listing flagged records with the reason, grouped as "re-check now" and "watch".
- A scheduled run (GitHub Actions, weekly) that commits the report and opens a GitHub issue when anything is flagged.
- The human then runs prompt 02 (re-check) on the flagged records.

## Phase 3b — Launch the website (prompt 07)

- **Hosting:** the agent compares 2–3 current options and recommends one; Charles decides. Requirements: Docker or Python support, managed PostgreSQL with pgvector, EU region, custom domain with HTTPS, scheduled jobs, low or free cost at small scale. Prices must be checked on the providers' own pages on the day.
- **Deploy flow:** push to `main` → tests + validator run → deploy → loader reloads records. A failing validator blocks the deploy.
- **Speed for mobile data in Nigeria:** small pages, compressed CSS, no large images, cache headers. Logos as small optimised files.
- **Search engines:** `sitemap.xml`, `robots.txt`, canonical URLs, unique titles and descriptions, structured data (schema.org) on detail pages where a fitting type exists.
- **Trust pages:** "How we verify" (the rules from the extraction prompt in plain English), "Report a problem" (a simple form that emails Charles, no account needed), Privacy policy.
- **Logos:** a `provider_logo` field in the record schema (`file`, `source_url`, `added_on`) and files in `app/static/logos/`. Monogram fallback when no logo exists.
- **Basic, privacy-friendly analytics** (no cookies requiring consent) or none at all.

## Phase 4 — Accounts and deadline alerts (prompt 09)

- **Sign-in by email link** (no passwords): user enters email, receives a one-time link that expires in 15 minutes.
- **Stored data, and only this:** email, saved scholarship slugs, alert settings, consent timestamp. No names, phone numbers, grades or nationality unless a later feature truly needs them.
- **Alerts:**
  - "Notify me when it opens": email when a saved scholarship's live status becomes open.
  - Deadline reminders at 14 days and 3 days before a saved scholarship's deadline.
  - Sent by a daily scheduled job. Every email has a one-click unsubscribe.
- **Email provider:** a transactional email service with a free tier; agent proposes, Charles decides.
- **Data protection:** Charles is in Sweden (EU GDPR applies) and users are mainly in Nigeria (Nigeria Data Protection Act 2023 applies). Build in: clear consent text at sign-up, "download my data", "delete my account" (deletes everything), privacy policy updated to match exactly what is stored. Get the privacy text checked by someone qualified before launch of accounts.
- **Later channel idea:** Telegram or WhatsApp alerts are popular in Nigeria. Not in this phase.

## Phase 5 — Flutter app (prompt 10)

- Android first. Uses the existing JSON API only; the app has no database of its own besides a local cache.
- Screens from Figma frames 01–04 (detail, search & list, eligibility checker, checklist) and the same colour tokens.
- Offline: saved scholarships and checklists cached on the device, so they open without data.
- Same accounts as the website (email link). Checklist progress stored on the device first; syncing is a later step.
- The eligibility checker needs schema v2.2's numeric fields (`min_grade_percent`, degree dates) to give real answers. Where a record lacks them, the app says "check the call" instead of guessing.

## Phase 6 — Chatbot (prompt 11)

- **Answers only from approved records.** Retrieval over record text stored in pgvector; each answer names the scholarship and links its official source.
- **Says "I don't know"** when the records don't contain the answer, and suggests the official page.
- **Test set first:** 30 real questions with expected answers (written by Charles) in `tests/chatbot_eval.jsonl`. The bot must pass them before going live, and after every change.
- **Costs under control:** small model, daily question limit per user, monthly spending cap.
- **Freshness:** embeddings rebuilt by the loader whenever records change.
