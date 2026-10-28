import csv
import json
from datetime import UTC, datetime

import pytest

from openprospect.core import config
from openprospect.core.config import paths
from openprospect.jobs import filters, sender
from openprospect.jobs.filters import fit_score, geo_ok, role_ok
from openprospect.jobs.finder import contacted_domains, day_dir, sent_file
from openprospect.jobs.harvest import company_domain
from openprospect.jobs.recipients import allowed_recipient, blocked, kind_of


@pytest.mark.parametrize(
    ("addr", "kind"),
    [
        ("careers@acme.io", "hiring"),
        ("jobs+eng@acme.io", "hiring"),
        ("talent-team@acme.io", "hiring"),
        ("hello@acme.io", "hello"),
        ("info@acme.io", "generic"),
        ("support@acme.io", "generic"),
        ("jane.doe@acme.io", "person"),
        ("jane@acme.io", "person"),
        ("x1@acme.io", "generic"),
    ],
)
def test_kind_of(addr, kind):
    assert kind_of(addr) == kind


def test_blocked_support_type_inboxes():
    for addr in (
        "support@acme.io",
        "help@acme.io",
        "billing@acme.io",
        "noreply@acme.io",
        "privacy@acme.io",
        "Security@acme.io",
    ):
        assert blocked(addr), addr
    for addr in ("careers@acme.io", "info@acme.io", "jane@acme.io"):
        assert not blocked(addr), addr


@pytest.mark.parametrize(
    ("addr", "role", "from_posting", "ok"),
    [
        ("careers@acme.io", "", False, True),
        ("hello@acme.io", "", False, True),
        ("info@acme.io", "", False, True),
        ("support@acme.io", "", False, False),
        ("careers@gmail.com", "", False, False),  # role inbox on free mail
        ("jane@acme.io", "CTO", False, True),
        ("jane@acme.io", "Senior Engineer", False, False),  # person without a qualifying role
        ("jane.founder@gmail.com", "Founder", False, False),
        ("jane.founder@gmail.com", "Founder", True, True),  # poster published it in the job post
        ("not-an-address", "", False, False),
    ],
)
def test_allowed_recipient(addr, role, from_posting, ok):
    assert allowed_recipient(addr, role, from_posting)[0] is ok


@pytest.fixture
def default_rules(workspace):
    filters._cache = None
    yield
    filters._cache = None


@pytest.mark.parametrize(
    ("title", "ok"),
    [
        ("Senior Full Stack Engineer", True),
        ("Founding Engineer (Python)", True),
        ("React Developer", True),
        ("Sales Manager", False),
        ("Engineering Manager, Python", False),
        ("Product Designer", False),
    ],
)
def test_role_ok(default_rules, title, ok):
    assert role_ok(title) is ok


@pytest.mark.parametrize(
    ("location", "ok"),
    [
        ("Worldwide", True),
        ("Anywhere", True),
        ("", True),
        ("US only", False),
        ("USA", False),
        ("Remote (EU)", False),
        ("Europe / Worldwide", True),
        ("Berlin", False),
    ],
)
def test_geo_ok(default_rules, location, ok):
    assert geo_ok(location) is ok


def test_geo_ok_reads_restrictions_in_the_text(default_rules):
    assert geo_ok("Remote", "Applicants must reside in the US.") is False
    assert geo_ok("REMOTE", "Great team", lenient=True) is True
    assert geo_ok("REMOTE (CET)", "", lenient=True) is False


def test_rules_come_from_settings(workspace):
    config.settings()["jobs"] = {"roles": ["rust"], "open_to": ["india", "apac"], "stack": ["rust", "tokio"]}
    filters._cache = None
    assert role_ok("Rust Engineer") and not role_ok("Python Engineer")
    assert geo_ok("India") and geo_ok("APAC")
    assert fit_score("We use Rust and Tokio") == 2
    filters._cache = None


