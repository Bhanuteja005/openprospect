"""Buyer intent via Huginn (https://github.com/huginn/huginn).

Huginn checks Reddit every hour for people asking to hire a website / marketing /
automation person (the scenario in infra/huginn/buyer-intent-scenario.json), filters out
freelancers advertising themselves, and publishes the real requests as a feed.

This module:
  setup_huginn()  logs into Huginn, imports the scenario and records the feed URL (one time)
  pull()          reads the feed and puts every new request into Twenty CRM as a deal
                  named "INTENT: <post title>" with the post link and text in a note.

These people asked publicly, so reply to them yourself on Reddit (fast!). Automated
replies get accounts banned, so this part stays a one-click manual step."""

from __future__ import annotations

import re

import requests

from openprospect.core import db
from openprospect.core.config import env, paths, set_huginn_feed_url, settings
from openprospect.core.log import log, warn
from openprospect.crm import Twenty

FEED_AGENT = "Buyer intent feed"
# The feed URL ends in a secret. The scenario file ships with a placeholder that is swapped for
# HUGINN_FEED_SECRET (random, made by `openprospect init`) on import, so no two installs share a URL.
PLACEHOLDER_SECRET = "openprospect-intent"
SOURCE = "buyer_intent"


def scenario_file():
    return paths.infra / "huginn" / "buyer-intent-scenario.json"


def _token(html: str) -> str:
    m = re.search(r'name="csrf-token" content="([^"]+)"', html) or re.search(
        r'name="authenticity_token" value="([^"]+)"', html
    )
    return m.group(1) if m else ""


def _login(base: str) -> requests.Session:
    s = requests.Session()
    page = s.get(f"{base}/users/sign_in", timeout=30).text
    r = s.post(
        f"{base}/users/sign_in",
        data={
            "authenticity_token": _token(page),
            "user[login]": env("HUGINN_USERNAME") or "admin",
            "user[password]": env("HUGINN_PASSWORD"),
            "user[remember_me]": "0",
        },
        timeout=30,
    )
    if "/users/sign_in" in r.url:
        raise RuntimeError("Huginn login failed: check HUGINN_USERNAME / HUGINN_PASSWORD in .env")
    return s


def _agents(s: requests.Session, base: str) -> list[dict]:
    r = s.get(f"{base}/agents.json", timeout=30)
    r.raise_for_status()
    return r.json()


def setup_huginn() -> str:
    base = env("HUGINN_URL").rstrip("/")
    s = _login(base)
    agents = _agents(s, base)
    feed = next((a for a in agents if a.get("name") == FEED_AGENT), None)
    if not feed:
        page = s.get(f"{base}/scenarios/scenario_imports/new", timeout=30).text
        r = s.post(
            f"{base}/scenarios/scenario_imports",
            data={
                "authenticity_token": _token(page),
                "scenario_import[data]": scenario_file()
                .read_text(encoding="utf-8")
                .replace(PLACEHOLDER_SECRET, feed_secret()),
                "scenario_import[do_import]": "1",
            },
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Huginn scenario import failed: {r.status_code}")
        agents = _agents(s, base)
        feed = next((a for a in agents if a.get("name") == FEED_AGENT), None)
        if not feed:
            raise RuntimeError("Scenario imported but the feed agent was not found")
        log("  Huginn: buyer-intent scenario imported (checks Reddit every hour)")
    url = f"{base}/users/{feed['user_id']}/web_requests/{feed['id']}/{feed_secret()}.json"
    set_huginn_feed_url(url)
    log(f"  Huginn feed: {url}")
    return url


def feed_secret() -> str:
    return env("HUGINN_FEED_SECRET") or PLACEHOLDER_SECRET


def push(conn, t: Twenty, lead) -> bool:
    title, link, text = lead["name"] or "", lead["website"] or "", lead["description"] or ""
    oid = t.create("opportunities", {"name": f"INTENT: {title[:110]}", "stage": "NEW"})
    if not oid:
        return False
    t.note("Buyer intent - reply fast", f"**{title}**\n\n{link}\n\n{text[:1500]}", targetOpportunityId=oid)
    db.update(conn, lead["id"], crm_opportunity_id=oid, crm_synced_at=db.now(), crm_stage="NEW")
    return True


def pull(conn) -> int:
    url = settings().get("intent", {}).get("huginn_feed_url")
    if not url:
        warn("Huginn feed not set up yet: run  openprospect setup")
        return 0
    try:
        data = requests.get(url, timeout=30).json()
    except (requests.RequestException, ValueError) as e:
        warn(f"Huginn feed not reachable: {e}")
        return 0
    items = data.get("items") or []
    t = Twenty()
    crm_ok = t.ok and t.check()
    new = 0
    for item in items:
        link = item.get("link") or item.get("url") or ""
        if not link:
            continue
        sid = f"intent:{link}"
        if conn.execute("SELECT 1 FROM leads WHERE source_id = ?", (sid,)).fetchone():
            continue
        title = (item.get("title") or "").strip()
        text = (item.get("description") or "").strip()
        db.upsert_lead(
            conn,
            {
                "source": SOURCE,
                "source_id": sid,
                "name": title[:200],
                "website": link,
                "description": text[:1500],
                "stage": "intent",
                "category": "Buyer intent",
            },
        )
        new += 1
    # new posts, plus any that missed the CRM on an earlier run (e.g. Twenty was down)
    pushed = 0
    if crm_ok:
        for lead in conn.execute(
            "SELECT * FROM leads WHERE source = ? AND crm_synced_at IS NULL", (SOURCE,)
        ).fetchall():
            pushed += push(conn, t, lead)
    conn.commit()
    log(f"  buyer intent: {new} new requests, {pushed} pushed to Twenty")
    return new
