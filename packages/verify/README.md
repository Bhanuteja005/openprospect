# openprospect-verify

Nothing is emailed until an address passes here. Bounces are the #1 reason new inboxes get blocked.

Part of the [OpenProspect](../../README.md) monorepo. Import it as `openprospect.verify`.

| Module | Responsibility |
| --- | --- |
| `mx.py` | free checks: disposable domains, MX / A records |
| `reacher.py` | mailbox checks with [Reacher](https://github.com/reacherhq/check-if-email-exists); falls back to *found on the business's own site + MX* when port 25 is blocked |
| `pipeline.py` | the `verify` step: best sendable address per lead, big chains skipped |

**Depends on:** core

**Settings:** `verify:`
