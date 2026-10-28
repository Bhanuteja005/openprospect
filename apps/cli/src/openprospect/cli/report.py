"""Health checks (`doctor`), numbers (`stats`) and CSV export."""

from __future__ import annotations

import csv
import shutil
import socket
from datetime import datetime

from openprospect.core import db
from openprospect.core.config import env, paths, settings
from openprospect.core.http import is_up
from openprospect.core.log import log
from openprospect.crm import Twenty
from openprospect.mail import Listmonk

EXPORT_COLS = [
    "tier",
    "score",
    "name",
    "category",
    "city",
    "country",
    "phone",
    "email",
    "email_status",
    "website",
    "rating",
    "reviews",
    "pain_points",
    "icebreaker",
    "stage",
    "seq_step",
    "maps_url",
    "source",
]


def port25_open() -> bool:
    """Reacher needs outbound port 25. Try Gmail's MX."""
    try:
        with socket.create_connection(("gmail-smtp-in.l.google.com", 25), timeout=6) as s:
            return s.recv(3) == b"220"
    except OSError:
        return False


def doctor() -> None:
    ok = lambda b: "OK  " if b else "--  "  # noqa: E731
    log(f"Workspace  {paths.home}")
    log(f"  {ok(paths.env_file.exists())}.env")
    log(f"  {ok(paths.settings_file.exists())}config/settings.yaml")
    if not (paths.env_file.exists() and paths.settings_file.exists()):
        log("  run `openprospect init` first")
        return
    agency = settings().get("agency", {})
    log(f"  {ok(bool(agency.get('sender_name')))}agency.sender_name set")
    log(f"  {ok(bool(agency.get('intro')))}agency.intro set (the sentence that says who you are)")
    profile, example = paths.config / "profile.md", paths.config / "profile.example.md"
    own_profile = profile.exists() and not (
        example.exists() and profile.read_text(encoding="utf-8").strip() == example.read_text(encoding="utf-8").strip()
    )
    log(f"  {ok(own_profile)}config/profile.md is your own (only for the job track)")
    log(f"  {ok(bool((agency.get('postal_address') or '').strip()))}agency.postal_address set (required for US leads)")
    log(f"  {ok(bool(shutil.which('docker')))}docker on PATH")
    log(
        f"  {ok(bool(shutil.which(settings().get('jobs', {}).get('writer', {}).get('command', 'claude'))))}"
        "Claude Code on PATH (only for `jobs write`)"
    )
    log("Services")
    log(f"  {ok(is_up(env('TWENTY_URL')))}Twenty CRM      {env('TWENTY_URL')}")
    log(f"  {ok(is_up(env('LISTMONK_URL')))}Listmonk        {env('LISTMONK_URL')}")
    log(f"  {ok(is_up(env('REACHER_URL')))}Reacher         {env('REACHER_URL')}")
    log(f"  {ok(is_up(env('HUGINN_URL')))}Huginn          {env('HUGINN_URL')}")
    log(f"  {ok(is_up(env('FIRECRAWL_URL')))}Firecrawl       {env('FIRECRAWL_URL')}  (optional)")
    log("Connections")
    t = Twenty()
    log(f"  {ok(t.ok and t.check())}Twenty API key")
    lm = Listmonk()
    log(f"  {ok(lm.ok and lm.check())}Listmonk API user/token")
    log(f"  {ok(bool(env('SMTP_USER') and env('SMTP_PASSWORD')))}SMTP inbox set in .env")
    log(f"  {ok(bool(env('IMAP_USER') or env('SMTP_USER')))}IMAP (reply detection) set in .env")
    log(f"  {ok(bool(settings().get('intent', {}).get('huginn_feed_url')))}Huginn buyer-intent feed")
    p25 = port25_open()
    log(
        f"  {ok(p25)}Outbound port 25 (Reacher deep check)"
        + ("" if p25 else "  - blocked: free MX check will be used instead")
    )


def stats(conn) -> None:
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    log(f"Leads total ........ {q('SELECT COUNT(*) FROM leads')}")
    for src in ("google_maps", "remote_companies", "buyer_intent"):
        log(f"  {src:<16} {q('SELECT COUNT(*) FROM leads WHERE source = ?', src)}")
    log(
        f"Tier A / B / C ..... {q('SELECT COUNT(*) FROM leads WHERE tier=?', 'A')} / "
        f"{q('SELECT COUNT(*) FROM leads WHERE tier=?', 'B')} / {q('SELECT COUNT(*) FROM leads WHERE tier=?', 'C')}"
    )
    sendable = settings().get("verify", {}).get("sendable_statuses", ["safe", "site_mx_ok"])
    marks = ",".join("?" for _ in sendable)
    log(f"With sendable email  {q(f'SELECT COUNT(*) FROM leads WHERE email_status IN ({marks})', *sendable)}")
    log(f"In CRM ............. {q('SELECT COUNT(*) FROM leads WHERE crm_synced_at IS NOT NULL')}")
    log(
        f"Emails sent ........ {q('SELECT COUNT(*) FROM sends WHERE state = ?', 'sent')}"
        f"  (waiting in draft campaigns: {q('SELECT COUNT(*) FROM sends WHERE state = ?', 'queued')})"
    )
    for stage in ("emailing", "replied", "unsubscribed", "bounced"):
        log(f"  {stage:<16} {q('SELECT COUNT(*) FROM leads WHERE stage = ?', stage)}")
    top = conn.execute(
        "SELECT name, tier, score, email, phone FROM leads WHERE tier IS NOT NULL ORDER BY score DESC LIMIT 10"
    ).fetchall()
    if top:
        log("Top 10 leads")
        for r in top:
            log(f"  [{r['tier']} {r['score']:>3}] {r['name'][:40]:<40} {r['email'] or r['phone'] or ''}")


def export(conn, path: str | None = None) -> str:
    out = paths.data / "exports"
    out.mkdir(parents=True, exist_ok=True)
    path = path or str(out / f"leads_{datetime.now():%Y%m%d_%H%M}.csv")
    rows = conn.execute("SELECT * FROM leads WHERE source != 'buyer_intent' ORDER BY score DESC").fetchall()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(EXPORT_COLS)
        for r in rows:
            w.writerow([", ".join(db.loads(r[c], [])) if c == "pain_points" else r[c] for c in EXPORT_COLS])
    log(f"  exported {len(rows)} leads -> {path}")
    return path