def test_company_domain_prefers_website_then_email_then_links():
    assert company_domain({"website": "https://www.acme.io", "text": ""}) == "acme.io"
    assert company_domain({"text": "email jane@gmail.com or jobs@acme.io"}) == "acme.io"
    assert company_domain({"text": "apply at https://jobs.lever.co/acme or see https://acme.dev/about"}) == "acme.dev"
    assert company_domain({"text": "nothing", "apply_url": "https://boards.greenhouse.io/acme"}) == ""


def _write_sent(rows):
    f = sent_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sender.FIELDS)
        w.writeheader()
        w.writerows(rows)


def test_contacted_domains_respects_window(workspace):
    _write_sent(
        [
            {
                "time": "2099-01-01T00:00:00+00:00",
                "id": 1,
                "company": "A",
                "to": "careers@recent.io",
                "subject": "",
                "result": "sent",
            },
            {
                "time": "2000-01-01T00:00:00+00:00",
                "id": 2,
                "company": "B",
                "to": "careers@old.io",
                "subject": "",
                "result": "sent",
            },
            {
                "time": "2099-01-01T00:00:00+00:00",
                "id": 3,
                "company": "C",
                "to": "careers@failed.io",
                "subject": "",
                "result": "error: x",
            },
        ]
    )
    assert contacted_domains() == {"recent.io"}


@pytest.fixture
def drafts(workspace, monkeypatch):
    monkeypatch.setattr(sender, "has_mx", lambda d: d != "nomx.io")
    monkeypatch.setattr(sender.time, "sleep", lambda s: None)
    d = day_dir("2026-10-28")
    d.mkdir(parents=True)
    items = [
        {"id": 1, "company": "Acme", "status": "send", "to": "careers@acme.io", "subject": "hi", "body": "b"},
        {"id": 2, "company": "Help", "status": "send", "to": "support@help.io", "subject": "hi", "body": "b"},
        {"id": 3, "company": "NoMx", "status": "send", "to": "jobs@nomx.io", "subject": "hi", "body": "b"},
        {"id": 4, "company": "Skip", "status": "skip", "to": "jobs@skip.io", "subject": "hi", "body": "b"},
        {"id": 5, "company": "Dup", "status": "send", "to": "CAREERS@acme.io", "subject": "hi", "body": "b"},
        {
            "id": 6,
            "company": "Beta",
            "status": "send",
            "to": "jane@beta.io",
            "recipient_role": "Founder",
            "subject": "hi",
            "body": "b",
        },
    ]
    (d / "drafts.json").write_text(json.dumps(items), encoding="utf-8")
    # what the scraper found for each posting: only these addresses count as published
    contacts = {1: "careers@acme.io", 2: "support@help.io", 3: "jobs@nomx.io", 5: "careers@acme.io", 6: "jane@beta.io"}
    candidates = [{"id": i, "contacts": [{"email": e}]} for i, e in contacts.items()]
    (d / "candidates.json").write_text(json.dumps(candidates), encoding="utf-8")
    (paths.config / "profile.md").write_text("# Me\nA real profile.\n", encoding="utf-8")
    monkeypatch.setattr(sender, "_sender_name", lambda: "Test Sender")
    monkeypatch.setattr(sender, "on_page", lambda url, address, s: False)
    monkeypatch.setenv("JOB_SMTP_USER", "me@mystudio.io")
    monkeypatch.setenv("JOB_SMTP_PASSWORD", "app pass word")
    return d


def test_send_dry_run_sends_nothing(drafts, monkeypatch):
    monkeypatch.setattr(sender, "send_plain", lambda *a, **k: pytest.fail("dry run must not send"))
    assert sender.send("2026-10-28", dry_run=True) == 0


