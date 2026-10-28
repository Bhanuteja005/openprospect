# Architecture

OpenProspect is a small amount of Python glue around seven self-hosted services, organised as
a monorepo of single-purpose packages. This page explains how the pieces fit, where the data
lives and how to extend it.

- [The big picture](#the-big-picture)
- [Packages and boundaries](#packages-and-boundaries)
- [Why a uv workspace with namespace packages](#why-a-uv-workspace-with-namespace-packages)
- [Data: what lives where](#data-what-lives-where)
- [The lead lifecycle](#the-lead-lifecycle)
- [The services](#the-services)
- [Extending OpenProspect](#extending-openprospect)

## The big picture

![How OpenProspect works](assets/pipeline.svg)

There are two independent tracks, and each is a sequence of **idempotent steps**. A step
reads what it needs from the lead store, does its work, writes the result back and commits.
Every step skips work that is already recorded as done (a lead already enriched, verified,
scored, synced or emailed), so you can rerun the daily job after a crash, or run any step by hand
at any time. Leads are unique in the store, and each email step is recorded before the next run.
One edge case: if the process dies in the middle of pushing a single lead to Twenty, the next
run pushes that lead again, which can leave a duplicate company or contact in the CRM.

```text
openprospect run (agency track)                       openprospect jobs daily (job track)
─────────────────────────────────                     ───────────────────────────────────
 1  replies   ← IMAP                                    find   ← 7 job boards → candidates.json
 2  send      → Listmonk (leads ready earlier)          write  ← Claude Code  → drafts.json
 3  scrape    ← Google Maps (Docker)                    send   → SMTP         → sent.csv
 4  remote    ← remoteintech/remote-jobs (git)
 5  enrich    ← each lead's website (+ Firecrawl)
 6  verify    ← DNS MX + Reacher
 7  score     (local)
 8  crm       → Twenty
 9  intent    ← Huginn → Twenty
10  send      → Listmonk (new leads, rest of limit)
11  export    → data/exports/all_leads.csv
```

`apps/cli/src/openprospect/cli/pipeline.py` runs each step inside `step()`, which logs and
swallows exceptions so one failing service never stops the others. `data/run.lock` holds the PID
of the running job so a scheduled run never overlaps a manual one.

## Packages and boundaries

| Package | Owns | May depend on |
| --- | --- | --- |
| [`core`](../packages/core/README.md) | Workspace paths, `.env`, `settings.yaml`, the SQLite store, text + HTTP helpers | nothing in the repo |
| [`crm`](../packages/crm/README.md) | Twenty REST client and lead sync | core |
| [`sources`](../packages/sources/README.md) | Google Maps, remote companies, Reddit buyer intent | core, crm |
| [`enrich`](../packages/enrich/README.md) | Website reader, signals, pain points | core |
| [`verify`](../packages/verify/README.md) | MX, Reacher, chain detection | core |
| [`scoring`](../packages/scoring/README.md) | Score, tiers, first lines and subjects | core |
| [`mail`](../packages/mail/README.md) | Listmonk sequences, IMAP replies, plain SMTP | core, crm |
| [`jobs`](../packages/jobs/README.md) | The job & freelance track | core, mail, verify |
| [`apps/cli`](../apps/cli/README.md) | Commands, the daily pipeline, doctor / stats / export, daemon | everything |

The rules (also in [CONTRIBUTING.md](../CONTRIBUTING.md)):

- `core` depends on nothing else in the repo.
- Only `apps/cli` wires steps together. Packages expose functions that take a database
  connection (`enrich(conn)`, `verify(conn)`, …). They never call another package's pipeline step.
- Dependencies point one way. `jobs` may use `mail` and `verify`, never the reverse.
- Each package mostly reads its own section of `settings.yaml`. Where a step needs shared facts it
  reads other sections too: `mail` reads `agency`, `verify.sendable_statuses` and
  `scoring.min_tier_to_email`; `crm` reads `scoring.deal_value` and `agency`; `jobs` falls back
  to `agency.sender_name`.

## Why a uv workspace with namespace packages

- **One lockfile, one virtualenv.** `uv sync` installs every package in editable mode, and
  `uv run` always uses the same environment. There's no per-package install dance.
- **Real package boundaries.** Each package has its own `pyproject.toml` that declares exactly
  which other packages it uses. Unwanted imports are visible in review, and a package can be
  published on its own later.
- **One import namespace.** Every package installs into `openprospect.*` (a PEP 420 namespace,
  with no `openprospect/__init__.py`), so code reads `from openprospect.core import db` and
  `from openprospect.crm import Twenty` wherever it lives.
- **One entry point.** Users only ever install and run `openprospect`, the CLI app, which
  depends on all the packages.

## Data: what lives where

Everything OpenProspect writes is under `data/` in the workspace (git-ignored), plus the Docker
volumes of the services.

| Path | What |
| --- | --- |
| `data/leads.db` | The SQLite lead store: the pipeline's memory |
| `data/raw/gmaps_<time>.csv` | Raw Google Maps results and the searches that produced them |
| `data/cache/remote-jobs/` | The cloned remote-companies list |
| `data/exports/` | CSV exports (`all_leads.csv` is refreshed every run) |
| `data/logs/` | One log per `run` / `jobs` invocation |
| `data/jobs/daily/<day>/` | `candidates.json` (found) and `drafts.json` (written) |
| `data/jobs/seen_postings.json`, `data/jobs/sent.csv` | Job-track memory: postings already handled, every send attempt |
| `data/run.lock` | Present only while a run is in progress |

### SQLite tables (`packages/core/src/openprospect/core/db.py`)

| Table | Purpose |
| --- | --- |
| `leads` | One row per lead: source, contact details, website signals (JSON), pain points, chosen email + status, score, tier, first line, sequence step, CRM ids, timestamps of every step |
| `sends` | One row per email: lead, step, Listmonk list/campaign, state (`queued` → `sent` / `cancelled`), delivery time |
| `done_queries` | Google Maps searches already scraped |
| `suppression` | Addresses and `@domains` never to email again (opt-outs, bounces) |
| `kv` | Small state: the Listmonk template id, IMAP message ids already read |

Every step selects only the rows it hasn't processed yet (for example `enriched_at IS NULL`).
That's what makes each step safe to re-run.

## The lead lifecycle

```text
            scrape / remote / intent
                      │
                      ▼
   new ──enrich──► enriched ──verify──► verified ──score──► scored ──crm──► in CRM (deal: NEW)
    │                                                          │
    │                                       send (step 1) ─────┘
    ▼
 emailing ── step 2 after 3 days ── step 3 after 5 more days ── (sequence ends)
    │
    ├── reply ─────────► replied        follow-ups stop, deal → SCREENING, reply added as a note
    ├── "no thanks" ───► unsubscribed   suppressed forever, blocklisted in Listmonk
    └── bounce ────────► bounced        suppressed forever, blocklisted in Listmonk
```

The `stage` column holds `new`, `emailing`, `replied`, `unsubscribed`, `bounced`, or `intent`
(Reddit posts: CRM-only, never emailed). Enriched / verified / scored are timestamps
(`enriched_at`, `verified_at`, `scored_at`), not stages. In the CRM you take it from there:
SCREENING → MEETING → PROPOSAL → CUSTOMER.

## The services

All defined in [`infra/docker-compose.yml`](../infra/docker-compose.yml) and started with `openprospect up`.

| Service | Image | Port | Used by |
| --- | --- | --- | --- |
| Twenty (server, worker, Postgres, Redis) | `twentycrm/twenty` | 3740 | `crm`, `sources.buyer_intent`, `mail.replies` |
| Listmonk (+ Postgres) | `listmonk/listmonk` | 3741 | `mail` |
| Reacher | `reacherhq/backend` | 3742 | `verify` |
| Huginn | `ghcr.io/huginn/huginn` | 3743 | `sources.buyer_intent` |
| Firecrawl *(profile `firecrawl`)* | `ghcr.io/firecrawl/firecrawl` | 3744 | `enrich` (optional) |
| Maps scraper web UI *(profile `mapsui`)* | `gosom/google-maps-scraper` | 3745 | you, by hand (`import-csv`) |
| OpenProspect runner *(profile `runner`)* | built from `apps/cli/Dockerfile` | — | runs `openprospect daemon` on servers |

The Google Maps scraper itself isn't a long-running service. `sources.google_maps` starts it
with `docker run --rm` for each batch of searches.

## Extending OpenProspect

### Add a lead source

1. Create `packages/sources/src/openprospect/sources/<name>.py` with a function
   `import_<name>(conn) -> int` that builds lead dicts and calls `db.upsert_lead(conn, lead)`.
   Give each lead a stable, unique `source_id` (for example `"<name>:<their id>"`) and
   `source="<name>"`, and fill whatever you know (`name`, `website`, `domain`, `country`, `emails`, …).
2. Add a settings section for it in `config/settings.example.yaml` if it needs options.
3. Add a step in `apps/cli/.../pipeline.py` (before *Enrich*) and a command in `main.py`.
   Enrich, verify, score, CRM and send then work for your leads with no further changes.
4. Add tests in `packages/sources/tests/` that use no network.

### Add a pain point

1. Detect the signal in `packages/enrich/src/openprospect/enrich/signals.py` (it must be
   visible to any visitor: **passive checks only**, no probing).
2. Turn it into a pain point in `enrich/pains.py`.
3. Give it a weight in `scoring/model.py` (`PAIN_WEIGHT`), and a first line, subject and
   problem phrase in `scoring/copy.py` (`ICEBREAKERS`, `SUBJECTS`, `PROBLEM_TEXT`).
4. Add an `offers:` sentence for it in `config/settings.example.yaml`.

### Add a job board

1. Write a fetcher in `packages/jobs/src/openprospect/jobs/boards.py` that returns postings
   built with `_posting(...)` (source, id, company, title, url, location, posted date, text).
2. Add it to the `BOARDS` list. Filtering, contact harvesting, writing and sending need no changes.
3. Only use public APIs or feeds that allow this use, and add a test with a recorded sample response.
