"""Who we may email about a job. The hard rule the sender enforces on every draft.

  person   a named HR / recruiter / founder / CEO / CTO / director (role checked, never guessed)
  hiring   careers@, jobs@, hiring@, talent@, recruiting@, hr@, people@ ...
  hello    hello@ when nothing above exists
  generic  info@, contact@, team@, engineering@ ... as a last resort

Support-type inboxes (support@, help@, billing@, noreply@, privacy@ ...) are never emailed."""

from __future__ import annotations

import re

from openprospect.core.text import FREE_MAIL

HIRING = {
    "careers",
    "career",
    "jobs",
    "job",
    "hiring",
    "talent",
    "recruiting",
    "recruitment",
    "recruiter",
    "recruiters",
    "hr",
    "people",
    "join",
    "joinus",
    "join-us",
    "work",
    "workwithus",
    "apply",
    "applications",
    "resumes",
    "resume",
    "cv",
    "humanresources",
}
HELLO = {"hello", "hi", "hey"}
GENERIC = {
    "info",
    "support",
    "help",
    "contact",
    "contactus",
    "sales",
    "team",
    "press",
    "media",
    "admin",
    "billing",
    "accounts",
    "office",
    "enquiries",
    "enquiry",
    "inquiries",
    "inquiry",
    "marketing",
    "partners",
    "partnerships",
    "privacy",
    "legal",
    "security",
    "abuse",
    "noreply",
    "no-reply",
    "donotreply",
    "webmaster",
    "feedback",
    "service",
    "customerservice",
    "care",
    "orders",
    "shop",
    "store",
    "newsletter",
    "events",
    "community",
    "success",
    "ops",
    "operations",
    "finance",
    "invoice",
    "invoices",
    "developers",
    "dev",
    "api",
    "status",
    "general",
    "mail",
    "email",
    "connect",
    "social",
    "news",
    "pr",
    "compliance",
    "dpo",
    "gdpr",
    "investors",
    "ir",
    "studio",
    "design",
    "editor",
    "editorial",
    "membership",
    "members",
    "booking",
    "bookings",
    "reception",
    "frontdesk",
    "it",
    "tech",
    "engineering",
    "product",
}
GENERIC_PREFIXES = (
    "support",
    "info",
    "help",
    "contact",
    "sales",
    "noreply",
    "no-reply",
    "billing",
    "privacy",
    "legal",
    "press",
    "marketing",
    "partner",
)
PERSON_ROLE_RE = re.compile(
    r"\b(founder|co-?founder|ceo|cto|coo|chief|director|head of|vp|vice president|president|"
    r"owner|managing partner|partner|hr|human resources|recruit\w*|talent|people (ops|team|partner)|"
    r"hiring manager|engineering manager)\b",
    re.I,
)
SUPPORT_RE = re.compile(
    r"^(support|help|helpdesk|care|customercare|customerservice|service|noreply|no-reply|donotreply|"
    r"billing|invoice|privacy|legal|abuse|security|gdpr|dpo|orders|press|media|newsletter|webmaster|"
    r"postmaster|accounts|accounting|finance|investors|ir|unsubscribe)(?![a-z])",
    re.I,
)


def kind_of(addr: str) -> str:
    """'person' | 'hiring' | 'hello' | 'generic' from the local part alone."""
    local = addr.split("@", 1)[0].lower()
    base = local.split("+", 1)[0]
    if base in HIRING or base.startswith(("careers", "jobs", "hiring", "talent", "recruit")):
        return "hiring"
    if base in HELLO:
        return "hello"
    if base in GENERIC or base.startswith(GENERIC_PREFIXES):
        return "generic"
    if re.fullmatch(r"[a-z]{2,}([._-][a-z]{1,})?\d{0,2}", base):
        return "person"
    return "generic"


def blocked(addr: str) -> bool:
    """Support-type inboxes we never email (everything else published is fair game)."""
    return bool(SUPPORT_RE.match(addr.split("@", 1)[0]))


def allowed_recipient(addr: str, role: str = "", from_posting: bool = False) -> tuple[bool, str]:
    """Returns (ok, reason)."""
    addr = (addr or "").strip().lower()
    if "@" not in addr:
        return False, "no address"
    k = kind_of(addr)
    dom = addr.split("@", 1)[1]
    if blocked(addr):
        return False, "support-type inbox (support/help/billing/noreply/...)"
    if k == "generic":
        return (dom not in FREE_MAIL), ("ok" if dom not in FREE_MAIL else "free-mail shared inbox")
    if k in ("hiring", "hello"):
        return (dom not in FREE_MAIL), ("ok" if dom not in FREE_MAIL else "free-mail role inbox")
    # person: must have a qualifying role; free-mail only if the poster put it in the job post
    if not PERSON_ROLE_RE.search(role or ""):
        return False, "person without HR/founder/CEO/director role"
    if dom in FREE_MAIL and not from_posting:
        return False, "personal free-mail not published for hiring"
    return True, "ok"
