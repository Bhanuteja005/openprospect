# The OpenProspect CLI in a container, for running the daily jobs on a server.
# Built by the `runner` profile in infra/docker-compose.yml (context = repo root):
#   docker compose -f infra/docker-compose.yml --env-file .env --profile runner up -d --build
#
# The repo is mounted at /workspace at runtime, so config/, templates/ and data/ are the host's.
# The Docker CLI is included so the pipeline can start the Google Maps scraper on the host's
# Docker daemon through the mounted /var/run/docker.sock.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl gnupg tzdata \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Install into /opt/openprospect so the /workspace mount doesn't hide the virtualenv.
WORKDIR /opt/openprospect
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8
COPY . .
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

ENV PATH="/opt/venv/bin:$PATH" \
    OPENPROSPECT_HOME=/workspace
WORKDIR /workspace

ENTRYPOINT []
CMD ["openprospect", "daemon"]
