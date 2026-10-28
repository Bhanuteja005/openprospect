# Getting started

This guide takes you from nothing to your first emails going out. It takes about 30 minutes,
most of it spent waiting for Docker images to download.

- [1. Install the prerequisites](#1-install-the-prerequisites)
- [2. Install OpenProspect](#2-install-openprospect)
- [3. Tell it who you are](#3-tell-it-who-you-are)
- [4. Choose what to scrape](#4-choose-what-to-scrape)
- [5. Connect your sending inbox](#5-connect-your-sending-inbox)
- [6. Connect the CRM](#6-connect-the-crm)
- [7. Check everything](#7-check-everything)
- [8. First run (drafts only)](#8-first-run-drafts-only)
- [9. Go automatic](#9-go-automatic)

## 1. Install the prerequisites

| Tool | Why | Install |
| --- | --- | --- |
| Docker | Runs the CRM, email sender, verifier and scraper | [Docker Desktop](https://docs.docker.com/get-docker/) (Windows/macOS) or Docker Engine (Linux) |
| uv | Installs and runs the Python workspace | `curl -LsSf https://astral.sh/uv/install.sh \| sh` or `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| Git | Clones the repo, updates the remote-companies list | [git-scm.com](https://git-scm.com/downloads) |

Give Docker at least **4 GB of memory**. The core services use about 2 GB, and the Maps scraper's
browser needs some headroom. Firecrawl is optional and needs about 4 GB more (see
[Troubleshooting](troubleshooting.md#docker-runs-out-of-memory--firecrawl)).

uv installs a suitable Python (3.11+) for you if you don't have one.

## 2. Install OpenProspect

```bash
git clone https://github.com/Bhanuteja005/openprospect
cd openprospect
```

**The quick way:** one script does everything in this step.

```bash
bash scripts/install.sh                                         # Linux / macOS
powershell -ExecutionPolicy Bypass -File scripts\install.ps1    # Windows
```

**Step by step**, if you'd rather see each part:

```bash
uv sync                       # install every package into .venv
uv run openprospect init      # create .env (random passwords) and config/ from the examples
uv run openprospect up        # start the services; the first start downloads ~6 GB
uv run openprospect setup     # create the Listmonk API user, set a safe sending speed, import the Huginn scenario
```

After `up`, these run on your machine:

| Service | URL | Login |
| --- | --- | --- |
| Twenty CRM | http://localhost:3740 | you create the account (step 6) |
| Listmonk (email sender) | http://localhost:3741/admin | `admin` / `LISTMONK_ADMIN_PASSWORD` from `.env` |
| Reacher (email checker) | http://localhost:3742 | none (an API) |
| Huginn (Reddit watcher) | http://localhost:3743 | `admin` / `HUGINN_PASSWORD` from `.env` |

Twenty can take a few minutes to finish its first start. If `setup` can't reach a service,
wait a minute and run it again. Every OpenProspect command is safe to repeat.

> All commands in this guide are written as `uv run openprospect …`. If you activate the
> virtualenv (`source .venv/bin/activate` or `.venv\Scripts\activate`), plain `openprospect …` works too.

## 3. Tell it who you are

Open `config/settings.yaml` (created by `init`, git-ignored) and fill in the `agency:` block.
The values below are an example; use your own:

```yaml
agency:
  name: "Rivera Studio"
  sender_name: "Alex Rivera"
  intro: "I'm Alex, a web developer."
  website: "https://yourstudio.com"
  postal_address: "123 Main St, Suite 4, Austin, TX 78701, USA"
```

- **`postal_address` is required.** US law (CAN-SPAM) requires it in every commercial email, and
  it's expected almost everywhere else. Nothing is sent until you set it, and `doctor` flags it.
- `sender_name` and `intro` start empty. `doctor` flags them until you fill them in.
- `intro` is the sentence after the personal first line of email 1. Then `offers:` adds one
  sentence per problem found. Rewrite those in your own words, and keep them true to what you
  actually do.

Every other setting has a safe default. They're all explained in [Configuration](configuration.md).

## 4. Choose what to scrape

Open `config/queries.txt` and write one Google Maps search per line, as niche + area:

```text
dentist in Austin TX
roofing contractor in Denver CO
family law attorney in Manchester UK
```

Each line is scraped once and remembered. When the file runs out, `scrape.auto_queries`
generates *niche in city* searches from the lists in `settings.yaml`, so the pipeline never
stalls. Each run does at most `scrape.max_queries_per_run` searches (15 by default, about an hour).

## 5. Connect your sending inbox

Listmonk sends through a normal inbox: Gmail, Google Workspace, Zoho or any SMTP server.

> **Use a separate domain for cold email** if you can (about $10/year), for example
> `alex@tryriverastudio.com` instead of `alex@riverastudio.com`. If something goes wrong,
> your main domain's reputation is never at risk. A free Gmail is fine for testing.

**Gmail / Google Workspace:**

1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an app password at https://myaccount.google.com/apppasswords and copy the 16 letters.
3. Open `.env` and fill in:

   ```env
   SMTP_USER=you@yourdomain.com
   SMTP_PASSWORD=abcdabcdabcdabcd
   FROM_EMAIL=you@yourdomain.com
   IMAP_USER=you@yourdomain.com
   IMAP_PASSWORD=abcdabcdabcdabcd
   ```

**Zoho:** `SMTP_HOST=smtp.zoho.com` and `IMAP_HOST=imap.zoho.com` (or the `.eu` / `.in` host of
your region). **Other providers:** use their SMTP and IMAP hosts; port 465 (SSL) and 587
(STARTTLS) both work.

Then push the inbox into Listmonk:

```bash
uv run openprospect setup
```

IMAP is how OpenProspect notices replies, opt-outs and bounces. Leave it filled in.

## 6. Connect the CRM

1. Open http://localhost:3740 and sign up. The account only exists on your machine.
2. In Twenty, go to **Settings → APIs & Webhooks → Create API key** and copy it. If you don't see
   *APIs & Webhooks*, turn on **Advanced mode** at the bottom of the Settings menu first.
3. In `.env`, set `TWENTY_API_KEY=` to that key.

## 7. Check everything

```bash
uv run openprospect doctor
```

Every line should say `OK`, with three exceptions that are fine:

- **Firecrawl** is optional. Without it the built-in website reader is used.
- **Claude Code on PATH** only matters for the job track's writer (`jobs write`). Ignore it if you
  only use the agency track.
- **Outbound port 25** is blocked on most home and many cloud networks. OpenProspect then uses
  a free fallback check (see the [FAQ](../README.md#faq)).

## 8. First run (drafts only)

```bash
uv run openprospect run
```

This runs all 11 steps of the daily job (see [How it works](../README.md#how-it-works)). The
first run takes the longest, because scraping and reading hundreds of websites takes time.
The output is also saved to `data/logs/run_<date>_<time>.log`.

Because `sending.auto_send` is `false` by default, emails are **not sent yet**. They are
created as **draft campaigns** in Listmonk:

1. Open http://localhost:3741/admin/campaigns.
2. Open a campaign and click **Preview**. Read a few emails as the recipient would see them.
3. If you're happy, press **Start**. If not, edit `templates/emails/*.html` or `offers:` in
   `settings.yaml`, delete the drafts, and run `uv run openprospect score --all` and then
   `uv run openprospect send`.

Then look at the results:

```bash
uv run openprospect stats            # totals + top 10 leads
uv run openprospect export           # everything to data/exports/leads_<time>.csv
```

In Twenty, open **Opportunities** and switch to the Kanban view. Every lead is a deal named
`<Business> - Tier A (82)`, with an estimated value and a note explaining the score.

## 9. Go automatic

When you trust what it sends:

1. In `config/settings.yaml`, set `sending.auto_send: true`. Campaigns then start on their own,
   scheduled into each lead's business hours (US leads: Eastern or Central time).
2. If this is a new inbox, set `sending.warmup_start_date` to today. Sending then starts at
   `warmup_first_day` emails and grows by `warmup_add_per_day` until it reaches `daily_limit`.
3. Schedule the daily run:

   ```bash
   bash scripts/schedule-cron.sh --install                                                 # Linux / macOS
   powershell -ExecutionPolicy Bypass -File scripts\schedule-windows.ps1 -AgencyTime 06:00  # Windows
   ```

   Your computer must be on and Docker running at that time. For a machine that's always on,
   see [Deployment](deployment.md).

From now on you only need [15 minutes a day](../README.md#your-15-minutes-a-day).

**Want to find work instead of (or as well as) clients?** Continue with the [Job track](job-track.md).
