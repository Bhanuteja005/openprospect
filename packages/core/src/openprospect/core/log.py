"""Plain console output. The CLI tees it into data/logs/ for scheduled runs."""

from __future__ import annotations


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"[!] {msg}", flush=True)
