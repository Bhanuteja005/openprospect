import pytest

from openprospect.verify import reacher
from openprospect.verify.reacher import Verifier


@pytest.fixture
def offline_verifier(workspace, monkeypatch):
    """Reacher not running; MX exists for every domain except nomx.test."""
    monkeypatch.setattr(reacher, "is_up", lambda *a, **k: False)
    monkeypatch.setattr(reacher, "has_mx", lambda d: d != "nomx.test")
    return Verifier()


def test_own_domain_found_on_site_is_sendable(offline_verifier):
    assert offline_verifier.check("info@acme.com", found_on_site=True, site_domain="acme.com") == "site_mx_ok"
    assert offline_verifier.check("info@mail.acme.com", found_on_site=True, site_domain="acme.com") == "site_mx_ok"


def test_free_mail_found_on_site_is_sendable(offline_verifier):
    assert offline_verifier.check("acmeclinic@gmail.com", found_on_site=True, site_domain="acme.com") == "site_mx_ok"


def test_foreign_domain_is_unknown(offline_verifier):
    # e.g. a chain's head-office address listed on a branch site
    assert offline_verifier.check("care@chain.com", found_on_site=True, site_domain="acme.com") == "unknown"


def test_guessed_address_is_never_trusted_without_reacher(offline_verifier):
    assert offline_verifier.check("info@acme.com", found_on_site=False, site_domain="acme.com") == "unknown"


def test_invalid_for_disposable_or_no_mx(offline_verifier):
    assert offline_verifier.check("a@mailinator.com", found_on_site=True) == "invalid"
    assert offline_verifier.check("a@nomx.test", found_on_site=True, site_domain="nomx.test") == "invalid"


def test_reacher_unknown_streak_disables_it(workspace, monkeypatch):
    monkeypatch.setattr(reacher, "is_up", lambda *a, **k: True)
    monkeypatch.setattr(reacher, "has_mx", lambda d: True)

    class Resp:
        def json(self):
            return {"is_reachable": "unknown"}

    calls = []
    monkeypatch.setattr(reacher.requests, "post", lambda *a, **k: calls.append(1) or Resp())
    v = Verifier()
    for _ in range(5):
        v.check("x@acme.com", found_on_site=True, site_domain="acme.com")
    assert v.reacher_works is False
    assert len(calls) == 3  # stops asking once port 25 looks blocked


def test_reacher_safe_wins(workspace, monkeypatch):
    monkeypatch.setattr(reacher, "is_up", lambda *a, **k: True)
    monkeypatch.setattr(reacher, "has_mx", lambda d: True)

    class Resp:
        def json(self):
            return {"is_reachable": "safe"}

    monkeypatch.setattr(reacher.requests, "post", lambda *a, **k: Resp())
    assert Verifier().check("guess@acme.com", found_on_site=False, site_domain="acme.com") == "safe"
