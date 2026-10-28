"""The sequence must never email someone twice, after they replied, or without a postal address."""

from datetime import UTC, datetime, timedelta

import pytest

from openprospect.core import config, db
from openprospect.mail import replies, sequence
from openprospect.mail.listmonk import ListmonkError


class FakeListmonk:
    """Records calls; `campaigns` maps id -> status, or an exception to raise."""

    ok = True

    def __init__(self, campaigns=None):
        self.campaigns = campaigns or {}
        self.calls = []

    def req(self, method, path, **kw):
        self.calls.append((method, path, kw.get("json")))
        if method == "GET" and path.startswith("/campaigns/"):
            got = self.campaigns[int(path.rsplit("/", 1)[1])]
            if isinstance(got, Exception):
                raise got
            return {"status": got}
        return {}

    def remove_from_lists(self, sid, list_ids):
        self.calls.append(("REMOVE", sid, list_ids))

    def blocklist(self, sid):
        self.calls.append(("BLOCK", sid, None))


def _send_row(conn, lead_id, campaign_id, state="queued", sent_at=None, list_id=7):
    conn.execute(
        "INSERT INTO sends(lead_id, step, campaign_id, list_id, state, sent_at) VALUES (?, 1, ?, ?, ?, ?)",
        (lead_id, campaign_id, list_id, state, sent_at or db.now()),
    )
    conn.commit()


def _states(conn):
    return [r["state"] for r in conn.execute("SELECT state FROM sends ORDER BY id")]


def test_refresh_only_cancels_campaigns_that_are_really_gone(conn, make_lead):
    a, b, c = make_lead(), make_lead(), make_lead()
    _send_row(conn, a["id"], 1)
    _send_row(conn, b["id"], 2)
    _send_row(conn, c["id"], 3)
    lm = FakeListmonk({1: ListmonkError(404, "gone"), 2: ListmonkError(502, "bad gateway"), 3: "running"})
    sequence.refresh_sends(conn, lm)
    # deleted -> cancelled; a hiccup -> left alone for the next run; running -> sent
    assert _states(conn) == ["cancelled", "queued", "sent"]


def test_refresh_frees_rows_whose_campaign_was_never_created(conn, make_lead):
    lead = make_lead()
    _send_row(conn, lead["id"], None)
    sequence.refresh_sends(conn, FakeListmonk())
    assert _states(conn) == []


def test_a_reply_cancels_scheduled_and_draft_sends(conn, make_lead):
    lead = make_lead(email="owner@bright.example", listmonk_id=42, stage="emailing", seq_step=1)
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat(timespec="seconds")
    past = (datetime.now(UTC) - timedelta(days=4)).isoformat(timespec="seconds")
    _send_row(conn, lead["id"], 1, state="sent", sent_at=past, list_id=5)  # already delivered
    _send_row(conn, lead["id"], 2, state="sent", sent_at=future, list_id=6)  # scheduled, not delivered yet
    _send_row(conn, lead["id"], 3, state="queued", list_id=7)  # draft
    lm = FakeListmonk()
    replies.stop_lead(
        conn, conn.execute("SELECT * FROM leads WHERE id = ?", (lead["id"],)).fetchone(), "replied", "", lm
    )
    assert _states(conn) == ["sent", "cancelled", "cancelled"]
    assert ("REMOVE", 42, [6, 7]) in lm.calls


def test_nothing_is_sent_without_a_postal_address(workspace, conn, monkeypatch):
    path = config.paths.settings_file
    path.write_text(path.read_text(encoding="utf-8").replace("1 Test Street, Testville", ""), encoding="utf-8")
    config.reload_settings()
    monkeypatch.setenv("LISTMONK_API_USER", "api")
    monkeypatch.setenv("LISTMONK_API_TOKEN", "token")
    monkeypatch.setenv("SMTP_USER", "me@studio.example")
    monkeypatch.setattr(sequence.Listmonk, "check", lambda self: True)
    monkeypatch.setattr(sequence, "refresh_sends", lambda conn, lm: None)
    monkeypatch.setattr(sequence, "due_leads", lambda *a: pytest.fail("must stop before picking leads"))
    assert sequence.send(conn) == 0