def test_send_filters_and_logs_once(drafts, monkeypatch):
    sent_to = []
    monkeypatch.setattr(
        sender, "send_plain", lambda host, port, user, pw, name, to, subj, body: sent_to.append((to, pw))
    )
    assert sender.send("2026-10-28") == 2
    assert sent_to == [("careers@acme.io", "apppassword"), ("jane@beta.io", "apppassword")]
    with sent_file().open(encoding="utf-8") as fh:
        results = {r["to"]: r["result"] for r in csv.DictReader(fh)}
    assert results["support@help.io"].startswith("skipped")
    assert results["jobs@nomx.io"] == "skipped: no MX"

    sent_to.clear()
    assert sender.send("2026-10-28") == 0  # a re-run never emails anyone twice
    assert sent_to == []


def test_send_stops_at_provider_limit(drafts, monkeypatch):
    def limit(*a, **k):
        raise sender.SendingLimitReached("5.4.5 Daily user sending limit exceeded")

    monkeypatch.setattr(sender, "send_plain", limit)
    assert sender.send("2026-10-28") == 0
    with sent_file().open(encoding="utf-8") as fh:
        errors = [r for r in csv.DictReader(fh) if r["result"].startswith("error")]
    assert len(errors) == 1


def test_send_refuses_until_profile_and_sender_are_set(drafts, monkeypatch):
    monkeypatch.setattr(sender, "send_plain", lambda *a, **k: pytest.fail("must not send"))
    (paths.config / "profile.md").unlink()
    assert sender.send("2026-10-28") == 0
    (paths.config / "profile.md").write_text("x", encoding="utf-8")
    (paths.config / "profile.example.md").write_text("x", encoding="utf-8")  # unchanged from the example
    assert sender.send("2026-10-28") == 0


def _one_draft(d, item):
    (d / "drafts.json").write_text(
        json.dumps([{"status": "send", "subject": "hi", "body": "b", **item}]), encoding="utf-8"
    )


def test_send_skips_addresses_that_were_never_published(drafts, monkeypatch):
    sent_to = []
    monkeypatch.setattr(sender, "send_plain", lambda *a: sent_to.append(a[5]))
    _one_draft(drafts, {"id": 1, "company": "Acme", "to": "ceo@acme.io", "recipient_role": "CEO"})
    assert sender.send("2026-10-28") == 0
    with sent_file().open(encoding="utf-8") as fh:
        assert "not verified as published" in next(csv.DictReader(fh))["result"]


def test_send_accepts_an_address_shown_on_the_evidence_page(drafts, monkeypatch):
    sent_to = []
    monkeypatch.setattr(sender, "send_plain", lambda *a: sent_to.append(a[5]))
    monkeypatch.setattr(sender, "on_page", lambda url, address, s: url == "https://acme.io/team")
    _one_draft(
        drafts,
        {
            "id": 1,
            "company": "Acme",
            "to": "ceo@acme.io",
            "recipient_role": "CEO",
            "evidence_url": "https://acme.io/team",
        },
    )
    assert sender.send("2026-10-28") == 1
    assert sent_to == ["ceo@acme.io"]


def test_send_emails_each_company_once_per_batch(drafts, monkeypatch):
    sent_to = []
    monkeypatch.setattr(sender, "send_plain", lambda *a: sent_to.append(a[5]))
    monkeypatch.setattr(sender, "on_page", lambda url, address, s: True)
    items = [
        {"id": 1, "company": "Acme", "status": "send", "to": "careers@acme.io", "subject": "a", "body": "b"},
        {
            "id": 7,
            "company": "Acme",
            "status": "send",
            "to": "jobs@acme.io",
            "subject": "a",
            "body": "b",
            "evidence_url": "https://acme.io",
        },
    ]
    (drafts / "drafts.json").write_text(json.dumps(items), encoding="utf-8")
    assert sender.send("2026-10-28") == 1
    assert sent_to == ["careers@acme.io"]


def test_free_mail_domains_never_block_a_whole_provider(workspace):
    _write_sent(
        [
            {
                "time": datetime.now(UTC).isoformat(),
                "id": 1,
                "company": "X",
                "to": "founder@gmail.com",
                "subject": "s",
                "result": "sent",
            }
        ]
    )
    assert "gmail.com" not in contacted_domains()
