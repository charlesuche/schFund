# Launch checklist (Phase 3b)

Things only a human can do. The setup is free: Render (website), Neon
(database), GitHub Actions (tests, deploys, weekly freshness check), Brevo
(problem-report emails). Prices checked 2026-10-29.

## 1. Code on GitHub
- [ ] Create a GitHub repository and push this folder (it is not a git repo yet).
      Check `.env` is not committed (it is in `.gitignore`).
- [ ] Default branch is `main` (deploys only run from `main`).

## 2. Database: Neon (free)
- [ ] Sign up at neon.com, create a project in **Frankfurt (aws-eu-central-1)**.
- [ ] Copy the **pooled** connection string (contains `-pooler`, ends with `sslmode=require`).
      This is `DATABASE_URL` for both Render and GitHub.

## 3. Website: Render (free)
- [ ] Sign up at render.com, connect the GitHub repo, choose **New > Blueprint**.
      It reads `render.yaml` (free plan, Frankfurt, auto-deploy off).
- [ ] Fill in the values Render asks for:
      `DATABASE_URL`, `SITE_URL` (your domain, e.g. `https://yourdomain.org`, no trailing slash;
      use the `onrender.com` address until the domain works), `SMTP_HOST` (`smtp-relay.brevo.com`,
      check in Brevo), `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`, `REPORT_TO`, `CONTACT_EMAIL`.
- [ ] Settings > Deploy Hook: copy the URL (a secret).

## 4. GitHub repository secrets (Settings > Secrets and variables > Actions)
- [ ] `RENDER_DEPLOY_HOOK_URL`: the Render deploy hook.
- [ ] `SITE_URL`: same as on Render.
- [ ] `DATABASE_URL`: the Neon connection string (the deploy job runs the loader with it).
- [ ] Settings > Actions > General > Workflow permissions: **Read and write**
      (the freshness workflow commits its report and opens issues).

## 5. Email: Brevo (free, 300 emails a day)
- [ ] Sign up and wait for Brevo to approve the account for sending.
- [ ] Add your domain under Senders & Domains and add the DNS records it shows (below).
- [ ] Create an SMTP key: that is `SMTP_PASSWORD`; the SMTP login is `SMTP_USER`.
- [ ] Pick `MAIL_FROM` (e.g. `no-reply@yourdomain.org`), `REPORT_TO` (your inbox),
      and `CONTACT_EMAIL` (shown on the Privacy page for data requests).

## 6. Domain and DNS
- [ ] Buy a domain (about $10–15 a year; the only cost).
- [ ] Render > Settings > Custom Domains: add it, then create the DNS record Render shows
      (usually a CNAME for `www`, and an A/ALIAS record for the bare domain). Render issues HTTPS itself.
- [ ] Brevo domain authentication: the DKIM and Brevo code records it shows, plus SPF and DMARC.
      Start DMARC with `p=none`.
- [ ] Update `SITE_URL` on Render and in GitHub to the final domain.

## 7. First deploy
- [ ] Push to `main`. Watch the "CI and deploy" workflow: tests, validator, deploy,
      wait for the new version, load records, check the live site.
- [ ] Open the site, a detail page, `/sitemap.xml`, `/robots.txt`.
- [ ] Send yourself a test problem report.
- [ ] Run the "Freshness check" workflow once by hand (Actions tab).

## 8. Search engines
- [ ] Google Search Console: verify the domain (DNS TXT record) and submit `/sitemap.xml`.
- [ ] Optional: Bing Webmaster Tools, same sitemap.

## 9. Before telling people
- [ ] Have the Privacy page checked by someone qualified (GDPR applies to you in Sweden;
      the Nigeria Data Protection Act 2023 to your users). It should also name who runs the site.
- [ ] Freshness check has run at least once on schedule (plan's launch threshold).

## Later, when traffic grows
- Render free sleeps after 15 minutes without visitors; the next visitor waits about 30–60 seconds.
  Moving to the $7/month Starter instance removes that. Change `plan: free` in `render.yaml`.
