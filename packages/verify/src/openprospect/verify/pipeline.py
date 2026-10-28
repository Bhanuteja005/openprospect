"""The verify step: pick the best sendable address for each lead, skip big chains.

Bounces are the #1 reason new sending inboxes get blocked, so nothing is emailed until an
address passes here."""

from __future__ import annotations

from openprospect.core import db
from openprospect.core.config import settings
from openprospect.core.log import log
from openprospect.core.text import pick_best_email

from .reacher import Verifier

ROLE_GUESSES = ["info", "contact", "hello", "office"]


def verify(conn, limit: int | None = None) -> int:
    cfg = settings().get("verify", {})
    limit = limit or int(cfg.get("per_run_limit", 200))
    sendable = set(cfg.get("sendable_statuses", ["safe", "site_mx_ok"]))
    rows = conn.execute(
        "SELECT * FROM leads WHERE enriched_at IS NOT NULL AND verified_at IS NULL AND stage = 'new' LIMIT ?",
        (limit,),
    ).fetchall()
    if not rows:
        log("  nothing new to verify")
        return 0
    chain_words = [w.lower() for w in cfg.get("skip_chains", [])]
    chain_domains = {
        r["domain"]
        for r in conn.execute(
            "SELECT domain FROM leads WHERE domain IS NOT NULL AND domain != '' GROUP BY domain HAVING COUNT(*) >= 3"
        )
    }
    v = Verifier()
    log(f"  verifying emails ({'Reacher + MX' if v.reacher_up else 'MX only, Reacher not running'})")
    good = 0
    for lead in rows:
        name = (lead["name"] or "").lower()
        if lead["domain"] in chain_domains or any(w in name for w in chain_words):
            # big chains answer from a head-office inbox and don't hire from cold email
            db.update(conn, lead["id"], email_status="chain", verified_at=db.now())
            continue
        found = [e for e in db.loads(lead["emails"], []) if not db.is_suppressed(conn, e)]
        results: dict[str, str] = {}
        # check the best-looking addresses first, stop at the first sendable one
        ordered = sorted(found, key=lambda e: e != pick_best_email(found, lead["domain"] or ""))
        for e in ordered[:4]:
            results[e] = v.check(e, found_on_site=True, site_domain=lead["domain"] or "")
            if results[e] in sendable:
                break
        # nothing usable on the site: guess info@ / contact@ - only kept if Reacher proves it exists
        if (
            not any(s in sendable for s in results.values())
            and cfg.get("guess_role_emails", True)
            and lead["domain"]
            and v.reacher_works is not False
            and v.reacher_up
        ):
            for local in ROLE_GUESSES:
                e = f"{local}@{lead['domain']}"
                if e in results:
                    continue
                st = v.check(e, found_on_site=False, site_domain=lead["domain"] or "")
                if st == "safe":
                    results[e] = st
                    break
        ok = [e for e, s in results.items() if s in sendable]
        best = (
            pick_best_email(ok, lead["domain"] or "") if ok else (pick_best_email(found, lead["domain"] or "") or None)
        )
        status = results.get(best, "none") if best else "none"
        db.update(conn, lead["id"], email=best, email_status=status, verified_at=db.now())
        good += status in sendable
    conn.commit()
    log(f"  verified {len(rows)} leads: {good} have a sendable email")
    return good
