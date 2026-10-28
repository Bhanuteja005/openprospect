"""The enrich step: read each new lead's website and record what we learned."""

from __future__ import annotations

import requests

from openprospect.core import db
from openprospect.core.config import settings
from openprospect.core.log import log, warn
from openprospect.core.text import clean_emails, domain_of, normalize_url

from .pains import pain_points
from .reader import Reader
from .signals import analyse_html, contact_pages, security_findings


def enrich_one(reader: Reader, website: str) -> dict:
    cfg = settings().get("enrich", {})
    url = normalize_url(website)
    final, html, secs, ok = reader.fetch(url)
    first_error = reader.last_error
    if not ok or not html:
        # try the https / http twin before giving up
        twin = (
            url.replace("http://", "https://", 1)
            if url.startswith("http://")
            else url.replace("https://", "http://", 1)
        )
        final, html, secs, ok = reader.fetch(twin)
    if not ok or not html:
        return {"site_ok": False, "site_error": first_error or reader.last_error or "down"}
    info = analyse_html(html, final)
    info.update(security_findings(reader, final, html, getattr(reader, "last_headers", {}) or {}))
    info["site_ok"] = True
    # https is broken but http works: anyone opening the https link sees a security warning
    info["ssl_broken"] = first_error == "ssl"
    info["final_url"] = final
    info["https"] = final.startswith("https://")
    info["load_seconds"] = round(secs, 2) if secs is not None else None

    if secs is not None and secs > float(cfg.get("slow_site_seconds", 4)):
        # one slow answer can be bad luck: time it once more and keep the faster result
        try:
            _, _, again = reader.direct(final)
            info["load_seconds"] = round(min(secs, again), 2)
        except requests.RequestException:
            pass

    for page in contact_pages(info["links"], final, int(cfg.get("max_pages_per_site", 4)) - 1):
        _, sub_html, _, sub_ok = reader.fetch(page)
        if sub_ok and sub_html:
            sub = analyse_html(sub_html, page)
            info["emails"] = clean_emails(info["emails"] + sub["emails"])
            info["booking"] = info["booking"] or sub["booking"]
            info["socials"] = {**sub["socials"], **info["socials"]}
    info.pop("links", None)
    return info


def enrich(conn, limit: int | None = None) -> int:
    limit = limit or int(settings().get("enrich", {}).get("per_run_limit", 150))
    rows = conn.execute(
        "SELECT * FROM leads WHERE enriched_at IS NULL AND stage = 'new' ORDER BY id LIMIT ?", (limit,)
    ).fetchall()
    if not rows:
        log("  nothing new to enrich")
        return 0
    reader = Reader()
    done = 0
    for i, lead in enumerate(rows, 1):
        old = db.loads(lead["signals"], {})
        sig: dict = {}
        if lead["website"]:
            try:
                sig = enrich_one(reader, lead["website"])
            except Exception as e:  # one bad site must never stop the run
                warn(f"{lead['name']}: {e}")
                sig = {"site_ok": False}
        emails = clean_emails(db.loads(lead["emails"], []) + sig.pop("emails", []))
        sig = {**old, **sig}
        db.update(
            conn,
            lead["id"],
            signals=sig,
            emails=emails,
            pain_points=pain_points(lead, sig),
            domain=lead["domain"] or domain_of(sig.get("final_url")),
            enriched_at=db.now(),
        )
        done += 1
        if i % 10 == 0:
            conn.commit()
            log(f"  enriched {i}/{len(rows)}")
    conn.commit()
    log(f"  enriched {done} leads")
    return done
