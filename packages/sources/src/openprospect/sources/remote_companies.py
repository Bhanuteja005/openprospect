"""Remote-friendly companies from remoteintech/remote-jobs (https://github.com/remoteintech/remote-jobs).

Turns its ~900 company profiles into B2B leads. These companies already work with remote
people, so they are used to outside help. The list is cloned into data/cache/ on first use
and updated on every run. Most profiles have no email; the enrich + verify steps find one."""

from __future__ import annotations

import subprocess

import yaml

from openprospect.core import db
from openprospect.core.config import paths, settings
from openprospect.core.log import log, warn
from openprospect.core.text import domain_of, normalize_url

REPO_URL = "https://github.com/remoteintech/remote-jobs"
SOURCE = "remote_companies"


def repo_dir():
    return paths.data / "cache" / "remote-jobs"


def update_repo() -> bool:
    """Clone the list the first time, fast-forward it after that. False if git failed."""
    repo = repo_dir()
    if (repo / ".git").exists():
        subprocess.run(["git", "-C", str(repo), "pull", "-q", "--ff-only"], check=False)
        return True
    repo.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(["git", "clone", "-q", "--depth", "1", REPO_URL, str(repo)], check=False).returncode == 0


def parse_profile(path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return None
    try:
        _, front, body = text.split("---", 2)
        meta = yaml.safe_load(front) or {}
    except (ValueError, yaml.YAMLError):
        return None
    blurb = ""
    if "## Company blurb" in body:
        blurb = body.split("## Company blurb", 1)[1].split("\n## ", 1)[0].strip()
    meta["blurb"] = blurb
    return meta


def import_companies(conn, limit: int | None = None) -> int:
    cfg = settings().get("remote_companies", {})
    limit = limit if limit is not None else int(cfg.get("limit_per_run", 50))
    sizes = {s.lower() for s in cfg.get("company_sizes") or []}
    techs = {t.lower() for t in cfg.get("technologies_any") or []}
    companies = repo_dir() / "src" / "companies"
    if not update_repo() or not companies.exists():
        warn(f"could not get the company list (needs git): {REPO_URL}")
        return 0
    known = {r["source_id"] for r in conn.execute("SELECT source_id FROM leads WHERE source = ?", (SOURCE,))}
    new = 0
    for path in sorted(companies.glob("*.md")):
        if new >= limit:
            break
        sid = f"remote:{path.stem}"
        if sid in known:
            continue
        meta = parse_profile(path)
        if not meta or not meta.get("website"):
            continue
        if sizes and str(meta.get("company_size", "")).lower() not in sizes:
            continue
        company_techs = {str(t).lower() for t in meta.get("technologies") or []}
        if techs and not (techs & company_techs):
            continue
        website = normalize_url(meta["website"])
        lead = {
            "source": SOURCE,
            "source_id": sid,
            "name": meta.get("title") or path.stem,
            "category": f"Remote company ({meta.get('company_size') or 'size n/a'})",
            "country": str(meta.get("region") or ""),
            "website": website,
            "domain": domain_of(website),
            "description": (meta.get("blurb") or "")[:1000],
            "signals": {
                "technologies": sorted(company_techs),
                "remote_policy": meta.get("remote_policy"),
                "company_size": meta.get("company_size"),
                "careers_url": meta.get("careers_url"),
            },
        }
        if db.upsert_lead(conn, lead):
            new += 1
    conn.commit()
    log(f"  remote companies: {new} new added")
    return new
