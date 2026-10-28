from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from openprospect.core import config
from openprospect.mail import sequence
from openprospect.mail.replies import OPT_OUT, _fresh_part
from openprospect.mail.templates import attribs_for, render_body


def _freeze(monkeypatch, local: datetime):
    """Make sequence.datetime.now() return `local` (converted to whatever tz is asked for)."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return local.astimezone(tz) if tz else local.replace(tzinfo=None)

    monkeypatch.setattr(sequence, "datetime", Frozen)
    monkeypatch.setattr(sequence.random, "randint", lambda a, b: 15)


NY = ZoneInfo("America/New_York")


def test_send_time_now_during_business_hours(workspace, monkeypatch):
    _freeze(monkeypatch, datetime(2026, 10, 28, 11, 0, tzinfo=NY))  # Wednesday 11:00
    assert sequence.send_time("America/New_York") is None


def test_send_time_before_hours_is_same_morning(workspace, monkeypatch):
    _freeze(monkeypatch, datetime(2026, 10, 28, 7, 0, tzinfo=NY))  # Wednesday 07:00
    at = sequence.send_time("America/New_York").astimezone(NY)
    assert (at.date().isoformat(), at.hour, at.minute) == ("2026-10-28", 9, 15)


def test_send_time_friday_evening_moves_to_monday(workspace, monkeypatch):
    _freeze(monkeypatch, datetime(2026, 10, 30, 18, 0, tzinfo=NY))  # Friday 18:00
    at = sequence.send_time("America/New_York")
    assert at.tzinfo == UTC
    local = at.astimezone(NY)
    assert (local.strftime("%A"), local.hour, local.minute) == ("Monday", 9, 15)


def test_send_time_weekend_moves_to_monday(workspace, monkeypatch):
    _freeze(monkeypatch, datetime(2026, 10, 31, 10, 0, tzinfo=NY))  # Saturday 10:00
    assert sequence.send_time("America/New_York").astimezone(NY).strftime("%A %d") == "Monday 02"


@pytest.mark.parametrize(
    ("country", "tz", "expected"),
    [
        ("US", "America/New_York", "America/New_York"),
        ("US", "America/Indiana/Indianapolis", "America/New_York"),
        ("US", "America/Denver", "America/Chicago"),
        ("US", "", "America/Chicago"),
        ("GB", "", "Europe/London"),
        ("AU", "Australia/Perth", "Australia/Perth"),
        ("", "Not/AZone", "UTC"),
        ("Europe", "", "Europe/London"),
    ],
)
def test_lead_tz(make_lead, country, tz, expected):
    assert sequence.lead_tz(make_lead(country=country, timezone=tz)) == expected


def test_render_body_fills_agency_placeholders(workspace):
    body = render_body(1)
    assert "[[" not in body
    assert "I'm Alex, a web developer." in body
    assert "Alex Rivera" in body
    assert "teststudio.example" in body and "https://" not in body
    assert "1 Test Street, Testville" in body
    assert "{{ .Subscriber.Attribs.first_line }}" in body  # left for Listmonk


def test_render_body_drops_empty_postal_address(workspace):
    s = config.settings()
    s["agency"]["postal_address"] = ""
    for step in (1, 2, 3):
        body = render_body(step)
        assert "[[" not in body
        assert 'color:#888;"></p>' not in body


def test_attribs_for(make_lead):
    lead = make_lead(
        name="Bright Smile Dental - Implants",
        icebreaker="Hi there.",
        signals={"offer": "I fix sites.", "subject": "bright smile website", "problem": "the website"},
    )
    a = attribs_for(lead)
    assert a["business"] == "Bright Smile Dental"
    assert a["first_line"] == "Hi there."
    assert a["subject"] == "bright smile website"
    assert a["short"] == "Bright Smile Dental"
    assert a["lead_id"] == lead["id"]


def test_fresh_part_strips_quoted_original():
    body = "Sounds good, call me Tuesday.\n> earlier text\n\nOn Mon, Oct 26, 2026 at 9:00 AM Alex wrote:\n> Hi team"
    assert _fresh_part(body) == "Sounds good, call me Tuesday."
    assert _fresh_part("Yes please\n-----Original Message-----\nFrom: x") == "Yes please"


@pytest.mark.parametrize(
    "text",
    ["Please unsubscribe me", "not interested, thanks", "No thanks!", "don't email me again", "Take me off your list"],
)
def test_opt_out_detected(text):
    assert OPT_OUT.search(text)


@pytest.mark.parametrize("text", ["Yes, interested! What does it cost?", "Thanks, let's talk"])
def test_normal_reply_not_opt_out(text):
    assert not OPT_OUT.search(text)
