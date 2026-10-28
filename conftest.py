"""Shared test fixtures: every test that needs config gets its own throwaway workspace."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent

SETTINGS = {
    "agency": {
        "name": "Test Studio",
        "sender_name": "Alex Rivera",
        "intro": "I'm Alex, a web developer.",
        "website": "https://teststudio.example",
        "postal_address": "1 Test Street, Testville",
        "calendar_link": "",
        "currency": "USD",
        "phone_country": "US",
        "phone_calling_code": "+1",
    },
    "offers": {
        "no_website": "I build websites.",
        "bad_ssl": "I fix certificates.",
        "slow_site": "I make sites fast.",
        "no_analytics": "I set up tracking.",
        "default": "I build things.",
    },
    "scrape": {
        "max_queries_per_run": 5,
        "auto_queries": {
            "enabled": True,
            "niches": ["dentist", "lawyer"],
            "cities": {"US": ["Austin TX", "Dallas TX"], "GB": ["London UK"]},
            "weights": {"US": 2},
        },
    },
    "enrich": {"slow_site_seconds": 4.0, "outdated_year_before": 2023},
    "verify": {"sendable_statuses": ["safe", "site_mx_ok"]},
    "scoring": {
        "category_points": {"dentist": 25, "cafe": 6},
        "default_category_points": 8,
        "tiers": {"A": 70, "B": 50},
        "deal_value": {"A": 1500, "B": 800, "C": 300},
        "min_tier_to_email": "C",
    },
    "sending": {
        "daily_limit": 20,
        "local_send_hours": [9, 16],
        "default_timezone": "UTC",
        "auto_send": False,
        "templates": {
            1: {"subject": "{{ .Subscriber.Attribs.subject }}", "file": "templates/emails/email_1_intro.html"},
            2: {"subject": "one more idea", "file": "templates/emails/email_2_followup.html"},
            3: {"subject": "should I close this?", "file": "templates/emails/email_3_breakup.html"},
        },
    },
    "ai": {"enabled": False},
    "schedule": {"agency_time": "06:00", "jobs_time": "13:00"},
}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A fresh OPENPROSPECT_HOME with config/settings.yaml, the email templates and an empty .env."""
    from openprospect.core import config

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(yaml.safe_dump(SETTINGS, sort_keys=False), encoding="utf-8")
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    (tmp_path / ".env").write_text("", encoding="utf-8")
    monkeypatch.setenv("OPENPROSPECT_HOME", str(tmp_path))
    for key in ("TWENTY_URL", "SMTP_USER", "TWENTY_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    config.reload_settings()
    yield tmp_path
    config.reload_settings()


@pytest.fixture
def conn(workspace):
    from openprospect.core import db

    c = db.connect()
    yield c
    c.close()


@pytest.fixture
def make_lead(conn):
    """Insert a lead and return it as a sqlite3.Row, like the pipeline steps see it."""
    from openprospect.core import db

    counter = {"n": 0}

    def _make(**fields):
        counter["n"] += 1
        lead = {
            "source": "google_maps",
            "source_id": f"gmaps:test{counter['n']}",
            "name": "Bright Smile Dental",
            "category": "Dentist",
            "city": "Austin",
            "country": "US",
            **fields,
        }
        db.upsert_lead(conn, lead)
        conn.commit()
        return conn.execute("SELECT * FROM leads WHERE source_id = ?", (lead["source_id"],)).fetchone()

    return _make
