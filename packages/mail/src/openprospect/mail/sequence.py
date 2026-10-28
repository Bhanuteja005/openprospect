"""The cold email sequence, sent through Listmonk.

Every run:
  1. checks earlier campaigns (did you start the drafts? were they cancelled?)
  2. picks who is due today, within your daily limit:
        follow-ups first (step 2 / step 3 for people who haven't replied), then new leads, best score first
  3. creates one Listmonk list + campaign per step, with each person's personalised first line
  4. auto_send: true  -> starts the campaigns
     auto_send: false -> leaves them as drafts in Listmonk for you to review and press Start

Replies, bounces and opt-outs are handled in replies.py, and stop the sequence for that person."""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from openprospect.core import db
from openprospect.core.config import env, settings
from openprospect.core.log import log, warn

from .listmonk import Listmonk, ListmonkError
from .templates import render_body


def _today_utc_start() -> str:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def refresh_sends(conn, lm: Listmonk) -> None:
    """Draft campaigns: once you press Start in Listmonk the people in it count as emailed.
    With auto_send on, drafts left over from earlier runs are started automatically."""
    auto = bool(settings()["sending"].get("auto_send", False))
    # rows whose campaign was never created (Listmonk failed mid-way): free them for the next send
    conn.execute("DELETE FROM sends WHERE state = 'queued' AND campaign_id IS NULL")
    queued = conn.execute("SELECT DISTINCT campaign_id FROM sends WHERE state = 'queued'").fetchall()
    for row in queued:
        cid = row["campaign_id"]
        try:
            status = lm.req("GET", f"/campaigns/{cid}")["status"]
            if status == "draft" and auto:
                lm.req("PUT", f"/campaigns/{cid}/status", json={"status": "running"})
                log(f"  started waiting draft campaign #{cid}")
                status = "running"
        except ListmonkError as e:
            if e.status != 404:  # a hiccup, not a deleted campaign: decide on the next run
                warn(f"campaign #{cid}: {e}")
                continue
            status = "cancelled"  # deleted in Listmonk
        except requests.RequestException as e:
            warn(f"campaign #{cid}: {e}")
            continue
        if status in ("running", "finished", "paused", "scheduled"):
            for s in conn.execute("SELECT * FROM sends WHERE campaign_id = ? AND state = 'queued'", (cid,)).fetchall():
                conn.execute("UPDATE sends SET state = 'sent' WHERE id = ?", (s["id"],))
                lead = conn.execute("SELECT stage FROM leads WHERE id = ?", (s["lead_id"],)).fetchone()
                fields = {
                    "seq_step": s["step"],
                    "last_emailed_at": max(s["sent_at"], db.now()) if status == "scheduled" else db.now(),
                }
                if lead and lead["stage"] == "new":
                    fields["stage"] = "emailing"
                db.update(conn, s["lead_id"], **fields)
        elif status == "cancelled":
            conn.execute("UPDATE sends SET state = 'cancelled' WHERE campaign_id = ? AND state = 'queued'", (cid,))
    conn.commit()


def due_leads(conn, budget: int) -> dict[int, list]:
    cfg = settings()
    sendable = tuple(cfg.get("verify", {}).get("sendable_statuses", ["safe", "site_mx_ok"]))
    tiers = {"A": ("A",), "B": ("A", "B"), "C": ("A", "B", "C")}[cfg["scoring"].get("min_tier_to_email", "C")]
    gaps = cfg["sending"].get("followup_after_days", [3, 5])
    max_step = len(cfg["sending"]["templates"])
    queued_ids = {r["lead_id"] for r in conn.execute("SELECT lead_id FROM sends WHERE state = 'queued'")}
    now = datetime.now(UTC)
    due: dict[int, list] = {}

    # follow-ups first
    for step in range(2, max_step + 1):
        gap = gaps[step - 2] if step - 2 < len(gaps) else gaps[-1]
        cutoff = (now - timedelta(days=gap)).isoformat()
        rows = conn.execute(
            "SELECT * FROM leads WHERE stage = 'emailing' AND seq_step = ? AND last_emailed_at <= ? ORDER BY score DESC",
            (step - 1, cutoff),
        ).fetchall()
        picked = [r for r in rows if r["id"] not in queued_ids and not db.is_suppressed(conn, r["email"])][:budget]
        if picked:
            due[step] = picked
            budget -= len(picked)
        if budget <= 0:
            return due

    marks = ",".join("?" for _ in sendable)
    tmarks = ",".join("?" for _ in tiers)
    rows = conn.execute(
        f"SELECT * FROM leads WHERE stage = 'new' AND email IS NOT NULL AND email_status IN ({marks}) "
        f"AND tier IN ({tmarks}) AND seq_step = 0 ORDER BY score DESC",
        (*sendable, *tiers),
    ).fetchall()
    skip_sources = set(cfg["sending"].get("skip_sources") or [])
    rows = [r for r in rows if r["source"] not in skip_sources]
    seen_emails = {r["email"] for r in conn.execute("SELECT email FROM leads WHERE seq_step > 0 AND email IS NOT NULL")}
    # Foreign first: countries in sending.country_priority go first (in that order), then the
    # rest; best score first inside each country. Some countries are capped per day.
    prio = [c.upper() for c in cfg["sending"].get("country_priority", ["US", "GB", "AU", "CA", "NZ", "IE"])]
    caps = {k.upper(): int(v) for k, v in (cfg["sending"].get("max_new_per_day_by_country") or {}).items()}

    def rank(r):
        return (
            prio.index((r["country"] or "").upper()) if (r["country"] or "").upper() in prio else len(prio),
            -(r["score"] or 0),
        )

    count: dict[str, int] = {}
    picked = []
    for r in sorted(rows, key=rank):
        if len(picked) >= budget:
            break
        if r["id"] in queued_ids or r["email"] in seen_emails or db.is_suppressed(conn, r["email"]):
            continue
        ctry = (r["country"] or "").upper()
        if ctry in caps and count.get(ctry, 0) >= caps[ctry]:
            continue
        count[ctry] = count.get(ctry, 0) + 1
        seen_emails.add(r["email"])  # chains share one inbox: email it once
        picked.append(r)
    if picked:
        due[1] = picked
    return due


