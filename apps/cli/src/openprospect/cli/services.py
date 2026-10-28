"""Start and stop the self-hosted services (infra/docker-compose.yml) without leaving the CLI."""

from __future__ import annotations

import shutil
import subprocess

from openprospect.core.config import env, paths
from openprospect.core.log import log, warn

URLS = [
    ("Twenty CRM", "TWENTY_URL", ""),
    ("Listmonk", "LISTMONK_URL", "/admin"),
    ("Huginn", "HUGINN_URL", ""),
    ("Reacher", "REACHER_URL", ""),
]


def compose(*args: str) -> int:
    if not shutil.which("docker"):
        warn("Docker is not installed or not on PATH: https://docs.docker.com/get-docker/")
        return 1
    cmd = ["docker", "compose", "-f", str(paths.infra / "docker-compose.yml"), "--env-file", str(paths.env_file), *args]
    return subprocess.run(cmd, cwd=paths.home).returncode


def up(firecrawl: bool = False) -> int:
    profiles = ["--profile", "firecrawl"] if firecrawl else []
    code = compose(*profiles, "up", "-d")
    if code == 0:
        log("\nServices are starting (the first start downloads ~6 GB and can take 10+ minutes):")
        for name, key, suffix in URLS:
            log(f"  {name:<11} {env(key)}{suffix}")
        if firecrawl:
            log(f"  {'Firecrawl':<11} {env('FIRECRAWL_URL')}")
    return code


def down() -> int:
    return compose("--profile", "firecrawl", "--profile", "mapsui", "--profile", "runner", "down")
