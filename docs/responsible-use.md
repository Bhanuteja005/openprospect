# Responsible use

OpenProspect sends real email to real people. Used carelessly, cold email can break the law, get
your domain blacklisted, and annoy the people you want as clients. This page covers the rules that
apply most often, and the safeguards built into the tool.

> **This is not legal advice.** Laws differ by country and change over time. If you send at
> volume, or into a market you don't know, check the rules there or ask a lawyer.

## The law, in short

### United States: CAN-SPAM

Cold email to businesses is legal in the US if you follow CAN-SPAM:

- **A valid physical postal address** in every email. Set `agency.postal_address` in
  `config/settings.yaml`; until you do, OpenProspect sends nothing at all (to any country).
- **A clear way to opt out**, honoured promptly. All three templates end with a P.S. saying
  "reply no and I won't email again", and each campaign carries a `List-Unsubscribe` header.
- **Honest headers and subjects:** your real name and address in "From", no misleading subjects.

### EU and UK: GDPR and PECR

- Email **business** addresses only, about something relevant to that business. B2B outreach can
  rely on *legitimate interest* under GDPR, but you must be able to justify it and you must honour
  objections immediately.
- Under UK PECR, corporate addresses (e.g. `info@company.co.uk`) can be emailed without prior
  consent; sole traders and some partnerships are treated like individuals and need consent.
- Tell people where you got their address if they ask, and delete their data on request.
- Several EU countries (e.g. Germany) are much stricter about unsolicited B2B email. Consider
  removing them from `scrape.auto_queries.cities` unless you know the local rules.

### Canada: CASL

CASL generally requires consent, with a narrow exception for addresses that are **conspicuously
published** by the business, without a "no unsolicited email" statement, where your message is
relevant to their role. Be cautious; penalties are high.
That's why Canada is not in the default `sending.country_priority`, and the default auto-searches
don't include Canadian cities.

### Other countries

Australia (Spam Act), and many others, have their own rules. When in doubt, don't send there.

## Platforms

- **Google Maps:** automated scraping is against Google's Terms of Service. The defaults keep
  volumes modest (a limited number of searches per run, low concurrency). Don't run the scraper
  continuously, and don't resell the data.
- **Reddit:** OpenProspect only *finds* posts where people ask to hire help and puts them in your
  CRM. Reply to them yourself. Automated replies break Reddit's rules and get accounts banned.
- **Job boards:** the job track reads public APIs and RSS feeds. Respect each board's terms, and
  don't hammer them; the default is one run a day.

## Deliverability basics

Getting blocked is the most common way cold email fails. To protect your sending reputation:

- **Use a separate domain or inbox** for cold email, never your main business domain.
- **Warm up new inboxes.** Set `sending.warmup_start_date`; OpenProspect starts at
  `warmup_first_day` emails a day and adds `warmup_add_per_day` until it reaches `daily_limit`.
- **Keep daily limits low:** about 20/day in week 1, 35 in week 2, 50 after that, per inbox.
  Listmonk is also configured to send at most 20 an hour.
- **Keep bounces near zero.** Only verified addresses are emailed (see below).
- **Write like a person.** Plain HTML, few links, short emails, one ask.
- Set up SPF, DKIM and DMARC for your sending domain (your email provider has a guide).

## Built-in safeguards

| Safeguard | What it does |
|-----------|--------------|
| Drafts by default | `auto_send: false` creates campaigns as drafts; nothing goes out until you press Start in Listmonk. |
| Verified addresses only | An address must be confirmed by Reacher, or published on the business's own website with a working mail server. Guessed role addresses are only kept if Reacher proves they exist. |
| Suppression list | Opt-outs and bounces are suppressed forever, by address, and blocklisted in Listmonk. |
| Opt-out detection | Replies like "unsubscribe", "not interested" or "remove me" stop the sequence permanently. |
| Reply detection | Any reply stops follow-ups for that lead, including follow-ups already scheduled in Listmonk, and moves the CRM deal to SCREENING. |
| Bounce handling | Bounce notices are read from your inbox and the address is never emailed again. |
| Business-hours sending | With `auto_send` on, emails are scheduled for weekday working hours in the lead's time zone (US leads: Eastern or Central). Drafts go out when you press Start. |
| Chain skipping | Big chains and any website shared by 3+ listings are kept in the CRM but never emailed. |
| One email per inbox | Branches that share an inbox are emailed once. |
| Postal address check | Nothing is sent until you set `agency.postal_address`; every email carries it. |
| Job track rules | Only published addresses of named HR / founders / hiring inboxes, then general company inboxes; never support@, billing@, noreply@ and similar; never guessed addresses (each address must be one the scraper found or appear on the page the writer cites, checked at send time); one email per company per 90 days. |
| Truthful copy | First lines are built only from facts a normal visitor can see on the lead's site or listing. Website checks are passive: no probing, no hidden paths. |

## Please don't

- Email consumers / private individuals.
- Buy or import lists of addresses and blast them.
- Remove the opt-out line or the postal address from the templates.
- Raise the limits on a fresh inbox to "go faster".
- Use OpenProspect for anything deceptive, harassing or illegal.
