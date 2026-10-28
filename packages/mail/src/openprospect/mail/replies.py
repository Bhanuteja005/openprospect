"""Reply, bounce and opt-out detection over IMAP (free, works with Gmail / Workspace / Zoho).

Reads your sending inbox and:
  - a reply from a lead        -> stops their follow-ups, moves the CRM deal to SCREENING, adds the reply as a note
  - "no thanks" / "unsubscribe" -> stops forever (suppression list) and blocklists them in Listmonk
  - a bounce (mailer-daemon)   -> stops forever and blocklists them
"""

from __future__ import annotations

import email
import imaplib
import json
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr

from openprospect import crm
from openprospect.core import db
from openprospect.core.config import env
from openprospect.core.log import log, warn
from openprospect.core.text import FREE_MAIL, clean_emails

from .listmonk import Listmonk

OPT_OUT = re.compile(
    r"\b(unsubscribe|remove me|stop emailing|not interested|no thanks|no, thanks|don'?t (email|contact)|take me off)\b",
    re.I,
)
BOUNCE_FROM = ("mailer-daemon", "postmaster", "mail delivery")


def _text(msg) -> str:
    parts = []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_type() in ("text/plain", "message/delivery-status") or (
            part.get_content_type() == "text/html" and not parts
        ):
            try:
                payload = part.get_payload(decode=True) or b""
                parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="ignore"))
            except Exception:
                continue
    text = "\n".join(parts)
    return re.sub(r"<[^>]+>", " ", text)


def _fresh_part(body: str) -> str:
    """Only the new text of a reply, not the quoted original email."""
    cut = re.split(r"\n\s*(On .{5,80}wrote:|-----Original Message-----|From: )", body, maxsplit=1)[0]
    return "\n".join(line for line in cut.splitlines() if not line.startswith(">")).strip()


def _lead_for(conn, addr: str):
    addr = addr.lower()
    row = conn.execute("SELECT * FROM leads WHERE lower(email) = ? AND seq_step > 0", (addr,)).fetchone()
    if row:
        return row
    domain = addr.split("@")[-1]
    if domain and domain not in FREE_MAIL:
        return conn.execute(
            "SELECT * FROM leads WHERE domain = ? AND seq_step > 0 ORDER BY score DESC", (domain,)
        ).fetchone()
    return None


def cancel_pending(conn, lead, lm: Listmonk | None) -> int:
    """Remove the lead from campaigns that haven't reached them yet: drafts, and scheduled sends
    whose delivery time is still ahead. Returns how many sends were cancelled."""
    rows = conn.execute(
        "SELECT id, list_id FROM sends WHERE lead_id = ? AND state != 'cancelled' AND (state = 'queued' OR sent_at > ?)",
        (lead["id"], db.now()),
    ).fetchall()
    if not rows:
        return 0
    if lm and lm.ok and lead["listmonk_id"]:
        try:
            lm.remove_from_lists(lead["listmonk_id"], sorted({r["list_id"] for r in rows if r["list_id"]}))
        except Exception as e:  # still cancel locally; the blocklist below covers opt-outs
            warn(f"could not remove {lead['email']} from pending Listmonk lists: {e}")
    conn.executemany("UPDATE sends SET state = 'cancelled' WHERE id = ?", [(r["id"],) for r in rows])
    return len(rows)


def stop_lead(conn, lead, stage: str, reason: str, lm: Listmonk | None) -> None:
    db.update(conn, lead["id"], stage=stage)
    cancel_pending(conn, lead, lm)
    if stage in ("unsubscribed", "bounced") and lead["email"]:
        db.suppress(conn, lead["email"], reason)
        if lm and lm.ok and lead["listmonk_id"]:
            lm.blocklist(lead["listmonk_id"])


def accounts() -> list[tuple[str, str, str]]:
    """Inboxes to read: the current sending inbox, plus an older one (IMAP2_*) so replies
    to emails sent from a previous address are still caught."""
    out = []
    for prefix in ("IMAP", "IMAP2"):
        host = env(f"{prefix}_HOST") or "imap.gmail.com"
        user = env(f"{prefix}_USER") or (env("SMTP_USER") if prefix == "IMAP" else "")
        pw = env(f"{prefix}_PASSWORD") or (env("SMTP_PASSWORD") if prefix == "IMAP" else "")
        if user and pw:
            out.append((host, user, pw))
    return out


