"""Free checks that need no mail server access: syntax, disposable domains, MX / A records."""

from __future__ import annotations

import functools

import dns.exception
import dns.resolver

DISPOSABLE = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "yopmail.com"}


@functools.lru_cache(maxsize=4096)
def has_mx(domain: str) -> bool:
    try:
        dns.resolver.resolve(domain, "MX", lifetime=6)
        return True
    except dns.resolver.NoAnswer:
        # No MX record: mail servers then try the domain's A record (RFC 5321).
        try:
            dns.resolver.resolve(domain, "A", lifetime=6)
            return True
        except dns.exception.DNSException:
            return False
    except dns.exception.DNSException:
        return False
