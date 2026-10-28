# openprospect-sources

Where leads come from.

Part of the [OpenProspect](../../README.md) monorepo. Import it as `openprospect.sources`.

| Module | Responsibility |
| --- | --- |
| `google_maps.py` | runs [gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper) in Docker for new searches in `config/queries.txt`, then auto-generated *niche in city* searches; loads the CSV into the lead store |
| `remote_companies.py` | ~900 remote-friendly companies from [remoteintech/remote-jobs](https://github.com/remoteintech/remote-jobs), cloned into `data/cache/` |
| `buyer_intent.py` | imports the Reddit buyer-intent scenario into [Huginn](https://github.com/huginn/huginn) and turns new posts into `INTENT:` deals in the CRM |

**Depends on:** core, crm

**Settings:** `scrape:`, `remote_companies:`, `intent:`
