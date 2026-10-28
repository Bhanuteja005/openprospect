"""Finding people: published addresses from the posting itself, then the company's own pages.
Nothing is guessed; every address comes with the page it was found on."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from openprospect.core.text import FREE_MAIL, clean_emails, domain_of

from .boards import plain
from .recipients import blocked, kind_of

SKIP_LINK_DOMAINS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workable.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "github.com",
    "news.ycombinator.com",
    "remotive.com",
    "remoteok.com",
    "himalayas.app",
    "weworkremotely.com",
    "wellfound.com",
    "angel.co",
    "breezy.hr",
    "recruitee.com",
    "bamboohr.com",
    "smartrecruiters.com",
    "jobs.",
    "apply.",
    "forms.gle",
    "google.com",
    "notion.site",
    "calendly.com",
    "youtube.com",
    "medium.com",
    "bit.ly",
    "typeform.com",
    "workatastartup.com",
)
PAGES = [
    "",
    "about",
    "about-us",
    "team",
    "our-team",
    "company",
    "people",
    "leadership",
    "careers",
    "jobs",
    "join",
    "join-us",
    "contact",
]


def company_domain(p: dict) -> str:
    if p.get("website"):
        return domain_of(p["website"])
    for e in clean_emails(p["text"]):
        d = e.split("@", 1)[1]
        if d not in FREE_MAIL:
            return d
    for u in re.findall(r"https?://[^\s<>\"')]+", p["text"]):
        d = domain_of(u)
        if d and not any(x in d for x in SKIP_LINK_DOMAINS):
            return d
    d = domain_of(p.get("apply_url"))
    if d and not any(x in d for x in SKIP_LINK_DOMAINS):
        return d
    return ""


def _snippet(text: str, needle: str, width: int = 140) -> str:
    i = text.lower().find(needle.lower())
    if i < 0:
        return ""
    return re.sub(r"\s+", " ", text[max(0, i - width) : i + len(needle) + width]).strip()


def harvest(s, p: dict) -> list[dict]:
    """Emails from the posting itself, then from the company's own pages."""
    found: dict[str, dict] = {}
    for e in clean_emails(p["text"]):
        found[e] = {
            "email": e,
            "kind": kind_of(e),
            "where": p["url"],
            "from_posting": True,
            "context": _snippet(p["text"], e),
        }
    dom = p.get("domain")
    if dom:
        for path in PAGES:
            url = urljoin(f"https://{dom}/", path)
            try:
                r = s.get(url, timeout=12)
            except Exception:  # noqa: BLE001
                continue
            if r.status_code >= 400 or "text/html" not in r.headers.get("content-type", ""):
                continue
            text = plain(r.text)
            for e in clean_emails(r.text):
                ed = e.split("@", 1)[1]
                if e in found or not (ed == dom or ed.endswith("." + dom)):
                    continue
                found[e] = {
                    "email": e,
                    "kind": kind_of(e),
                    "where": url,
                    "from_posting": False,
                    "context": _snippet(text, e),
                }
    return [f for f in found.values() if not blocked(f["email"])]