REGION_TZ = {
    "north america": "America/New_York",
    "usa": "America/New_York",
    "us": "America/New_York",
    "europe": "Europe/London",
    "uk": "Europe/London",
    "australia": "Australia/Sydney",
    "asia": "Asia/Kolkata",
    "india": "Asia/Kolkata",
}
COUNTRY_TZ = {
    "US": "America/New_York",
    "CA": "America/Toronto",
    "GB": "Europe/London",
    "UK": "Europe/London",
    "AU": "Australia/Sydney",
    "NZ": "Pacific/Auckland",
    "IE": "Europe/Dublin",
    "IN": "Asia/Kolkata",
    "AE": "Asia/Dubai",
    "SG": "Asia/Singapore",
}


EASTERN = ("America/New_York", "America/Detroit", "America/Indiana", "America/Kentucky", "America/Toronto")


def lead_tz(lead) -> str:
    """The business's own time zone (from Google Maps), or a best guess from its country/region.
    US leads only use Eastern or Central: East Coast keeps Eastern, the rest of the US uses Central."""
    if (lead["country"] or "").upper() == "US":
        own = (lead["timezone"] if "timezone" in lead.keys() else "") or ""
        return "America/New_York" if own.startswith(EASTERN) else "America/Chicago"

    for cand in (
        lead["timezone"] if "timezone" in lead.keys() else None,
        COUNTRY_TZ.get((lead["country"] or "").upper()),
        REGION_TZ.get((lead["country"] or "").lower()),
    ):
        if cand:
            try:
                ZoneInfo(cand)
                return cand
            except Exception:
                continue
    return settings().get("sending", {}).get("default_timezone", "UTC")


def send_time(tz: str) -> datetime | None:
    """None = it's business hours there now, send immediately. Otherwise the next weekday
    morning (9:00-10:30 local, a random minute so it doesn't look automated), in UTC."""
    cfg = settings().get("sending", {})
    start_h, end_h = cfg.get("local_send_hours", [9, 16])
    local = datetime.now(ZoneInfo(tz))
    if local.weekday() < 5 and start_h <= local.hour < end_h:
        return None
    day = local
    if local.hour >= start_h or local.weekday() >= 5:
        day = local + timedelta(days=1)
    while day.weekday() >= 5:  # skip Saturday / Sunday
        day += timedelta(days=1)
    at = day.replace(hour=start_h, minute=0, second=0, microsecond=0) + timedelta(minutes=random.randint(0, 90))
    return at.astimezone(UTC)


