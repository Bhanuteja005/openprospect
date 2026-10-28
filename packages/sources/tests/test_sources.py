import csv
import json

from openprospect.core import db
from openprospect.sources import google_maps
from openprospect.sources.remote_companies import parse_profile


def test_auto_queries_rotate_countries_with_weights(workspace):
    got = google_maps.auto_queries(set(), 6)
    assert got == [
        "dentist in Austin TX",
        "lawyer in Austin TX",
        "dentist in London UK",
        "dentist in Dallas TX",
        "lawyer in Dallas TX",
        "lawyer in London UK",
    ]


def test_auto_queries_skip_done_and_stop_when_exhausted(workspace):
    done = {"dentist in Austin TX", "dentist in London UK"}
    got = google_maps.auto_queries(set(done), 99)
    assert not (set(got) & done)
    assert len(got) == 4  # 6 combinations minus 2 done


def test_auto_queries_disabled(workspace):
    from openprospect.core import config

    config.settings()["scrape"]["auto_queries"]["enabled"] = False
    assert google_maps.auto_queries(set(), 5) == []


def test_pending_queries_prefers_queries_file_and_caps(conn, workspace):
    (workspace / "config" / "queries.txt").write_text(
        "# comment\nplumber in Boise ID\n\nroofer in Boise ID\n", encoding="utf-8"
    )
    conn.execute("INSERT INTO done_queries(query, done_at) VALUES ('roofer in Boise ID', 'x')")
    todo = google_maps.pending_queries(conn)
    assert todo[0] == "plumber in Boise ID"
    assert "roofer in Boise ID" not in todo
    assert len(todo) == 5  # topped up with auto queries up to max_queries_per_run


def test_load_csv(conn, tmp_path):
    path = tmp_path / "gmaps.csv"
    fields = [
        "place_id",
        "title",
        "category",
        "address",
        "complete_address",
        "website",
        "phone",
        "emails",
        "review_rating",
        "review_count",
        "status",
        "link",
        "input_id",
        "timezone",
    ]
    rows = [
        {
            "place_id": "p1",
            "title": "Bright Smile Dental",
            "category": "Dentist",
            "address": "500 Main St, Austin, TX 78701",
            "complete_address": json.dumps({"city": "Austin", "country": "us"}),
            "website": "brightsmile.com",
            "phone": "(512) 555-0123",
            "emails": "Info@BrightSmile.com, noreply@brightsmile.com",
            "review_rating": "4.8",
            "review_count": "212",
            "status": "",
            "link": "https://maps/p1",
            "input_id": "dentist in Austin TX",
            "timezone": "America/Chicago",
        },
        {"place_id": "p2", "title": "Gone Dental", "status": "Permanently closed"},
        {"place_id": "", "title": "No id"},
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    new, total = google_maps.load_csv(conn, path, ["dentist in Austin TX"])
    assert (new, total) == (1, 3)
    lead = conn.execute("SELECT * FROM leads").fetchone()
    assert lead["source_id"] == "gmaps:p1"
    assert lead["website"] == "http://brightsmile.com" and lead["domain"] == "brightsmile.com"
    assert lead["country"] == "US" and lead["city"] == "Austin"
    assert lead["rating"] == 4.8 and lead["reviews"] == 212
    assert db.loads(lead["emails"], []) == ["info@brightsmile.com"]
    assert conn.execute("SELECT COUNT(*) FROM done_queries").fetchone()[0] == 1

    assert google_maps.load_csv(conn, path, []) == (0, 3)  # same file again: nothing new


def test_parse_profile(tmp_path):
    p = tmp_path / "acme.md"
    p.write_text(
        """---
title: Acme Corp
website: https://acme.io
company_size: small
technologies:
  - Python
  - React
---

## Company blurb

Acme builds widgets for remote teams.

## Remote status

Fully remote.
""",
        encoding="utf-8",
    )
    meta = parse_profile(p)
    assert meta["title"] == "Acme Corp"
    assert meta["website"] == "https://acme.io"
    assert meta["technologies"] == ["Python", "React"]
    assert meta["blurb"] == "Acme builds widgets for remote teams."


def test_parse_profile_without_front_matter(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("# just markdown\n", encoding="utf-8")
    assert parse_profile(p) is None


def test_each_install_gets_its_own_huginn_feed_secret(workspace, monkeypatch):
    import shutil
    from pathlib import Path

    from openprospect.sources import buyer_intent

    repo_infra = Path(__file__).resolve().parents[3] / "infra"
    shutil.copytree(repo_infra, workspace / "infra")
    scenario = buyer_intent.scenario_file().read_text(encoding="utf-8")
    assert buyer_intent.PLACEHOLDER_SECRET in scenario  # the shipped file only has the placeholder

    monkeypatch.setenv("HUGINN_FEED_SECRET", "s3cret-xyz")
    assert buyer_intent.feed_secret() == "s3cret-xyz"
    imported = scenario.replace(buyer_intent.PLACEHOLDER_SECRET, buyer_intent.feed_secret())
    assert "s3cret-xyz" in imported and buyer_intent.PLACEHOLDER_SECRET not in imported
