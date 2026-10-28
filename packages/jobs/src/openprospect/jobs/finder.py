"""The find step: today's fresh openings that fit you, plus who to email at each company.

Writes data/jobs/daily/<day>/candidates.json for the writing step (writer.py), which writes
drafts.json next to it for the sender (sender.py). Postings already seen and companies
emailed in the last `recontact_days` are skipped."""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from openprospect.core.config import paths, settings
from openprospect.core.http import session
from openprospect.core.log import log
from openprospect.core.text import FREE_MAIL

from .boards import BOARDS
from .filters import fit_score, geo_ok, role_ok
from .harvest import company_domain, harvest


def jobs_settings() -> dict:
    try:
        return settings().get("jobs") or {}
    except FileNotFoundError:
        return {}


def jobs_dir() -> Path:
    return paths.data / "jobs"


def day_dir(day: str) -> Path:
    return jobs_dir() / "daily" / day


def seen_file() -> Path:
    return jobs_dir() / "seen_postings.json"


def sent_file() -> Path:
    return jobs_dir() / "sent.csv"


def contacted_domains() -> set[str]:
    """Company domains emailed (successfully) within the re-contact window."""
    out = set()
    f = sent_file()
    if f.exists():
        days = int(jobs_settings().get("recontact_days", 90))
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with f.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("result") != "sent":
                    continue
                try:
                    when = datetime.fromisoformat(r["time"])
                except (KeyError, ValueError):
                    when = datetime.now(UTC)
                if when >= cutoff:
                    dom = r["to"].split("@")[-1].lower()
                    if dom not in FREE_MAIL:  # one gmail.com recipient must not block every other one
                        out.add(dom)
    return out


def find(day: str | None = None, limit: int | None = None) -> int:
    """Collect today's candidates. Returns how many companies need the writing step."""
    cfg = jobs_settings()
    day = day or date.today().isoformat()
    limit = limit or int(cfg.get("max_companies_per_day", 80))
    max_age = int(cfg.get("max_age_days", 3))
    recontact = int(cfg.get("recontact_days", 90))
    out_dir = day_dir(day)
    out_dir.mkdir(parents=True, exist_ok=True)
    cand_file = out_dir / "candidates.json"
    if cand_file.exists():  # a re-run the same day must not wipe today's list
        n = len(json.loads(cand_file.read_text(encoding="utf-8")))
        log(f"  {day} already collected ({n} companies); keeping it")
        return n
    s = session()
    seen = set(json.loads(seen_file().read_text(encoding="utf-8"))) if seen_file().exists() else set()
    done = contacted_domains()
    cutoff = (date.today() - timedelta(days=max_age)).isoformat()

    raw = []
    for name, fn in BOARDS:
        got = fn(s, max_age)
        log(f"  {name}: {len(got)} postings")
        raw += got

    picked, companies = [], set()
    for p in raw:
        if p["id"] in seen or (p["source"] != "hn" and p["posted"] and p["posted"] < cutoff):
            continue
        if not role_ok(p["title"], p["text"]) or not geo_ok(p["location"], p["text"], p["source"] == "hn"):
            continue
        key = p["company"].lower()
        if not key or key in companies:
            continue
        p["domain"] = company_domain(p)
        if p["domain"] and p["domain"] in done:
            continue
        p["fit"] = fit_score(f"{p['title']} {p['text']}") + (3 if p["source"] == "hn" else 0)
        companies.add(key)
        picked.append(p)
    picked.sort(key=lambda p: p["fit"], reverse=True)
    picked = picked[:limit]
    log(f"  {len(picked)} new companies fit (role + location + not contacted in {recontact} days)")

    for i, p in enumerate(picked, 1):
        p["contacts"] = harvest(s, p)
        if i % 10 == 0:
            log(f"  looked for people at {i}/{len(picked)}")
    with_contact = sum(1 for p in picked if p["contacts"])
    cand_file.write_text(json.dumps(picked, indent=1, ensure_ascii=False), encoding="utf-8")
    seen_file().write_text(json.dumps(sorted(seen | {p["id"] for p in picked})), encoding="utf-8")
    log(f"  {with_contact} already have a usable address; the rest go to the writing step")
    log(f"  wrote {cand_file}")
    return len(picked)
