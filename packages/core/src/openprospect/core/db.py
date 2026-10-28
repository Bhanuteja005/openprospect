"""SQLite store: one row per lead. This is the pipeline's memory, so nothing is
scraped, emailed or pushed to the CRM twice."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from .config import paths


def db_path():
    return paths.data / "leads.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,          -- google_maps | remote_companies | buyer_intent
    source_id       TEXT NOT NULL UNIQUE,   -- place_id, slug or post URL
    name            TEXT,
    category        TEXT,
    address         TEXT,
    city            TEXT,
    country         TEXT,
    timezone        TEXT,
    phone           TEXT,
    website         TEXT,
    domain          TEXT,
    rating          REAL,
    reviews         INTEGER,
    price_range     TEXT,
    maps_url        TEXT,
    query           TEXT,
    description     TEXT,
    emails          TEXT DEFAULT '[]',      -- JSON list of candidate emails
    email           TEXT,                   -- the chosen address
    email_status    TEXT,                   -- safe | risky | site_mx_ok | invalid | unknown | none
    signals         TEXT DEFAULT '{}',      -- JSON: what we learned from the website
    pain_points     TEXT DEFAULT '[]',      -- JSON list
    icebreaker      TEXT,
    score           INTEGER,
    tier            TEXT,
    stage           TEXT DEFAULT 'new',     -- new | emailing | replied | bounced | unsubscribed | intent
    seq_step        INTEGER DEFAULT 0,      -- last email step sent (0 = none)
    last_emailed_at TEXT,
    enriched_at     TEXT,
    verified_at     TEXT,
    scored_at       TEXT,
    crm_company_id  TEXT,
    crm_person_id   TEXT,
    crm_opportunity_id TEXT,
    crm_synced_at   TEXT,
    crm_stage       TEXT,
    listmonk_id     INTEGER,
    created_at      TEXT,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(domain);

CREATE TABLE IF NOT EXISTS sends (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     INTEGER NOT NULL,
    step        INTEGER NOT NULL,
    campaign_id INTEGER,
    list_id     INTEGER,
    state       TEXT DEFAULT 'queued',      -- queued (draft campaign) | sent | cancelled
    sent_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS done_queries (
    query   TEXT PRIMARY KEY,
    done_at TEXT
);

CREATE TABLE IF NOT EXISTS suppression (
    value   TEXT PRIMARY KEY,   -- an email or a @domain
    reason  TEXT,
    added_at TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    paths.data.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path(), timeout=120)  # wait for another run instead of failing
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(leads)")}
    if "timezone" not in cols:
        conn.execute("ALTER TABLE leads ADD COLUMN timezone TEXT")
    return conn


def upsert_lead(conn: sqlite3.Connection, lead: dict) -> bool:
    """Insert a new lead. Returns True if it was new. Existing leads keep their progress,
    but empty fields get filled in from the new data."""
    lead = dict(lead)
    lead.setdefault("created_at", now())
    lead["updated_at"] = now()
    for k in ("emails", "signals", "pain_points"):
        if k in lead and not isinstance(lead[k], str):
            lead[k] = json.dumps(lead[k])
    row = conn.execute("SELECT * FROM leads WHERE source_id = ?", (lead["source_id"],)).fetchone()
    if row is None:
        cols = ",".join(lead)
        marks = ",".join("?" for _ in lead)
        conn.execute(f"INSERT INTO leads ({cols}) VALUES ({marks})", list(lead.values()))
        return True
    fills = {k: v for k, v in lead.items() if v not in (None, "", "[]") and not row[k] and k != "created_at"}
    if fills:
        update(conn, row["id"], **fills)
    return False


def update(conn: sqlite3.Connection, lead_id: int, **fields) -> None:
    for k in ("emails", "signals", "pain_points"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k])
    fields["updated_at"] = now()
    sets = ",".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE leads SET {sets} WHERE id = ?", [*fields.values(), lead_id])


def loads(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def kv_get(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def kv_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value)
    )


def suppress(conn: sqlite3.Connection, value: str, reason: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO suppression(value, reason, added_at) VALUES (?, ?, ?)",
        (value.lower(), reason, now()),
    )


def is_suppressed(conn: sqlite3.Connection, email: str) -> bool:
    email = (email or "").lower()
    domain = "@" + email.split("@")[-1] if "@" in email else ""
    row = conn.execute("SELECT 1 FROM suppression WHERE value IN (?, ?)", (email, domain)).fetchone()
    return row is not None