def check(conn, days: int = 14) -> int:
    boxes = accounts()
    if not boxes:
        warn("IMAP_USER / IMAP_PASSWORD not set in .env: can't detect replies yet (see docs/getting-started.md)")
        return 0
    lm = Listmonk()
    seen = set(db.loads(db.kv_get(conn, "imap_seen", "[]"), []))
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    handled = 0
    for host, user, pw in boxes:
        try:
            box = imaplib.IMAP4_SSL(host)
            box.login(user, pw)
        except Exception as e:
            warn(f"IMAP login failed for {user}: {e}")
            continue
        handled += _check_box(conn, box, seen, since, lm)
    db.kv_set(conn, "imap_seen", json.dumps(sorted(seen)[-5000:]))
    conn.commit()
    if not handled:
        log("  no new replies or bounces")
    return handled


def _check_box(conn, box, seen: set, since: str, lm) -> int:
    handled = 0
    try:
        box.select("INBOX", readonly=True)
        # Only ask Gmail for mail from people we emailed (and their domains) plus bounce notices,
        # instead of downloading the whole inbox.
        contacted = conn.execute("SELECT email, domain FROM leads WHERE seq_step > 0 AND email IS NOT NULL").fetchall()
        senders = {r["email"].lower() for r in contacted}
        senders |= {r["domain"] for r in contacted if r["domain"] and r["domain"] not in FREE_MAIL}
        senders |= {"mailer-daemon", "postmaster"}
        nums: list[bytes] = []
        for who in sorted(senders):
            try:
                _, data = box.search(None, f'(SINCE "{since}" FROM "{who}")')
                nums.extend((data[0] or b"").split())
            except imaplib.IMAP4.error as e:
                warn(f"IMAP search for {who} failed: {e}")
        for num in dict.fromkeys(nums):
            try:
                _, hdr = box.fetch(num, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
                mid = (email.message_from_bytes(hdr[0][1]).get("Message-ID") or num.decode()).strip()
                if mid in seen:
                    continue
                _, raw = box.fetch(num, "(BODY.PEEK[])")
                msg = email.message_from_bytes(raw[0][1])
            except (imaplib.IMAP4.error, TypeError, IndexError) as e:
                warn(f"skipped one message: {e}")
                continue
            seen.add(mid)
            sender = parseaddr(msg.get("From", ""))[1].lower()
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            body = _text(msg)

            if any(b in sender for b in BOUNCE_FROM) or any(b in msg.get("From", "").lower() for b in BOUNCE_FROM):
                for addr in clean_emails(body):
                    lead = conn.execute("SELECT * FROM leads WHERE lower(email) = ?", (addr,)).fetchone()
                    if lead and lead["stage"] != "bounced":
                        stop_lead(conn, lead, "bounced", "bounce", lm)
                        log(f"  bounce: {addr}")
                        handled += 1
                continue

            lead = _lead_for(conn, sender)
            if not lead or lead["stage"] in ("replied", "unsubscribed", "bounced"):
                continue
            fresh = _fresh_part(body)[:1500]
            if OPT_OUT.search(fresh) or "unsubscribe" in subject.lower():
                stop_lead(conn, lead, "unsubscribed", "opt-out reply", lm)
                crm.set_stage(conn, lead, lead["crm_stage"] or "NEW", note=f"Opted out by reply\n\n> {fresh[:500]}")
                log(f"  opt-out: {lead['name']} <{sender}>")
            else:
                stop_lead(conn, lead, "replied", "", lm)
                crm.set_stage(conn, lead, "SCREENING", note=f"Replied: {subject}\n\nFrom {sender}\n\n> {fresh}")
                log(f"  REPLY from {lead['name']} <{sender}>: {subject}")
            handled += 1
    finally:
        try:
            box.logout()
        except Exception:
            pass
    return handled
