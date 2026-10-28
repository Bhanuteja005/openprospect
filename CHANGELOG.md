# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-28

Initial public release.

### Added

- **Agency track:** find local businesses on Google Maps, read their websites, verify their
  emails, score them 0-100 (tiers A/B/C), sync them to a CRM, and send a personalised 3-email
  sequence in each business's own working hours.
- Lead sources: Google Maps (gosom/google-maps-scraper), remote-friendly companies
  (remoteintech/remote-jobs) and Reddit buyer-intent posts (Huginn).
- Website enrichment: contact emails, socials, site builder, analytics / ad pixels, booking and
  chat tools, and passive checks for fixable problems (no website, site down, certificate issues,
  old TLS / WordPress / PHP / jQuery, not mobile-friendly, slow, outdated, no booking, low rating).
- Email verification with Reacher, and a free MX + "published on their own site" fallback when
  port 25 is blocked. Big chains are detected and never emailed.
- Personalised first line and subject per lead, built only from observable facts; optional
  local-AI first lines with Ollama.
- Listmonk sending with warm-up, daily limits, per-country caps and business-hours scheduling.
- IMAP reply, bounce and opt-out detection with a permanent suppression list.
- Twenty CRM sync: companies, contacts, deals with estimated value, and insight notes;
  rate-limit aware.
- **Job & freelance track:** fresh remote openings from Hacker News "Who is hiring", Remotive,
  Remote OK, Himalayas, We Work Remotely, Jobicy and Working Nomads; strict recipient rules;
  AI-written drafts from your profile; safe sending with a 90-day re-contact window.
- `openprospect` CLI: `init`, `up`, `setup`, `doctor`, `run`, step-by-step commands, `stats`,
  `export`, `jobs`, and a `daemon` scheduler.
- Docker Compose stack for Twenty, Listmonk, Reacher, Huginn and optional Firecrawl.
- Documentation, configuration examples and responsible-use guide.
