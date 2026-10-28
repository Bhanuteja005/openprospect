# openprospect-enrich

Reads each lead's website like a normal visitor and records what a freelancer or agency could fix.

Part of the [OpenProspect](../../README.md) monorepo. Import it as `openprospect.enrich`.

| Module | Responsibility |
| --- | --- |
| `reader.py` | fetches pages directly, through [Firecrawl](https://github.com/firecrawl/firecrawl) when it is running and a site needs JavaScript |
| `signals.py` | emails, socials, site builder, analytics / ad pixels, booking, chat, copyright year, passive security findings |
| `pains.py` | signals → pain points (`no_website`, `bad_ssl`, `slow_site`, `outdated_wordpress`, …) |
| `pipeline.py` | the `enrich` step |

**Depends on:** core

**Settings:** `enrich:`
