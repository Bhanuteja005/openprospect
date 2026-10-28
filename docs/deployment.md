# Deployment

OpenProspect runs well on a laptop that's on every morning. If you want it running 24/7 with
nothing to remember, put it on a small server. This page covers both.

- [Choosing where to run it](#choosing-where-to-run-it)
- [Scheduling](#scheduling)
- [Server setup with the runner container](#server-setup-with-the-runner-container)
- [Ports, domains and reverse proxies](#ports-domains-and-reverse-proxies)
- [Backups](#backups)
- [Updating](#updating)

## Choosing where to run it

| | Your computer | A VPS |
| --- | --- | --- |
| Cost | Free | A few dollars to ~$20/month |
| Needs | Docker Desktop running at the scheduled time | Nothing after setup |
| Sizing | 4 GB free for Docker (8 GB+ with Firecrawl) | 2 vCPU / 4 GB minimum; **4 vCPU / 8 GB recommended** (16 GB with Firecrawl); 40 GB disk |
| Port 25 (Reacher deep checks) | Usually blocked by ISPs | Often blocked too, some providers unblock on request |

The services (Twenty, Listmonk, Reacher, Huginn) use about 2 GB together. During a run, the
Google Maps scraper starts a headless browser, which adds 1–2 GB.

## Scheduling

Pick **one** of these:

| Option | Command | Best for |
| --- | --- | --- |
| cron | `bash scripts/schedule-cron.sh --install` (`AGENCY_TIME=06:00 JOBS_TIME=13:00` to change times) | Linux / macOS, CLI installed with uv |
| Task Scheduler | `powershell -ExecutionPolicy Bypass -File scripts\schedule-windows.ps1 -AgencyTime 06:00 -JobsTime 13:00` (`-NoJobs` to skip the job track) | Windows |
| `openprospect daemon` | Times in `settings.yaml` → `schedule:` | Servers, containers, anything with a process supervisor |

All three run `openprospect run` (agency track) and `openprospect jobs daily` (job track), and
write logs to `data/logs/`. The agency track (`openprospect run`) takes a lock
(`data/run.lock`): if the previous run is still going, the new one exits. The job track has no
lock, but each step skips work already done (candidates already collected, drafts already
written, addresses already emailed).

`daemon` uses the machine's local time zone (inside the `runner` container that is `TZ` from
`.env`, UTC unless you change it), reloads `settings.yaml` on every check, and
runs each track in a separate process, so a failed run never stops the daemon.

## Server setup with the runner container

With the `runner` Compose profile, the CLI runs in a container next to the services. You
don't need Python or uv on the server, only Docker and Git.

```bash
# 1. Get the code (the folder below is an example; any absolute path works)
sudo mkdir -p /srv && cd /srv
git clone https://github.com/Bhanuteja005/openprospect && cd openprospect

# 2. Create .env and config/ (one-off container, nothing installed on the host).
docker compose -f infra/docker-compose.yml --env-file .env --profile runner run --rm openprospect openprospect init

# 3. Edit your settings and inbox
nano config/settings.yaml config/queries.txt .env

# 4. Tell the runner where data/ is on the HOST (required, see below)
echo "OPENPROSPECT_HOST_DATA_DIR=/srv/openprospect/data" >> .env

# 5. Start everything, the daily scheduler included
docker compose -f infra/docker-compose.yml --env-file .env --profile runner up -d

# 6. One-time setup, then a health check
docker compose -f infra/docker-compose.yml --env-file .env --profile runner exec openprospect openprospect setup
docker compose -f infra/docker-compose.yml --env-file .env --profile runner exec openprospect openprospect doctor
```

**Why `OPENPROSPECT_HOST_DATA_DIR`?** The runner starts the Google Maps scraper through the host's
Docker (the mounted `/var/run/docker.sock`). The scraper writes its results into a folder
mounted from the host, so OpenProspect has to pass the host's path, not the container's.
Without it, the scraper writes to a path the host can't see and every scrape returns nothing.

Inside the runner, the service URLs point at the Compose services (`http://twenty-server:3000`,
`http://listmonk:9000`, …). That's set in `infra/docker-compose.yml`, so the `localhost` URLs in
`.env` stay correct for running commands on the host.

Run any command inside the runner with:

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile runner exec openprospect openprospect stats
```

> The runner mounts the Docker socket, which gives it control of the host's Docker. Keep the
> server single-purpose, or run it as a dedicated user.

**The job track in a container:** `jobs write` needs the Claude Code CLI, which isn't in the
runner image. Either run `jobs write` on a machine that has it (the files are plain JSON in
`data/jobs/`), extend the Dockerfile to install it, or set `schedule.jobs_time: ""` and run the
job track elsewhere.

## Ports, domains and reverse proxies

| Service | Host port | Variable | Expose publicly? |
| --- | --- | --- | --- |
| Twenty CRM | 3740 | `TWENTY_PORT` | Yes, if you want the CRM in your browser from anywhere (behind HTTPS) |
| Listmonk | 3741 | `LISTMONK_PORT` | Optional (admin UI). Keep it private or behind auth |
| Reacher | 3742 | `REACHER_PORT` | **No.** It's an API without auth |
| Huginn | 3743 | `HUGINN_PORT` | Optional (admin UI) |
| Firecrawl | 3744 | `FIRECRAWL_PORT` | **No** |
| Maps scraper UI | 3745 | `MAPS_UI_PORT` | **No** |

Compose publishes these ports on `127.0.0.1` only (`BIND_ADDRESS` in `.env`), so they are not
reachable from the internet by default. The simplest way to use the web UIs from your laptop is
an SSH tunnel: `ssh -L 3740:localhost:3740 -L 3741:localhost:3741 you@server`. If you need them
public, put the ones you want behind a reverse proxy with HTTPS and authentication (Caddy, nginx,
Traefik) on the same machine. Setting `BIND_ADDRESS=0.0.0.0` exposes every port directly. Only do
that behind a firewall (for example `ufw default deny incoming`, then allow SSH and 443), and never
let Reacher be reachable from outside.

Pin image versions for a production server: set `TWENTY_TAG`, `LISTMONK_TAG`, `REACHER_TAG`,
`HUGINN_TAG`, `FIRECRAWL_TAG` and `MAPS_SCRAPER_TAG` in `.env` (all default to `latest`).

When Twenty is served on a domain, set its public URL in `.env` before the first start, then
recreate the container:

```env
TWENTY_SERVER_URL=https://crm.example.com
HUGINN_DOMAIN=intent.example.com
```

## Backups

Everything worth keeping:

| What | Where | How |
| --- | --- | --- |
| Lead store, logs, job-track files | `data/` | Copy the folder (stop runs first, or use `sqlite3 data/leads.db ".backup leads.bak"`) |
| Your settings | `config/settings.yaml`, `config/queries.txt`, `config/profile.md`, `templates/`, `.env` | Copy. `.env` holds secrets, so store it encrypted |
| CRM data | Docker volume `openprospect_twenty-db-data` | `docker compose -f infra/docker-compose.yml --env-file .env exec twenty-db pg_dumpall -U postgres > twenty.sql` |
| Listmonk data | Docker volume `openprospect_listmonk-db-data` | `docker compose -f infra/docker-compose.yml --env-file .env exec listmonk-db pg_dumpall -U listmonk > listmonk.sql` |
| Huginn data | Docker volume `openprospect_huginn-mysql` | Export the scenario from the Huginn UI, or back up the volume |

Keep `TWENTY_ENCRYPTION_KEY` with your backups. Twenty needs it to read its own data.

## Updating

```bash
git pull
uv sync                                    # or rebuild the runner: --profile runner up -d --build
uv run openprospect up                     # pulls nothing new by itself; to update service images:
docker compose -f infra/docker-compose.yml --env-file .env pull && uv run openprospect up
```

Check [CHANGELOG.md](../CHANGELOG.md) before updating. Service images use `latest` tags by
default. Pin them in `infra/docker-compose.yml` (and `scrape.image`) if you want updates only
when you choose.
