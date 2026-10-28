"""The write step: an AI agent researches each company and writes one email per company.

Runs Claude Code headless (https://claude.com/claude-code) with prompts/job-outreach.md. It
reads candidates.json, your persona in config/profile.md and the rules in
prompts/cold-email-guide.md, and writes drafts.json. It never sends anything itself.

Any other agent CLI can be used (settings.yaml `jobs.writer.command`), or you can write
drafts.json by hand: a JSON array of
  {"id","company","title","url","status":"send"|"skip","skip_reason","to","recipient_name",
   "recipient_role","recipient_kind":"person"|"hiring"|"hello"|"generic","evidence_url",
   "from_posting":bool,"subject","body"}"""

from __future__ import annotations

import shutil
import subprocess
import threading
from datetime import date

from openprospect.core.config import paths
from openprospect.core.log import log, warn

from .finder import day_dir, jobs_settings

# The writer reads untrusted job posts and web pages, so it can read and research, but it may only
# create files under data/jobs/ - never .env, config/, scripts/ or code. Anything not listed is denied.
DEFAULT_TOOLS = ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "Write(data/jobs/**)"]


def write(day: str | None = None) -> bool:
    """True when drafts.json exists afterwards."""
    day = day or date.today().isoformat()
    folder = day_dir(day)
    if not (folder / "candidates.json").exists():
        warn(f"no candidates for {day}: run `openprospect jobs find` first")
        return False
    if (folder / "drafts.json").exists():
        log(f"  {day} already has drafts.json; keeping it")
        return True
    prompt_file = paths.prompts / "job-outreach.md"
    if not prompt_file.exists():
        warn(f"{prompt_file} is missing")
        return False
    cfg = jobs_settings().get("writer") or {}
    cmd = str(cfg.get("command") or "claude")
    exe = shutil.which(cmd)
    if not exe:
        warn(
            f"'{cmd}' not found. Install Claude Code (https://claude.com/claude-code), set "
            f"jobs.writer.command in settings.yaml, or write {folder / 'drafts.json'} yourself "
            "(schema in prompts/job-outreach.md)."
        )
        return False
    rel = folder.relative_to(paths.home).as_posix()
    prompt = prompt_file.read_text(encoding="utf-8").replace("{DAY}", day).replace("{DATA_DIR}", rel)
    tools = [str(t) for t in (cfg.get("allowed_tools") or DEFAULT_TOOLS)]
    log(f"  writing emails with {cmd} (this can take a while)...")
    timeout = float(cfg.get("timeout_minutes") or 60) * 60
    proc = subprocess.Popen(
        [exe, "-p", "--allowedTools", *tools],
        cwd=paths.home,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    watchdog = threading.Timer(timeout, proc.kill)  # never let a stuck writer hang the daily run
    watchdog.start()
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
        for line in proc.stdout:
            log("  " + line.rstrip())
        proc.wait()
    finally:
        watchdog.cancel()
    if proc.returncode != 0:
        warn(f"{cmd} exited with code {proc.returncode}")
    ok = (folder / "drafts.json").exists()
    if not ok:
        warn(f"no drafts.json was written for {day}")
    return ok
