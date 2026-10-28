"""Text helpers: URLs and domains, email extraction and ranking, business names."""

from __future__ import annotations

import re
from urllib.parse import urlparse


def normalize_url(url: str | None) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def domain_of(url: str | None) -> str:
    url = normalize_url(url)
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


# Free mail providers: fine to email, but they don't tell us the business domain.
FREE_MAIL = {
    "gmail.com",
    "yahoo.com",
    "yahoo.co.in",
    "yahoo.co.uk",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "rediffmail.com",
    "icloud.com",
    "aol.com",
    "protonmail.com",
    "proton.me",
    "zoho.com",
    "ymail.com",
    "msn.com",
    "gmx.com",
    "mail.com",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,24}")

_JUNK_PARTS = (
    "example.",
    "sentry",
    "wixpress",
    "domain.com",
    "yourdomain",
    "email.com",
    "mysite",
    "godaddy",
    "@2x",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    "u003e",
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "@sentry",
    "cloudflare",
    "schema.org",
    "w3.org",
    "bootstrap",
    "jquery",
    "privacy@",
    "abuse@",
    "postmaster@",
    "hostmaster@",
    "webmaster@",
    "@email.",
    "test@",
    "name@",
    "user@",
    "@company.",
)


def clean_emails(raw) -> list[str]:
    """Find, lowercase, de-junk and de-duplicate emails from text or a list."""
    if isinstance(raw, (list, tuple, set)):
        text = " ".join(str(x) for x in raw)
    else:
        text = str(raw or "")
    out: list[str] = []
    for m in EMAIL_RE.findall(text):
        e = m.strip(".").lower()
        if any(j in e for j in _JUNK_PARTS):
            continue
        if e not in out:
            out.append(e)
    return out


ROLE_PREFERENCE = [
    "owner",
    "founder",
    "ceo",
    "director",
    "doctor",
    "dr",
    "info",
    "contact",
    "hello",
    "enquiry",
    "enquiries",
    "inquiry",
    "office",
    "admin",
    "sales",
    "appointments",
    "reception",
    "booking",
    "support",
]


def pick_best_email(emails: list[str], site_domain: str) -> str:
    """Prefer a personal address on the business's own domain, then role addresses
    on their domain, then free-mail addresses (gmail etc.)."""
    if not emails:
        return ""

    def rank(e: str) -> tuple:
        local, _, dom = e.partition("@")
        on_domain = bool(site_domain) and (dom == site_domain or dom.endswith("." + site_domain))
        free = dom in FREE_MAIL
        role_idx = next((i for i, r in enumerate(ROLE_PREFERENCE) if local.startswith(r)), None)
        personal = role_idx is None and not free
        return (
            0 if on_domain else (1 if free else 2),
            0 if personal else 1,
            role_idx if role_idx is not None else 99,
            len(e),
        )

    return sorted(emails, key=rank)[0]


def short_name(name: str | None) -> str:
    """Google Maps names are often stuffed with keywords:
    'Bright Smile Dental - Downtown - Implants & Aligners' -> 'Bright Smile Dental'."""
    name = (name or "").strip()
    for sep in (" - ", " | ", " – ", " — ", ": ", " ("):
        if sep in name:
            head = name.split(sep, 1)[0].strip()
            if len(head) >= 3:
                name = head
    if "," in name and len(name.split(",", 1)[0]) >= 3:
        name = name.split(",", 1)[0].strip()
    if name.isupper() and len(name) > 4:  # "DR. SMITH'S DENTAL CARE" -> "Dr. Smith's Dental Care"
        name = " ".join(w.capitalize() for w in name.split())
    return name


def subject_name(name: str | None) -> str:
    """Short enough for a 2-4 word subject line:
    'Lakeside Family Dental & Orthodontics Center' -> 'Lakeside Family'."""
    n = short_name(name)
    if len(n) > 24:
        words = n.split()
        # keep titles + initials with the real name: 'Dr J Patel Dental Studio' -> 'Dr J Patel'
        keep = 2
        while keep < len(words) and (
            len(words[keep - 1].strip(".")) <= 2 or words[keep - 2].rstrip(".").lower() in ("dr", "mr", "mrs", "ms")
        ):
            keep += 1
        n = " ".join(words[:keep])
    return re.sub(r"'s$", "", n)


def possessive(name: str) -> str:
    return name + ("'" if name.endswith("s") else "'s")


def city_from_address(address: str) -> str:
    """Best effort: '500 Main St, Austin, TX 78701' -> 'Austin'."""
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    if len(parts) >= 3:
        return re.sub(r"\d", "", parts[-2]).strip() or parts[-3]
    if len(parts) == 2:
        return re.sub(r"\d", "", parts[0]).strip()
    return ""
