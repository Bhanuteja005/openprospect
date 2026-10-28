import pytest
import requests

from openprospect.crm import twenty
from openprospect.crm.sync import phone_fields
from openprospect.crm.twenty import Twenty


@pytest.mark.parametrize(
    ("raw", "country", "expected"),
    [
        (
            "(512) 555-0123",
            "US",
            {"primaryPhoneNumber": "5125550123", "primaryPhoneCountryCode": "US", "primaryPhoneCallingCode": "+1"},
        ),
        (
            "020 7946 0958",
            "GB",
            {"primaryPhoneNumber": "2079460958", "primaryPhoneCountryCode": "GB", "primaryPhoneCallingCode": "+44"},
        ),
        (
            "020 7946 0958",
            "UK",
            {"primaryPhoneNumber": "2079460958", "primaryPhoneCountryCode": "GB", "primaryPhoneCallingCode": "+44"},
        ),
        (
            "080 5550 1234",
            "IN",
            {"primaryPhoneNumber": "8055501234", "primaryPhoneCountryCode": "IN", "primaryPhoneCallingCode": "+91"},
        ),
        (
            "+1 512 555 0123",
            "US",
            {"primaryPhoneNumber": "5125550123", "primaryPhoneCountryCode": "US", "primaryPhoneCallingCode": "+1"},
        ),
        ("+44 20 7946 0958", "US", {"primaryPhoneNumber": "2079460958", "primaryPhoneCallingCode": "+44"}),
        ("", "US", {}),
    ],
)
def test_phone_fields(workspace, raw, country, expected):
    assert phone_fields(raw, country) == expected


def test_phone_fields_defaults_to_agency_country(workspace):
    assert phone_fields("(512) 555-0123")["primaryPhoneCallingCode"] == "+1"


class FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


@pytest.fixture
def client(workspace, monkeypatch):
    monkeypatch.setenv("TWENTY_API_KEY", "k")
    sleeps = []
    monkeypatch.setattr(twenty.time, "sleep", sleeps.append)
    t = Twenty()
    t.sleeps = sleeps
    return t


def test_req_retries_after_429(client, monkeypatch):
    answers = iter([FakeResp(429), FakeResp(429), FakeResp(200, {"data": {"createCompany": {"id": "c1"}}})])
    monkeypatch.setattr(twenty.requests, "request", lambda *a, **k: next(answers))
    assert client.create("companies", {"name": "Acme"}) == "c1"
    assert 20 in client.sleeps and 40 in client.sleeps


def test_req_retries_after_timeout(client, monkeypatch):
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise requests.Timeout("slow")
        return FakeResp(200, {"data": {"id": "p1"}})

    monkeypatch.setattr(twenty.requests, "request", flaky)
    assert client.create("people", {}) == "p1"
    assert len(calls) == 2 and 10 in client.sleeps


def test_req_gives_up_after_repeated_timeouts(client, monkeypatch):
    def always_slow(*a, **k):
        raise requests.Timeout("slow")

    monkeypatch.setattr(twenty.requests, "request", always_slow)
    with pytest.raises(requests.Timeout):
        client.create("people", {})


def test_create_returns_none_on_error(client, monkeypatch):
    monkeypatch.setattr(twenty.requests, "request", lambda *a, **k: FakeResp(400, {"error": "duplicate entry"}))
    assert client.create("companies", {}, quiet_duplicate=True) is None


def test_id_finds_nested_record():
    assert Twenty._id({"data": {"createOpportunity": {"id": "o9", "name": "x"}}}) == "o9"
    assert Twenty._id({"data": {}}) is None