def send(conn) -> int:
    lm = Listmonk()
    if not lm.ok:
        warn("LISTMONK_API_USER / LISTMONK_API_TOKEN not set in .env: skipping sending (see docs/getting-started.md)")
        return 0
    if not lm.check():
        warn("Listmonk not reachable or API token wrong: skipping sending")
        return 0
    refresh_sends(conn, lm)
    if not (env("FROM_EMAIL") or env("SMTP_USER")):
        warn("FROM_EMAIL / SMTP_USER not set in .env: connect your sending inbox first (docs/getting-started.md)")
        return 0
    cfg = settings()
    # Cold email law (CAN-SPAM in the US, and good practice everywhere) wants a postal address
    # in every email. Nothing is sent until one is set.
    if not (cfg.get("agency", {}).get("postal_address") or "").strip():
        warn("agency.postal_address is empty in config/settings.yaml: nothing is sent until you add it")
        return 0
    limit = int(cfg["sending"].get("daily_limit", 20))
    ws = cfg["sending"].get("warmup_start_date")
    if ws:
        days = (date.today() - date.fromisoformat(str(ws))).days
        ramp = int(cfg["sending"].get("warmup_first_day", 15)) + max(days, 0) * int(
            cfg["sending"].get("warmup_add_per_day", 5)
        )
        if ramp < limit:
            log(f"  warm-up: day {days + 1} of the new inbox, sending up to {ramp} today (full speed: {limit})")
            limit = ramp
    auto = bool(cfg["sending"].get("auto_send", False))
    used = conn.execute(
        "SELECT COUNT(*) c FROM sends WHERE state != 'cancelled' AND sent_at >= ?", (_today_utc_start(),)
    ).fetchone()["c"]
    budget = max(limit - used, limit if auto else 0)  # per-day room is checked again per delivery day below
    if budget <= 0:
        log(f"  daily limit reached ({limit}); more tomorrow")
        return 0
    due = due_leads(conn, budget)
    if not due:
        log("  nobody is due an email today")
        return 0

    tpl_id = lm.template_id(conn)
    frm = env("FROM_EMAIL") or env("SMTP_USER")
    sender = cfg.get("agency", {}).get("sender_name", "")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = 0
    groups: dict[tuple, list] = {}
    for step, leads in due.items():
        for lead in leads:
            groups.setdefault((step, lead_tz(lead)), []).append(lead)

    def delivered_on(day_utc: str) -> int:
        # emails going out on that UTC day (sends.sent_at holds the delivery time)
        return conn.execute(
            "SELECT COUNT(*) c FROM sends WHERE state != 'cancelled' AND substr(sent_at, 1, 10) = ?", (day_utc,)
        ).fetchone()["c"]

    for (step, tz), leads in sorted(groups.items()):
        when = send_time(tz) if auto else None
        deliver_at = (when or datetime.now(UTC)).isoformat(timespec="seconds")
        room = limit - delivered_on(deliver_at[:10])
        if room <= 0:
            log(f"  {tz}: {deliver_at[:10]} is already full ({limit}); these wait for the next run")
            continue
        leads = leads[:room]
        label = f"step {step} - {tz.split('/')[-1]} - {stamp}"
        lst = lm.req(
            "POST",
            "/lists",
            json={
                "name": f"Cold {label}",
                "type": "private",
                "optin": "single",
                "tags": ["openprospect", f"step{step}"],
            },
        )
        added = 0
        for lead in leads:
            try:
                sid = lm.upsert_subscriber(lead, lst["id"])
                db.update(conn, lead["id"], listmonk_id=sid)
                conn.execute(
                    "INSERT INTO sends(lead_id, step, list_id, state, sent_at) VALUES (?, ?, ?, 'queued', ?)",
                    (lead["id"], step, lst["id"], deliver_at),
                )
                added += 1
            except Exception as e:
                warn(f"{lead['email']}: {e}")
        if not added:
            continue
        tpl = cfg["sending"]["templates"][step]
        camp = {
            "name": f"Cold {label} ({added})",
            "subject": tpl["subject"],
            "lists": [lst["id"]],
            "type": "regular",
            "content_type": "html",
            "body": render_body(step),
            "messenger": "email",
            "template_id": tpl_id,
            "tags": ["openprospect", f"step{step}", tz],
        }
        if frm:
            camp["from_email"] = f"{sender} <{frm}>" if sender else frm
            camp["headers"] = [{"List-Unsubscribe": f"<mailto:{frm}?subject=unsubscribe>"}]
        if when and auto:
            camp["send_at"] = when.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            c = lm.req("POST", "/campaigns", json=camp)
        except (ListmonkError, requests.RequestException) as e:
            # nobody was emailed: forget these rows so the leads are picked again next time
            conn.execute("DELETE FROM sends WHERE list_id = ? AND campaign_id IS NULL", (lst["id"],))
            conn.commit()
            warn(f"step {step}: could not create the campaign ({e}); these {added} leads wait for the next run")
            continue
        conn.execute("UPDATE sends SET campaign_id = ? WHERE list_id = ?", (c["id"], lst["id"]))
        conn.commit()
        if auto and when:
            lm.req("PUT", f"/campaigns/{c['id']}/status", json={"status": "scheduled"})
            local = when.astimezone(ZoneInfo(tz)).strftime("%a %H:%M")
            log(f"  step {step}: campaign #{c['id']} SCHEDULED for {added} people at {local} {tz} time")
        elif auto:
            lm.req("PUT", f"/campaigns/{c['id']}/status", json={"status": "running"})
            log(f"  step {step}: campaign #{c['id']} STARTED for {added} people ({tz}, business hours now)")
        else:
            log(
                f"  step {step}: campaign #{c['id']} created as a DRAFT for {added} people "
                f"(review + press Start at {env('LISTMONK_URL')}/admin/campaigns/{c['id']})"
            )
        total += added
    if auto:
        refresh_sends(conn, lm)
    return total
