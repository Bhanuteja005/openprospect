# openprospect-crm

Keeps [Twenty CRM](https://github.com/twentyhq/twenty) in step with the pipeline.

Part of the [OpenProspect](../../README.md) monorepo. Import it as `openprospect.crm`.

| Module | Responsibility |
| --- | --- |
| `twenty.py` | REST client, rate-limit aware (100 calls/min: spaced calls, retries on 429 and timeouts) |
| `sync.py` | company + contact + deal (`<Business> - Tier A (82)`, estimated value) + insight note per lead; `set_stage()` on replies |

**Depends on:** core

**Settings:** `scoring.deal_value`, `agency.currency`, `agency.phone_country`
