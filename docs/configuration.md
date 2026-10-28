# Configuration

OpenProspect reads four files from your **workspace**. That's the folder you run it from (the
cloned repo), or the folder in the `OPENPROSPECT_HOME` environment variable.

| File | Created by | Holds |
| --- | --- | --- |
| `config/settings.yaml` | `init`, from `config/settings.example.yaml` | Everything about *how* it prospects and sends |
| `config/queries.txt` | `init`, from `config/queries.example.txt` | Your Google Maps searches |
| `config/profile.md` | `init`, from `config/profile.example.md` | Your persona for the job track's AI writer |
| `.env` | `init` (random passwords) | Service URLs, passwords, inbox credentials, API keys |

All four are git-ignored, so your details never end up in a commit. `init` never overwrites
an existing file. After editing `settings.yaml`, the next command picks it up; `daemon` reloads
it on every check. To apply new scoring or offer wording to leads that were already scored, run
`openprospect score --all`.

- [settings.yaml](#settingsyaml)
  - [agency](#agency) · [offers](#offers) · [scrape](#scrape) · [remote_companies](#remote_companies) · [enrich](#enrich) · [verify](#verify) · [scoring](#scoring) · [sending](#sending) · [intent](#intent) · [ai](#ai) · [schedule](#schedule) · [jobs](#jobs)
- [queries.txt](#queriestxt)
- [Email templates](#email-templates)
- [.env](#env)

## settings.yaml

### `agency`

Who you are. These values fill the `[[…]]` placeholders in `templates/emails/*.html`.

| Key | Default | Meaning |
| --- | --- | --- |
| `name` | `""` | Your agency / studio / brand (`[[AGENCY_NAME]]`) |
| `sender_name` | `""` | The name emails come from (`[[SENDER_NAME]]`, and the *From* name). `doctor` flags it while empty |
| `intro` | `""` | The sentence after the personal first line of email 1 (`[[SENDER_INTRO]]`), e.g. `"I'm Alex, a web developer."`. `doctor` flags it while empty |
| `website` | `""` | Your site. Shown as plain text, not a link, which helps inbox placement (`[[AGENCY_WEBSITE_TEXT]]`) |
| `postal_address` | `""` | **Required.** Nothing is sent until it's set; every email carries it in the footer (CAN-SPAM in the US, and expected in most countries) |
| `calendar_link` | `""` | Optional booking link (`[[CALENDAR_LINE]]`) |
| `currency` | `"USD"` | Currency of deal values in the CRM |
| `phone_country` / `phone_calling_code` | `"US"` / `"+1"` | Fallback country for local phone numbers sent to the CRM |

### `offers`

One sentence per pain point, saying what you'd do about it. Email 1 is:
*personal first line* → `intro` → the offer for the lead's biggest problem → a small ask. The
keys are the pain points the enrich step can find:

`no_website`, `site_down`, `bad_ssl`, `no_https`, `ssl_expiring`, `old_tls`,
`outdated_wordpress`, `old_php`, `old_jquery`, `no_https_redirect`, `mixed_content`,
`not_mobile`, `slow_site`, `outdated_site`, `no_booking`, `no_analytics`, `low_rating`, and
`default` (used when nothing specific was found).

`no_analytics` counts toward the score but is never claimed in an email, because a page can't prove it reliably.

### `scrape`

Google Maps scraping with [gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper), started in Docker on demand.

| Key | Default | Meaning |
| --- | --- | --- |
| `image` | `gosom/google-maps-scraper` | Docker image. Pin a tag for reproducible runs |
| `depth` | `2` | How far to scroll each search: 1 ≈ 20 results, 10 ≈ 120+ |
| `concurrency` | `1` | Parallel browser jobs. Keep it low on small machines |
| `extract_emails` | `true` | Also visit each website for emails |
| `language` | `"en"` | Google Maps language |
| `exit_on_inactivity` | `"3m"` | Stop when nothing new arrives for this long |
| `max_queries_per_run` | `15` | Searches per run (about an hour). The rest wait for the next run |
| `auto_queries.enabled` | `true` | When `queries.txt` runs out, generate *niche in city* searches |
| `auto_queries.weights` | `{ US: 2 }` | Picks per country per round (others get 1) |
| `auto_queries.niches` | 25 high-value niches | Business types to search |
| `auto_queries.cities` | US / GB / AU lists | `COUNTRY: [cities]`. Add your own countries |

### `remote_companies`

B2B leads from [remoteintech/remote-jobs](https://github.com/remoteintech/remote-jobs), cloned into `data/cache/remote-jobs` on first use.

| Key | Default | Meaning |
| --- | --- | --- |
| `company_sizes` | `["tiny", "small"]` | Only these sizes. Add `"medium"` for more |
| `technologies_any` | `[]` | Only companies using any of these (e.g. `["wordpress", "shopify"]`). Empty = all |
| `limit_per_run` | `50` | New companies per run |

### `enrich`

| Key | Default | Meaning |
| --- | --- | --- |
| `max_pages_per_site` | `4` | Homepage + up to 3 contact / about / team pages |
| `timeout_seconds` | `15` | Per page |
| `slow_site_seconds` | `4.0` | Slower than this (measured twice, best kept) ⇒ `slow_site` |
| `outdated_year_before` | `2023` | Copyright year older than this ⇒ `outdated_site` |
| `per_run_limit` | `700` | Leads read per run |

### `verify`

| Key | Default | Meaning |
| --- | --- | --- |
| `sendable_statuses` | `["safe", "site_mx_ok"]` | Which results may receive email. `safe` = Reacher confirmed the inbox; `risky` = catch-all or full inbox; `site_mx_ok` = published on the business's own site and its domain has a mail server (the fallback when port 25 is blocked) |
| `guess_role_emails` | `true` | Try `info@` / `contact@` / `hello@` / `office@` when none was found. Kept only if Reacher says `safe` |
| `per_run_limit` | `200` | Leads verified per run |
| `skip_chains` | sample list | Name fragments of big chains: kept in the CRM, never emailed. Any website shared by 3+ listings is also treated as a chain |

### `scoring`

The score (0–100) adds up: category (0–25), demand from review count (0–20), reputation from
rating (0–10), price level (0–10), budget signals (0–10), opportunity from pain points (0–20),
and reachability (0–5).

| Key | Default | Meaning |
| --- | --- | --- |
| `category_points` | ~60 keywords | Keyword in the Google category ⇒ points. The highest match wins |
| `default_category_points` | `8` | When no keyword matches |
| `tiers` | `A: 70`, `B: 50` | Score thresholds. Below B is C |
| `deal_value` | `A: 1500`, `B: 800`, `C: 300` | Estimated deal size per tier, shown in the CRM |
| `min_tier_to_email` | `"C"` | `"A"` = email only the best, `"B"` = A+B, `"C"` = everyone with a valid email |

### `sending`

The agency sequence, sent through Listmonk.

| Key | Default | Meaning |
| --- | --- | --- |
| `daily_limit` | `20` | Emails per inbox per day (follow-ups included). A sensible ramp is ~20 in week 1, ~35 in week 2, ~50 after that |
| `country_priority` | `["US", "GB", "AU", "NZ", "IE"]` | New-lead slots go to these countries first, in order. Follow-ups always go first. Canada is left out on purpose: CASL generally requires consent (see [Responsible use](responsible-use.md)) |
| `max_new_per_day_by_country` | `{}` | Per-country daily caps for new leads, e.g. `{ DE: 3 }` |
| `skip_sources` | `[]` | Optional list of sources never emailed by the sequence, e.g. `["remote_companies"]` |
| `warmup_start_date` | `""` | The day a new inbox started. Sending starts at `warmup_first_day` and adds `warmup_add_per_day` each day until `daily_limit` |
| `warmup_first_day` / `warmup_add_per_day` | `15` / `5` | The warm-up ramp |
| `followup_after_days` | `[3, 5]` | Email 2 three days after email 1, email 3 five days after email 2 |
| `local_send_hours` | `[9, 16]` | Weekdays, between these hours **in the lead's own time zone** |
| `default_timezone` | `"UTC"` | When a lead's time zone can't be worked out |
| `auto_send` | `false` | `false`: campaigns are created as drafts for you to review and start. `true`: they're scheduled automatically |
| `templates` | 3 steps | Subject + HTML file per step. Step 1's subject is per business (`{{ .Subscriber.Attribs.subject }}`) |

Listmonk itself is set (by `setup`) to send at most **20 emails per hour**, one at a time, and
each campaign carries a `List-Unsubscribe` mailto header.

### `intent`

| Key | Default | Meaning |
| --- | --- | --- |
| `huginn_feed_url` | `""` | The JSON feed of Huginn's *Buyer intent feed* agent. `openprospect setup` fills it in |

The Reddit feeds and keywords live in Huginn (http://localhost:3743) and in
`infra/huginn/buyer-intent-scenario.json`.

### `ai`

Optional free local AI for the first line of each email, through [Ollama](https://ollama.com).

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `false` | `true` = ask the local model, fall back to templates if it fails |
| `ollama_url` | `http://localhost:11434` | Your Ollama server |
| `model` | `llama3.2` | Run `ollama pull llama3.2` first |

### `schedule`

Used by `openprospect daemon` (and the `runner` container). The times are in the machine's local time zone; inside the `runner` container that is `TZ` from `.env` (UTC unless you change it). Quoted (`"06:00"`) or unquoted both work.

| Key | Default | Meaning |
| --- | --- | --- |
| `agency_time` | `"06:00"` | When `openprospect run` starts. Empty = off |
| `jobs_time` | `"13:00"` | When `openprospect jobs daily` starts. Empty = off |

### `jobs`

The job & freelance track. See [Job track](job-track.md) for the full picture.

| Key | Default | Meaning |
| --- | --- | --- |
| `sender_name` | `""` | *From* name. Empty = `agency.sender_name`; `jobs send` refuses to send while both are empty |
| `max_age_days` | `3` | Only postings this fresh |
| `recontact_days` | `90` | Never email the same company twice within this window |
| `max_companies_per_day` | `30` | Upper bound on companies passed to the writer. This track has no warm-up, so keep it at 20–30 on a new inbox |
| `roles` | developer roles | Regular-expression fragments for titles you want (case-insensitive) |
| `exclude_roles` | sales, design, devops, … | Titles to skip even when a role matches |
| `stack` | web / AI keywords | Each match in a posting raises its fit score (best fits are written first) |
| `open_to` | `worldwide`, `anywhere`, … | Location words meaning *you may apply*. **Add your country / region / time zone** (e.g. `india`, `apac`, `latam`, `europe`) |
| `blocked_regions` | US, EU, UK, … | Region words that exclude you unless an `open_to` word is also present. **Remove the ones you live in** |
| `writer.command` | `"claude"` | The agent CLI that writes `drafts.json` |
| `writer.allowed_tools` | `Read`, `Glob`, `Grep`, `WebFetch`, `WebSearch`, `Write(data/jobs/**)` | Tools the writer may use. It reads untrusted web pages, so it may only write inside `data/jobs/`. Don't add `Edit`, `Bash` or `Agent` |
| `writer.timeout_minutes` | `60` | The writer is stopped if it runs longer than this |

## queries.txt

One Google Maps search per line. Lines starting with `#` are comments.

```text
# niche + area works best
med spa in Scottsdale AZ
personal injury lawyer in Leeds UK
```

Each line is scraped once (`scrape --all` re-runs every line). High-value niches score higher
automatically through `scoring.category_points`.

## Email templates

`templates/emails/email_1_intro.html`, `email_2_followup.html` and `email_3_breakup.html` hold the
three emails. They use two kinds of placeholder:

- `[[SENDER_NAME]]`, `[[SENDER_INTRO]]`, `[[AGENCY_NAME]]`, `[[AGENCY_WEBSITE]]`,
  `[[AGENCY_WEBSITE_TEXT]]`, `[[POSTAL_ADDRESS]]`, `[[CALENDAR_LINE]]` are filled from `agency:`.
- `{{ .Subscriber.Attribs.first_line }}`, `.offer`, `.short`, `.business`, `.problem`, `.city`,
  `.category`, `.rating`, `.reviews`, `.website`, `.tier`, `.score` are filled per recipient by Listmonk.

Keep the emails short and plain. Fewer links and no images means better inbox placement.

## .env

`init` creates `.env` with random passwords. [`.env.example`](../.env.example) documents
every key. A real environment variable always wins over `.env`.

| Key | Meaning |
| --- | --- |
| `TWENTY_URL`, `LISTMONK_URL`, `REACHER_URL`, `HUGINN_URL`, `FIRECRAWL_URL` | Where the services are, as seen from the machine running the CLI (defaults `http://localhost:3740`–`3744`) |
| `TWENTY_API_KEY` | Twenty → Settings → APIs & Webhooks → Create API key (turn on **Advanced mode** in Settings if you don't see it) |
| `LISTMONK_API_USER`, `LISTMONK_API_TOKEN` | Created for you by `setup` (user `openprospect-api`) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL` | The agency track's sending inbox. Port 465 = SSL, 587 = STARTTLS |
| `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD` | Reply / bounce detection. User and password fall back to `SMTP_*` |
| `IMAP2_HOST`, `IMAP2_USER`, `IMAP2_PASSWORD` | Optional older inbox, so replies to mail sent from it are still caught |
| `JOB_SMTP_HOST`, `JOB_SMTP_PORT`, `JOB_SMTP_USER`, `JOB_SMTP_PASSWORD` | The job track's inbox (falls back to `SMTP_*`). A separate inbox is recommended |
| `REACHER_HELLO_NAME`, `REACHER_FROM_EMAIL` | The identity Reacher uses when talking to mail servers: a domain you send from |
| `TZ` | Time zone of Listmonk and of the `runner` container, so it also sets when `openprospect daemon` starts each track there (default `UTC`) |
| `LISTMONK_ADMIN_USER`, `LISTMONK_ADMIN_PASSWORD`, `LISTMONK_DB_PASSWORD` | Generated by `init` |
| `TWENTY_DB_PASSWORD`, `TWENTY_ENCRYPTION_KEY` | Generated by `init`. **Don't change them after Twenty's first start** |
| `HUGINN_USERNAME`, `HUGINN_PASSWORD` | Generated by `init` |
| `HUGINN_FEED_SECRET` | Generated by `init`: the random secret in your buyer-intent feed URL. Keep it private |
| `BIND_ADDRESS` | Optional. The address service ports are published on (default `127.0.0.1`, this machine only). `0.0.0.0` exposes them to the network: only behind a firewall or a reverse proxy with auth |
| `TWENTY_PORT`, `LISTMONK_PORT`, `REACHER_PORT`, `HUGINN_PORT`, `FIRECRAWL_PORT`, `MAPS_UI_PORT` | Optional host ports (defaults 3740–3745). If you change one, change the matching `*_URL` too |
| `TWENTY_TAG`, `LISTMONK_TAG`, `REACHER_TAG`, `HUGINN_TAG`, `FIRECRAWL_TAG`, `MAPS_SCRAPER_TAG` | Optional Docker image tags (default `latest`). Pin them for production |
| `TWENTY_SERVER_URL`, `HUGINN_DOMAIN`, `HUGINN_TIMEZONE` | Optional, for servers with a public domain (see [Deployment](deployment.md)) |
| `OPENPROSPECT_HOST_DATA_DIR` | Only for the `runner` container: the host's absolute path to `data/` |
| `OPENPROSPECT_HOME` | Optional: run the CLI against a workspace other than the current folder |
