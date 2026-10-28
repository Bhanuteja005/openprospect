# Troubleshooting

Start with `uv run openprospect doctor`. It checks the workspace, every service, every
connection and port 25. Each run's full output is also in `data/logs/`.

- [A service is down](#a-service-is-down)
- [The scraper finds 0 results](#the-scraper-finds-0-results)
- [Emails don't go out](#emails-dont-go-out)
- [Port 25 is blocked](#port-25-is-blocked)
- [CRM sync: 429 / rate limited / timeouts](#crm-sync-429--rate-limited--timeouts)
- [Replies aren't detected](#replies-arent-detected)
- [Docker runs out of memory / Firecrawl](#docker-runs-out-of-memory--firecrawl)
- [Nothing is sent: postal address missing](#nothing-is-sent-postal-address-missing)
- [The job track refuses to send](#the-job-track-refuses-to-send)
- [The job track writes nothing](#the-job-track-writes-nothing)
- [Getting help](#getting-help)

## A service is down

```bash
uv run openprospect up                                                       # start (again)
docker compose -f infra/docker-compose.yml --env-file .env ps                # what's running
docker compose -f infra/docker-compose.yml --env-file .env logs -f twenty-server   # or listmonk, huginn, reacher
```

- **Twenty** takes a few minutes on its first start (database migrations). Wait until
  `http://localhost:3740/healthz` answers.
- **"port is already allocated"**: another program uses that port. Set `TWENTY_PORT` (etc.) in
  `.env`, and the matching `TWENTY_URL`.
- **Blank passwords / auth errors right after install**: Compose was started without your
  `.env`. Always use `openprospect up`, or pass `--env-file .env` when calling `docker compose` yourself.

## The scraper finds 0 results

- Google is throttling you. Lower `scrape.max_queries_per_run` and `scrape.depth`, and try again later.
- Check Docker is running and can pull `gosom/google-maps-scraper`.
- In the `runner` container: `OPENPROSPECT_HOST_DATA_DIR` must be the host's absolute path to
  `data/` (see [Deployment](deployment.md#server-setup-with-the-runner-container)).
- "no new searches": every line of `queries.txt` has been done and `scrape.auto_queries` is off.
  Add lines, turn auto queries on, or use `openprospect scrape --all`.

## Emails don't go out

Work down this list:

1. `sending.auto_send: false` (the default) creates **draft** campaigns. Open
   http://localhost:3741/admin/campaigns and press **Start**, or switch `auto_send` on.
2. With `auto_send: true`, campaigns are **scheduled** into each lead's business hours
   (`local_send_hours`, weekdays only), so nothing goes out at night or on weekends in their time zone.
3. "daily limit reached": the limit is shared by both send steps and includes follow-ups. Check
   `sending.daily_limit` and the warm-up (`warmup_start_date`).
4. "nobody is due an email today": no lead has a sendable email at your `min_tier_to_email`
   yet. Run `openprospect stats`.
5. SMTP itself: in Listmonk, go to **Settings → SMTP → Test connection**. For Gmail this is
   almost always the app password, or 2-Step Verification being off. After changing `.env`,
   run `openprospect setup` again.

## Port 25 is blocked

`doctor` shows `-- Outbound port 25`. This is normal on home internet and many cloud servers.
Reacher can't talk to mail servers, so OpenProspect uses its free fallback: an address counts as
sendable (`site_mx_ok`) only if it was published on the business's own website (or is a
personal free-mail address shown there) and the domain has a mail server. Guessed `info@`
addresses are skipped. Nothing to fix. If your server provider can unblock port 25, Reacher
deep checks switch on automatically.

## CRM sync: 429 / rate limited / timeouts

Twenty allows 100 API calls per minute per key. OpenProspect spaces its calls and waits and
retries on `429` and on timeouts. A busy or memory-starved Twenty can still time out. After 5
failures in a row the sync stops, and the remaining leads wait for the next run (they're never
lost). Run `openprospect crm` to continue, and give Docker more memory if it keeps happening.

## Replies aren't detected

- `IMAP_USER` / `IMAP_PASSWORD` must be set (they fall back to `SMTP_*`). For Gmail, enable IMAP
  in Gmail settings, and use the same app password.
- Only mail from people you emailed (or their domain), plus bounce notices, from the last 14 days is read.
- Moved to a new sending inbox? Put the old one in `IMAP2_*` so replies to it are still caught.

## Docker runs out of memory / Firecrawl

The core services need about 2 GB, and the scraper's browser needs 1–2 GB more during a run.
Firecrawl needs another ~4 GB.

**Docker Desktop on Windows (WSL 2):** create `%USERPROFILE%\.wslconfig` with

```ini
[wsl2]
memory=10GB
```

then run `wsl --shutdown` and restart Docker Desktop. **macOS:** Docker Desktop → Settings →
Resources → Memory.

Then `uv run openprospect up --firecrawl`. Without Firecrawl, the built-in reader handles most
small-business sites. Firecrawl only helps with JavaScript-only sites and sites that block
simple requests.

## Nothing is sent: postal address missing

US law (CAN-SPAM) requires a physical postal address in commercial email, and it's expected almost
everywhere else, so OpenProspect sends nothing until you set one. Set `agency.postal_address` in
`config/settings.yaml`; the waiting leads go out on the next send. `doctor` flags it while it's
empty.

## The job track refuses to send

- **No sender name:** set `jobs.sender_name` or `agency.sender_name` in `config/settings.yaml`.
- **Profile not filled in:** `config/profile.md` is missing or still the example. Replace it with your own.
- **"not verified as published":** the address isn't among the addresses `jobs find` collected for
  that posting, and doesn't appear on the draft's `evidence_url` page. This is the guard against
  guessed addresses; the draft is skipped on purpose.

## The job track writes nothing

- `'claude' not found`: install [Claude Code](https://claude.com/claude-code), sign in once by
  running `claude`, or set `jobs.writer.command` (see [Job track](job-track.md#without-claude-code)).
- `no candidates for <day>`: run `openprospect jobs find` first. If it finds 0 companies, your
  `roles` are too narrow or your location lists exclude everything (`open_to`, `blocked_regions`).
- `drafts.json` exists, so writing is skipped. Delete it to rewrite that day.
- The writer was stopped after `jobs.writer.timeout_minutes` (default 60). Lower
  `jobs.max_companies_per_day`, or raise the timeout.
- Nothing sent: try `openprospect jobs send --dry-run`. Skipped recipients and their reasons
  are in `data/jobs/sent.csv`.

## Getting help

Search the [issues](https://github.com/Bhanuteja005/openprospect/issues) first. When you open
a new one, include the output of `openprospect doctor` and the relevant part of
`data/logs/…`, **with emails, names and API keys removed**.
