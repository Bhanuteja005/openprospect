# openprospect-core

The foundation every other package builds on. No network calls, no business logic.

Part of the [OpenProspect](../../README.md) monorepo. Import it as `openprospect.core`.

| Module | Responsibility |
| --- | --- |
| `config.py` | `paths` (workspace folders, resolved from `OPENPROSPECT_HOME` or the current directory), `env()` (real env > `.env` > default), `settings()` (config/settings.yaml), `init_workspace()` |
| `db.py` | the SQLite lead store at `data/leads.db`: `connect`, `upsert_lead`, `update`, suppression list, key-value store |
| `text.py` | URL/domain normalising, email extraction + ranking, business-name shortening for subjects |
| `http.py` | a browser-like `requests` session and `is_up()` |
| `log.py` | `log()` / `warn()` |

**Depends on:** nothing (only third-party: requests, PyYAML)

**Settings:** —
