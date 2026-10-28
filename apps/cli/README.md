# openprospect (CLI)

The `openprospect` command: the only thing users run. It wires the packages in `packages/`
into two daily tracks and a handful of setup commands.

| Module | Responsibility |
| --- | --- |
| `main.py` | argument parsing and command dispatch |
| `pipeline.py` | the agency track (`openprospect run`): every step isolated, one run at a time, logged to `data/logs/` |
| `report.py` | `doctor`, `stats`, `export` |
| `services.py` | `up` / `down`: Docker Compose for `infra/docker-compose.yml` |
| `daemon.py` | `daemon`: a tiny daily scheduler for servers and containers |
| `Dockerfile` | the image used by the `runner` Compose profile |

Run `openprospect --help` for every command. See the [root README](../../README.md).
