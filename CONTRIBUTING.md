# Contributing to OpenProspect

Thanks for helping. This guide covers the dev setup, how the monorepo is laid out, and the most
common kinds of contribution.

## Dev setup

You need [uv](https://docs.astral.sh/uv/) and Python 3.11+. Docker is only needed to run the
services (CRM, mailer, verifier), not for the tests.

```bash
git clone https://github.com/<you>/openprospect
cd openprospect
uv sync                  # one virtualenv with every package installed in editable mode
uv run openprospect --help
```

## Checks (run them before every PR)

There is no CI pipeline, so these run on your machine. A PR should pass all three:

```bash
uv run pytest            # every package's tests
uv run ruff check .      # lint
uv run ruff format --check .
```

Tests must not touch the network, Docker or a real inbox. Use `tmp_path` and set
`OPENPROSPECT_HOME` to it when a test needs a workspace.

## Monorepo layout

```text
apps/cli/                 the `openprospect` command: argument parsing, the daily pipeline, doctor/stats/export
packages/core/            paths, .env + settings.yaml, the SQLite lead store, text helpers
packages/sources/         where leads come from: Google Maps, remote-friendly companies, Reddit buyer intent
packages/enrich/          reads each lead's website: emails, signals, fixable problems ("pain points")
packages/verify/          MX checks, Reacher deep checks, chain detection
packages/scoring/         0-100 score, tiers, the first line and subject of each email
packages/mail/            Listmonk sequences, IMAP reply / bounce / opt-out handling, plain SMTP
packages/crm/             Twenty CRM client + sync
packages/jobs/            the job & freelance track
infra/                    docker-compose.yml and the Huginn scenario
config/  templates/  prompts/   examples and copy users edit
docs/                     user documentation
```

Every package lives under the shared `openprospect.*` namespace (`from openprospect.core import db`).

### Package boundaries

- `core` depends on nothing else in the repo. Everything may depend on `core`.
- `crm` depends only on `core`. `sources` and `mail` may call `crm` (intent deals, reply stages).
- `jobs` may use `mail` (SMTP) and `verify` (MX), never the other way round.
- Only `apps/cli` wires steps together. Packages expose functions that take a database
  connection; they never call each other's pipeline steps.
- Keep a step idempotent: re-running it must not duplicate leads, CRM records or emails.
  The lead store is the memory that makes that possible.

## Common contributions

**A new lead source.** Add a module to `packages/sources/src/openprospect/sources/` that turns
records into lead dicts and saves them with `db.upsert_lead(conn, lead)`. Give `source_id` a stable,
unique prefix (`yelp:<id>`), set `source`, then add a CLI command and a pipeline step in `apps/cli`.

**A new pain point.** Detect the signal in `packages/enrich/.../signals.py`, turn it into a
pain point in `pains.py`, then give it a weight (`scoring/model.py` `PAIN_WEIGHT`), a first line,
subject and problem phrase (`scoring/copy.py`) and an offer sentence in
`config/settings.example.yaml`. Only add problems a normal visitor can observe; no probing.

**A new job board.** In `packages/jobs/src/openprospect/jobs/boards.py`, add a
`fetch_<board>(session, max_age_days)` function that returns a list of postings built with
`_posting(...)`, so they have the same shape as the others. Then add `("Board name", fetch_<board>)`
to the `BOARDS` list at the bottom of that file; the finder runs every entry. Prefer official APIs
or RSS feeds, and catch errors so one dead board never stops the hunt.

## Commit style

Short imperative subject, optionally prefixed with the package: `enrich: detect expired SSL`,
`cli: add export --tier`. Explain the why in the body when it isn't obvious.

## Pull request checklist

- [ ] `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] New behaviour has a test
- [ ] Docs / `settings.example.yaml` updated if users see the change
- [ ] No personal data, real email addresses, API keys or scraped data in the diff
- [ ] Sending behaviour stays safe by default (limits, opt-outs, suppression)

## Code of conduct

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
