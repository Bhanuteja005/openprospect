"""Mailbox-level checks with Reacher (https://github.com/reacherhq/check-if-email-exists).

Reacher talks to the recipient's mail server on port 25. Many home and cloud networks block
port 25; then Reacher answers "unknown" for everything and we fall back to a free check:
valid syntax + the domain has a mail server (MX record) + the address was published on the
business's own website => "site_mx_ok"."""

from __future__ import annotations

import requests

from openprospect.core.config import env
from openprospect.core.http import is_up
from openprospect.core.log import log
from openprospect.core.text import FREE_MAIL

from .mx import DISPOSABLE, has_mx


class Verifier:
    def __init__(self):
        self.url = env("REACHER_URL").rstrip("/")
        self.reacher_up = is_up(self.url, timeout=2)
        self.reacher_works: bool | None = None  # learned from the first answers
        self.unknown_streak = 0

    def reacher(self, email: str) -> str | None:
        if not self.reacher_up or self.reacher_works is False:
            return None
        try:
            r = requests.post(f"{self.url}/v0/check_email", json={"to_email": email}, timeout=90)
            status = (r.json() or {}).get("is_reachable")
        except (requests.RequestException, ValueError):
            return None
        if status in ("safe", "invalid", "risky"):
            self.reacher_works = True
            self.unknown_streak = 0
            return status
        self.unknown_streak += 1
        if self.reacher_works is None and self.unknown_streak >= 3:
            self.reacher_works = False
            log(
                "  Reacher returns 'unknown' every time: port 25 is probably blocked on this network."
                " Using the free MX check instead."
            )
        return "unknown"

    def check(self, email: str, found_on_site: bool, site_domain: str = "") -> str:
        domain = email.split("@")[-1]
        if domain in DISPOSABLE or not has_mx(domain):
            return "invalid"
        status = self.reacher(email)
        if status in ("safe", "invalid", "risky"):
            return status
        # Without a mailbox check (port 25 blocked), only trust addresses that clearly belong
        # to this business: on its own website domain, or a personal Gmail/Yahoo-type address.
        # e.g. care@bigchain.com listed on bigchain.example bounced -> 'unknown', not sent.
        own = bool(site_domain) and (domain == site_domain or domain.endswith("." + site_domain))
        if found_on_site and (own or domain in FREE_MAIL):
            return "site_mx_ok"
        return "unknown"
