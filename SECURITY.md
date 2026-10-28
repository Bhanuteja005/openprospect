# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Report them privately with GitHub's
private vulnerability reporting: open the repository's **Security** tab and choose
**Report a vulnerability**. Include what you found, how to reproduce it, and what an attacker could
do with it.

You can expect an acknowledgement within a few days. Once a fix is ready we publish an advisory and
credit you, unless you'd rather stay anonymous.

## Supported versions

Only the latest release on the `main` branch receives security fixes.

## Scope

In scope:

- the `openprospect` CLI and the packages in this repository
- the Docker Compose setup in `infra/` (exposed ports, default credentials, secrets handling)
- anything that could leak secrets, lead data or email content, or send email the user didn't intend

Out of scope (report these upstream): vulnerabilities in Twenty, Listmonk, Reacher, Huginn,
Firecrawl or the Google Maps scraper themselves.

## Handling secrets

- Secrets live in `.env`, which is git-ignored. `openprospect init` generates random database and
  admin passwords; never commit `.env` or paste it into an issue.
- Use app passwords for SMTP / IMAP, never your main account password.
- `data/` holds your lead database and scraped data. Treat it as personal data and keep it private.

## Network exposure

- Every service port in `infra/docker-compose.yml` is published on `127.0.0.1` only, through
  `BIND_ADDRESS` in `.env`. Setting `BIND_ADDRESS=0.0.0.0` exposes them to the network. Only do
  that behind a firewall, a VPN, or a reverse proxy with authentication.
- **Reacher has no authentication.** Anyone who can reach it can make your server probe mail servers
  for them. Never expose it.
- **Twenty's sign-up page is open.** After you create your own account, keep the CRM private or put
  it behind a proxy with authentication.

## Known limitations

- `openprospect setup` creates the Listmonk API user with Listmonk's admin role, because the
  pipeline manages lists, campaigns, templates and settings. Treat `LISTMONK_API_TOKEN` like an
  admin password, and rotate it in Listmonk (Users) if it ever leaks.
- The job track's AI writer (`openprospect jobs write`) reads untrusted job posts and web pages. Its
  tools are therefore limited (`jobs.writer.allowed_tools`): it can read and research, and it can
  only write inside `data/jobs/`. The send step re-checks every recipient in code, including that
  the address was actually published. Don't widen those tools.
- The Huginn feed URL contains a random per-install secret (`HUGINN_FEED_SECRET` in `.env`). Keep
  it private.
