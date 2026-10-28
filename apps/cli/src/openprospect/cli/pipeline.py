"""The daily agency run: every step in order, each one isolated so a failure in one step
never stops the rest. Only one run at a time (data/run.lock)."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime

from openprospect import crm, enrich, mail, scoring, verify
from openprospect.core.config import paths
from openprospect.core.log import log, warn
from openprospect.sources import buyer_intent, google_maps, remote_companies

from . import report


def step(name: str, fn, *args) -> None:
    log(f"\n== {name} ==")
    try:
        fn(*args)
    except Exception as e:  # keep the daily job going if one step fails
        warn(f"{name} failed: {e}")
        traceback.print_exc()


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import subprocess

        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def run_all(conn, with_remote: bool = True) -> None:
    lock = paths.data / "run.lock"
    if lock.exists():
        try:
            other = int(lock.read_text().strip())
        except ValueError:
            other = 0
        if other and _pid_alive(other):
            warn(f"another run is already in progress (process {other}); not starting a second one")
            return
    lock.write_text(str(os.getpid()))
    try:
        _run_steps(conn, with_remote)
    finally:
        lock.unlink(missing_ok=True)


def prep(conn) -> None:
    """Everything except scraping and sending: get leads ready for the next run."""
    for name, fn in (
        ("Enrich", enrich.enrich),
        ("Verify", verify.verify),
        ("Score", scoring.score),
        ("CRM", crm.sync),
        ("Buyer intent", buyer_intent.pull),
    ):
        step(name, fn, conn)


def _run_steps(conn, with_remote: bool) -> None:
    step("1. Replies, bounces, opt-outs", mail.check_replies, conn)
    # Send first (follow-ups + leads prepared yesterday) so emails always go out, even if
    # today's scraping runs long. The daily limit is shared with the second send below.
    step("2. Send emails (leads ready from earlier runs)", mail.send, conn)
    step("3. Google Maps", google_maps.scrape, conn)
    if with_remote:
        step("4. Remote-friendly companies", remote_companies.import_companies, conn)
    step("5. Enrich websites", enrich.enrich, conn)
    step("6. Verify emails", verify.verify, conn)
    step("7. Score leads", scoring.score, conn)
    step("8. Sync CRM", crm.sync, conn)
    step("9. Buyer intent", buyer_intent.pull, conn)
    step("10. Send emails (new leads, rest of the daily limit)", mail.send, conn)
    step("11. Export data/exports/all_leads.csv", report.export, conn, str(paths.data / "exports" / "all_leads.csv"))
    log("\n== Summary ==")
    report.stats(conn)


class Tee:
    """Mirror everything printed into a log file (data/logs/<name>_<stamp>.log)."""

    def __init__(self, name: str):
        logs = paths.data / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        self.path = logs / f"{name}_{datetime.now():%Y%m%d_%H%M}.log"
        self.file = self.path.open("a", encoding="utf-8")
        self.streams = (sys.stdout, sys.stderr)

    def __enter__(self):
        sys.stdout = _Both(self.streams[0], self.file)
        sys.stderr = _Both(self.streams[1], self.file)
        return self

    def __exit__(self, *exc):
        sys.stdout, sys.stderr = self.streams
        self.file.close()


class _Both:
    def __init__(self, a, b):
        self.a, self.b = a, b

    def write(self, text):
        self.a.write(text)
        self.b.write(text)
        return len(text)

    def flush(self):
        self.a.flush()
        self.b.flush()

    def __getattr__(self, name):
        return getattr(self.a, name)
