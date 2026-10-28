"""A tiny scheduler for servers and containers: runs the agency track and the job track once a
day at the times in settings.yaml (`schedule:`), in the machine's local time zone.

On a desktop, the OS scheduler is simpler: scripts/schedule-cron.sh or scripts/schedule-windows.ps1."""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime

from openprospect.core.config import reload_settings, settings
from openprospect.core.log import log, warn


def parse_time(value) -> tuple[int, int] | None:
    """'06:00' -> (6, 0). Unquoted 06:00 in YAML arrives as the integer 360 (minutes)."""
    if value is None or value == "" or value is False:
        return None
    if isinstance(value, int):
        return divmod(value, 60)
    h, _, m = str(value).strip().partition(":")
    return int(h), int(m or 0)


def _due(hhmm, last_day: str | None, now: datetime) -> bool:
    t = parse_time(hhmm)
    if t is None:
        return False
    h, m = t
    return last_day != now.date().isoformat() and (now.hour, now.minute) >= (h, m)


def run_forever(poll_seconds: int = 30) -> None:
    last: dict[str, str | None] = {"agency": None, "jobs": None}
    # Don't fire for times that already passed before the daemon started.
    now = datetime.now()
    sched = settings().get("schedule", {})
    for track, key in (("agency", "agency_time"), ("jobs", "jobs_time")):
        if _due(sched.get(key), None, now):
            last[track] = now.date().isoformat()
    log(f"daemon: agency track at {sched.get('agency_time') or 'off'}, job track at {sched.get('jobs_time') or 'off'}")
    while True:
        reload_settings()  # pick up edits to settings.yaml without a restart
        sched = settings().get("schedule", {})
        now = datetime.now()
        for track, key, cmd in (("agency", "agency_time", ["run"]), ("jobs", "jobs_time", ["jobs", "daily"])):
            if _due(sched.get(key), last[track], now):
                last[track] = now.date().isoformat()
                log(f"\ndaemon: starting the {track} track ({now:%Y-%m-%d %H:%M})")
                # a separate process, so a crash or memory leak in one run never kills the daemon
                code = subprocess.run([sys.executable, "-m", "openprospect.cli", *cmd]).returncode
                if code:
                    warn(f"daemon: {track} track exited with code {code}")
        time.sleep(poll_seconds)
