"""The send step: send the individually written job/freelance emails in drafts.json.

Nothing the writer produced is trusted blindly. Every recipient must:
  - pass recipients.allowed_recipient (who may be emailed at all),
  - be published: found by the scraper for that posting, or present on the page in evidence_url,
  - have a mail server, and belong to a company not emailed within `recontact_days`
    (and only one email per company per batch).
Emails go out a few seconds apart from JOB_SMTP_* (or SMTP_*); sending stops when the provider
reports its daily limit. Every attempt is logged to data/jobs/sent.csv, so a re-run never emails
anyone twice. Nothing is sent until your sender name and config/profile.md are filled in."""

from __future__ import annotations

import csv
import json
import random
import smtplib
import time
from datetime import UTC, date, datetime

import requests

from openprospect.core.config import env, paths, settings
from openprospect.core.http import session
from openprospect.core.log import log, warn
from openprospect.core.text import FREE_MAIL
from openprospect.mail.smtp import SendingLimitReached, send_plain
from openprospect.verify.mx import has_mx

from .finder import contacted_domains, day_dir, jobs_settings, sent_file
from .recipients import allowed_recipient

FIELDS = ["time", "id", "company", "to", "subject", "result"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def already_sent() -> set[str]:
    f = sent_file()
    if not f.exists():
        return set()
    with f.open(encoding="utf-8") as fh:
        return {r["to"].lower() for r in csv.DictReader(fh) if r.get("result") == "sent"}


def log_row(it: dict, to: str, result: str) -> None:
    f = sent_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    new = not f.exists()
    with f.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(
            {
                "time": _now(),
                "id": it.get("id"),
                "company": it.get("company", ""),
                "to": to,
                "subject": it.get("subject", ""),
                "result": result,
            }
        )


def load(day: str) -> list[dict]:
    path = day_dir(day) / "drafts.json"
    if not path.exists():
        warn(f"no drafts for {day} ({path})")
        return []
    items = json.loads(path.read_text(encoding="utf-8"))
    return [i for i in items if i.get("status") == "send" and i.get("to") and i.get("body")]


def _sender_name() -> str:
    name = jobs_settings().get("sender_name")
    if name:
        return str(name)
    try:
        return str(settings().get("agency", {}).get("sender_name") or "")
    except FileNotFoundError:
        return ""


def not_ready() -> str:
    """Why sending must not start yet, or "" when it may."""
    if not _sender_name():
        return "set jobs.sender_name (or agency.sender_name) in config/settings.yaml"
    profile, example = paths.config / "profile.md", paths.config / "profile.example.md"
    if not profile.exists():
        return "write config/profile.md (start from config/profile.example.md)"
    if example.exists() and profile.read_text(encoding="utf-8").strip() == example.read_text(encoding="utf-8").strip():
        return "config/profile.md is still the example: replace it with your own story and proof"
    return ""


def published_contacts(day: str) -> dict[str, set[str]]:
    """posting id -> addresses the scraper found in the posting or on the company's own pages."""
    f = day_dir(day) / "candidates.json"
    if not f.exists():
        return {}
    return {
        str(c.get("id")): {x["email"].lower() for x in c.get("contacts") or [] if x.get("email")}
        for c in json.loads(f.read_text(encoding="utf-8"))
    }


def on_page(url: str, address: str, s: requests.Session) -> bool:
    """Is the address really written on the evidence page? (The writer must never guess one.)"""
    if not url.startswith(("http://", "https://")):
        return False
    try:
        r = s.get(url, timeout=20)
    except requests.RequestException:
        return False
    return r.status_code < 400 and address.lower() in r.text.lower()


def _password(host: str) -> str:
    pw = env("JOB_SMTP_PASSWORD") or env("SMTP_PASSWORD") or ""
    # Google shows app passwords in groups of four ("abcd efgh ..."); the spaces aren't part of it
    return pw.replace(" ", "") if "gmail" in host or "google" in host else pw


def send(day: str | None = None, dry_run: bool = False) -> int:
    """Returns how many emails were sent."""
    day = day or date.today().isoformat()
    host = env("JOB_SMTP_HOST") or env("SMTP_HOST")
    port = int(env("JOB_SMTP_PORT") or env("SMTP_PORT") or 587)
    user = env("JOB_SMTP_USER") or env("SMTP_USER")
    pw = _password(host)
    why_not = not_ready()
    if why_not and not dry_run:
        warn(f"not sending: {why_not}")
        return 0
    done = already_sent()
    done_domains = contacted_domains()
    published = published_contacts(day)
    s = session()
    seen: set[str] = set()
    seen_domains: set[str] = set()
    queue = []
    for it in load(day):
        to = it["to"].strip().lower()
        domain = to.partition("@")[2]
        if to in done or to in seen or not domain:
            continue
        ok, why = allowed_recipient(to, it.get("recipient_role", ""), bool(it.get("from_posting")))
        if not ok:
            log_row(it, to, f"skipped: {why}")
            continue
        company_domain = domain not in FREE_MAIL
        if company_domain and (domain in done_domains or domain in seen_domains):
            continue  # one email per company, and none within recontact_days
        if to not in published.get(str(it.get("id")), set()) and not on_page(it.get("evidence_url") or "", to, s):
            log_row(it, to, "skipped: not verified as published (not in contacts, not on evidence_url)")
            continue
        if not has_mx(domain):
            log_row(it, to, "skipped: no MX")
            continue
        seen.add(to)
        if company_domain:
            seen_domains.add(domain)
        queue.append(it)

    log(f"  {len(queue)} emails to send from {user or '(no JOB_SMTP_USER / SMTP_USER set)'}")
    if dry_run:
        if why_not:
            warn(f"a real send would stop here: {why_not}")
        for it in queue:
            log(f"  - {it.get('company', ''):<30} {it['to']:<38} {it['subject']}")
        return 0
    if queue and not (host and user and pw):
        warn("JOB_SMTP_USER / JOB_SMTP_PASSWORD (or SMTP_USER / SMTP_PASSWORD) not set in .env")
        return 0

    sender = _sender_name()
    sent = 0
    for n, it in enumerate(queue, 1):
        to = it["to"].strip()
        try:
            send_plain(host, port, user, pw, sender, to, it["subject"], it["body"])
            result = "sent"
            sent += 1
        except SendingLimitReached as e:
            log_row(it, to, f"error: {e}")
            warn("the provider's daily sending limit was reached; the rest wait for tomorrow")
            break
        except (smtplib.SMTPException, OSError) as e:
            result = f"error: {e}"
        log_row(it, to, result)
        log(f"  [{n}/{len(queue)}] {result:<6} {it.get('company', '')} <{to}>")
        if n < len(queue):
            time.sleep(random.uniform(3, 8))
    return sent
