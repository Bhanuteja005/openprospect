#!/usr/bin/env bash
# First-time setup on Linux / macOS. Run from anywhere:  bash scripts/install.sh
#
#   1. checks Docker and uv
#   2. installs the Python workspace (uv sync)
#   3. creates .env (random passwords) and config/ from the examples
#   4. starts the services (first time downloads ~6 GB)
#   5. connects them (Listmonk API user + sending limits, Huginn scenario) and runs a health check
set -euo pipefail

cd "$(dirname "$0")/.."

say() { printf '\033[36m%s\033[0m\n' "$*"; }
die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

say "1/5 Checking Docker and uv..."
command -v docker >/dev/null 2>&1 || die "Docker is not installed: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start it and run this again."
command -v uv >/dev/null 2>&1 || die "uv is not installed: curl -LsSf https://astral.sh/uv/install.sh | sh"

say "2/5 Installing OpenProspect (uv sync)..."
uv sync

say "3/5 Creating .env and config/ (existing files are kept)..."
uv run openprospect init

say "4/5 Starting services (first time can take 10+ minutes)..."
uv run openprospect up

twenty_port="$(grep -E '^TWENTY_PORT=' .env 2>/dev/null | cut -d= -f2 || true)"
twenty_port="${twenty_port:-3740}"
say "   waiting for the CRM (http://localhost:${twenty_port}) to finish its first start..."
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:${twenty_port}/healthz" >/dev/null 2>&1; then break; fi
  sleep 5
done

say "5/5 Connecting the pieces (Listmonk API user, sending limits, Huginn scenario)..."
uv run openprospect setup
uv run openprospect doctor

printf '\n\033[32mDone.\033[0m Next: edit config/settings.yaml, add your inbox + Twenty API key to .env\n'
printf 'and see docs/getting-started.md. Then:  uv run openprospect run\n'
