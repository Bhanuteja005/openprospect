# The job & freelance track

The agency track finds *clients*. This track finds *work*. Every day it collects fresh remote
and freelance openings that fit your skills and location, and finds the right person to email
at each company. An AI then writes each email individually from your own profile, and the
emails are sent safely, once.

```bash
uv run openprospect jobs daily          # find → write → send
```

- [Set it up](#set-it-up)
- [The three steps](#the-three-steps)
- [Who it will (and won't) email](#who-it-will-and-wont-email)
- [drafts.json](#draftsjson)
- [Without Claude Code](#without-claude-code)
- [Files it writes](#files-it-writes)

## Set it up

**1. Your profile.** `openprospect init` created `config/profile.md` from the example. Replace
everything in it: `jobs send` refuses to send while it is missing or still the example. The AI
writer reads it for every email:

- **Who I am:** one or two lines, your location and time zone (used to check that a posting is open to you)
- **Stack:** what you work with
- **Proof:** 3–5 things you built, each with a link and, if you have one, a real number. The writer picks the 1–2 that fit each company
- **Sign-off:** exactly how emails should end
- **Rules for the writer:** anything it must never do or claim

**2. Your filters.** In `config/settings.yaml`, the `jobs:` block (all keys are in
[Configuration](configuration.md#jobs)):

```yaml
jobs:
  sender_name: ""                                           # empty = agency.sender_name
  max_companies_per_day: 30                                 # no warm-up here: 20-30 on a new inbox
  roles: ["full[- ]?stack", "react", "python", ...]        # titles you want
  exclude_roles: ["sales", "designer", "devops", ...]      # titles you don't
  stack: ["react", "typescript", "postgres", ...]          # your skills, for the fit score
  open_to: ["worldwide", "anywhere", "global", "europe"]   # add your country / region / time zone
  blocked_regions: ["us", "usa", "canada", "uk", ...]      # remove the ones you live in
```

The two location lists matter most. A posting limited to "US only" or "CET time zone" is
skipped unless one of your `open_to` words also appears in it.

`jobs send` needs a From name: `jobs.sender_name`, or `agency.sender_name` when that is empty.
It refuses to send while both are empty.

This track has **no warm-up**: every draft that passes the checks goes out the same day. On a
fresh inbox keep `max_companies_per_day` at 20–30 (the example default is 30) and raise it slowly.

**3. A sending inbox.** In `.env`, set `JOB_SMTP_USER` and `JOB_SMTP_PASSWORD` (plus
`JOB_SMTP_HOST` / `JOB_SMTP_PORT` if it isn't Gmail). If they're empty, the agency inbox
(`SMTP_*`) is used. A separate inbox is better: job emails then never affect the reputation of
your client outreach.

**4. The AI writer.** Install [Claude Code](https://claude.com/claude-code) and sign in once
(`claude`). The `jobs write` step runs it headless. To use a different agent CLI, see
[Without Claude Code](#without-claude-code).

**5. Schedule it.** The daily schedule (`scripts/schedule-cron.sh`, `scripts/schedule-windows.ps1`,
or `openprospect daemon` with `schedule.jobs_time`) runs `openprospect jobs daily`.

## The three steps

Each step works on today's folder, `data/jobs/daily/<YYYY-MM-DD>/`. Add `--day YYYY-MM-DD` to
work on another day. Re-running a step never redoes finished work.

### `jobs find`

1. Reads Hacker News *Who is hiring?* and *Freelancer? Seeking freelancer?*, Remotive,
   Remote OK, Himalayas, We Work Remotely, Jobicy and Working Nomads.
2. Keeps postings that are at most `max_age_days` old, match your `roles` and not your
   `exclude_roles`, and are open to your location. Postings already seen on an earlier day are skipped.
   Hacker News is the exception to the age limit: its threads are monthly, so the whole current
   thread is read every day and `seen_postings.json` stops any comment being picked twice.
3. Takes one posting per company, drops companies emailed within `recontact_days`, sorts by fit
   (how many of your `stack` words appear), and keeps the best `max_companies_per_day`.
4. Looks for **published** addresses in the posting itself and on the company's own pages (`/about`,
   `/team`, `/careers`, `/contact`, …).
5. Writes `candidates.json`.

### `jobs write`

Runs the writer (`jobs.writer.command`, default `claude`) with
[`prompts/job-outreach.md`](../prompts/job-outreach.md). The writer reads your profile, the
writing guide in [`prompts/cold-email-guide.md`](../prompts/cold-email-guide.md) and
`candidates.json`. For each company it then:

- double-checks that the role is really open to you, and skips it otherwise
- picks one recipient under the rules below, researching the company's site if needed
- writes a 70–130 word email that names the exact role, says one specific true thing about
  the company, offers 1–2 proof items from your profile, and makes one small ask

It writes `drafts.json`. It never sends anything itself.

Job posts and web pages are untrusted text written by strangers, so the writer runs with limited
tools (`jobs.writer.allowed_tools`): `Read`, `Glob`, `Grep`, `WebFetch`, `WebSearch` and
`Write(data/jobs/**)`. It can research, but it can only write inside `data/jobs/`: it can't edit
your settings, `.env` or scripts. It is stopped after `jobs.writer.timeout_minutes` (default 60),
so a stuck run can never block the next day.

### `jobs send`

Sends every draft with `"status": "send"`, a few seconds apart. Before each one it **re-checks
everything**:

- the recipient rules below
- that the address was really **published**: it must be one of the addresses `jobs find` found
  for that posting (`contacts` in `candidates.json`), or appear on the page in the draft's
  `evidence_url`, which is fetched at send time. Otherwise the draft is skipped as
  "not verified as published"
- that the domain has a mail server
- that this address was never emailed, and the company wasn't emailed within `recontact_days`
- one email per company per run (two drafts for the same company domain: only the first goes)

Shared free-mail domains (Gmail etc.) count per address, not per domain, so one Gmail recipient
never blocks every other Gmail address. Every attempt is
logged to `data/jobs/sent.csv`. When the provider reports its daily limit, sending stops and the
rest wait for the next run.

```bash
uv run openprospect jobs send --dry-run    # list what would be sent, send nothing
```

## Who it will (and won't) email

One recipient per company, in this order:

1. **A named person** in a hiring role (HR, recruiter, talent, people, founder, CEO, CTO,
   director, head of engineering). Their address must be published, and tied to their name and
   title, with the page recorded as `evidence_url`. A personal Gmail-type address is allowed
   only when the poster wrote it in the job post itself.
2. **A hiring inbox** on the company's domain: `careers@`, `jobs@`, `hiring@`, `talent@`,
   `recruiting@`, `hr@`, `people@`, …
3. **`hello@`** on the company's domain.
4. **Another published company inbox** (`info@`, `contact@`, `team@`, …), as a last resort.

**Never:** `support@`, `help@`, `billing@`, `noreply@`, `privacy@`, `legal@`, `security@`,
`press@` and similar inboxes, and **never a guessed address**. The writer is told this, and
`jobs send` enforces it again in code: the inbox rules in
`packages/jobs/src/openprospect/jobs/recipients.py`, and the *published address* check described
under [`jobs send`](#jobs-send).

## drafts.json

A JSON array with one object per company:

```json
[
  {
    "id": "hn:41234567",
    "company": "Acme Analytics",
    "title": "Senior Full-Stack Engineer",
    "url": "https://news.ycombinator.com/item?id=41234567",
    "status": "send",
    "skip_reason": "",
    "to": "careers@acme-analytics.com",
    "recipient_name": "",
    "recipient_role": "",
    "recipient_kind": "hiring",
    "evidence_url": "https://acme-analytics.com/careers",
    "from_posting": false,
    "subject": "full-stack role at acme",
    "body": "Hi Acme team,\n\n..."
  }
]
```

| Field | Meaning |
| --- | --- |
| `status` | `"send"` or `"skip"` (with `skip_reason`) |
| `recipient_kind` | `"person"`, `"hiring"`, `"hello"` or `"generic"` |
| `recipient_role` | Required for `"person"`: their title (checked against the allowed roles) |
| `from_posting` | `true` if the address appeared in the job post itself |
| `evidence_url` | The public page where the address appears. **Required** for any address that isn't in the posting's `contacts`; `jobs send` fetches it and checks |
| `subject`, `body` | Plain text. The body is sent exactly as written |

## Without Claude Code

`jobs write` is the only step that needs an AI agent. You have three options:

- **Another agent CLI.** Set `jobs.writer.command` (and `allowed_tools`) in `settings.yaml`. It
  is called as `<command> -p --allowedTools …` (anything not listed is denied), with the prompt on
  stdin and the workspace as its working folder. Keep its write access limited to `data/jobs/`.
  Use a small wrapper script if your tool takes
  different flags.
- **By hand or with any chat AI.** Open `data/jobs/daily/<day>/candidates.json`, write
  `drafts.json` next to it in the format above, and run `uv run openprospect jobs send`.
- **Skip it.** Run `jobs find` only and use `candidates.json` as a daily list of companies hiring people like you.

## Files it writes

| Path | What |
| --- | --- |
| `data/jobs/daily/<day>/candidates.json` | Today's fitting postings with the addresses found |
| `data/jobs/daily/<day>/drafts.json` | The writer's output |
| `data/jobs/seen_postings.json` | Postings already handled, so they're never picked twice |
| `data/jobs/sent.csv` | Every send attempt (time, company, to, subject, result) |
| `data/logs/jobs_<time>.log` | The console output of each `jobs` command |
