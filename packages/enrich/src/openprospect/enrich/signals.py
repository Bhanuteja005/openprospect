"""What a page tells us: emails, socials, site builder, analytics / ad pixels, booking, chat,
copyright year, and passive security findings (certificate, TLS, outdated software)."""

from __future__ import annotations

import re
from datetime import UTC
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from openprospect.core.text import clean_emails

CONTACT_HINTS = ("contact", "about", "team", "reach", "enquir", "inquir", "appointment", "book", "location")

TECH_MARKERS = {
    "wordpress": ("wp-content", "wp-includes"),
    "wix": ("wixstatic.com", "wix.com"),
    "shopify": ("cdn.shopify.com", "myshopify.com"),
    "squarespace": ("squarespace.com", "static1.squarespace"),
    "webflow": ("webflow.com", "assets.website-files.com"),
    "godaddy_builder": ("img1.wsimg.com", "websitebuilder"),
    "react_or_next": ("__next", "_next/static", "react"),
}
ANALYTICS = (
    "googletagmanager.com",
    "google-analytics.com",
    "gtag",
    "gtm.js",
    "analytics.js",
    "clarity.ms",
    "hotjar",
    "matomo",
    "plausible",
    "umami",
    "segment.com",
    "mixpanel",
    "posthog",
)
ADS_PIXELS = ("connect.facebook.net", "fbq(", "googleadservices", "AW-", "linkedin.com/insight", "snap.licdn")
BOOKING = (
    "calendly.com",
    "practo.com",
    "setmore",
    "zocdoc",
    "acuityscheduling",
    "simplybook",
    "booksy",
    "fresha.com",
    "squareup.com/appointments",
    "book an appointment",
    "book appointment",
    "book now",
    "schedule an appointment",
    "request an appointment",
    "booking",
    "reserve a table",
    "opentable",
    "dineout",
    "zomato.com/book",
)
CHAT = (
    "tawk.to",
    "intercom",
    "crisp.chat",
    "drift.com",
    "zendesk",
    "wa.me/",
    "api.whatsapp.com",
    "livechat",
    "tidio",
    "freshchat",
)
SOCIAL = {
    "facebook": "facebook.com/",
    "instagram": "instagram.com/",
    "linkedin": "linkedin.com/",
    "twitter": ("twitter.com/", "x.com/"),
    "youtube": "youtube.com/",
}


def _visible_text(soup: BeautifulSoup) -> str:
    for t in soup(["script", "style", "noscript"]):
        t.extract()
    return " ".join(soup.get_text(" ").split())


def analyse_html(html: str, base_url: str) -> dict:
    low = html.lower()
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    desc_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})

    links = []
    mailtos = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            mailtos.append(href[7:].split("?")[0])
        else:
            links.append(urljoin(base_url, href))

    socials = {}
    for name, marker in SOCIAL.items():
        markers = marker if isinstance(marker, tuple) else (marker,)
        for link in links:
            if any(m in link.lower() for m in markers) and "share" not in link.lower():
                socials[name] = link
                break

    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", low)]
    text = _visible_text(soup)
    emails = clean_emails(mailtos + clean_emails(text) + clean_emails(html))

    return {
        "title": title[:200],
        "meta_description": (desc_tag.get("content", "") if desc_tag else "")[:300],
        "mobile_viewport": viewport is not None,
        "tech": [k for k, marks in TECH_MARKERS.items() if any(m.lower() in low for m in marks)],
        "analytics": any(m.lower() in low for m in ANALYTICS),
        "ads_pixel": any(m.lower() in low for m in ADS_PIXELS),
        "booking": any(m in low for m in BOOKING),
        "chat_widget": any(m in low for m in CHAT),
        "copyright_year": max(years) if years else None,
        "socials": socials,
        "emails": emails,
        "links": links,
        "text_sample": text[:600],
    }


def ssl_days_left(host: str) -> int | None:
    """Days until the site's SSL certificate expires. None = unknown."""
    import socket
    import ssl
    from datetime import datetime

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=6) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as s:
                not_after = s.getpeercert()["notAfter"]
        exp = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
        return (exp - datetime.now(UTC)).days
    except Exception:
        return None


def version_tuple(s: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3])


def security_findings(reader, final_url: str, html: str, headers: dict) -> dict:
    """Real problems any visitor's browser can see. PASSIVE ONLY: we load the page and the
    certificate exactly like a normal visitor. No hidden paths, no PUT/DELETE, no probing.
    Ignores the 'missing security header' noise that every scanner repeats."""
    low = html.lower()
    out: dict = {}
    host = urlparse(final_url).hostname or ""

    if final_url.startswith("https://") and host:
        days = ssl_days_left(host)
        if days is not None:
            out["ssl_days_left"] = days
        tls = getattr(reader, "last_tls", None)
        if tls:
            out["tls_version"] = tls
        try:  # does typing the plain address move visitors to the secure version?
            r = reader.s.get(f"http://{host}/", timeout=reader.timeout, allow_redirects=True)
            out["http_redirects_to_https"] = r.url.startswith("https://")
        except requests.RequestException:
            pass
        # secure page that loads scripts/frames over plain http: browsers block them
        out["mixed_content"] = bool(re.search(r'<(?:script|iframe)[^>]+src=["\']http://', low))

    m = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']wordpress\s+([\d.]+)', low)
    if m:
        out["wordpress_version"] = m.group(1)

    # jQuery below 3.5.0 has publicly known XSS issues (CVE-2020-11022 / CVE-2020-11023)
    m = re.search(r"jquery[-.](\d+\.\d+\.\d+)(?:\.min)?\.js", low) or re.search(
        r"jquery(?:\.min)?\.js\?ver=(\d+\.\d+\.\d+)", low
    )
    if m:
        out["jquery_version"] = m.group(1)

    powered = (headers.get("X-Powered-By") or headers.get("x-powered-by") or "").lower()
    m = re.search(r"php/(\d+\.\d+)", powered)
    if m:
        out["php_version"] = m.group(1)
    return out


def contact_pages(links: list[str], home: str, limit: int) -> list[str]:
    host = urlparse(home).hostname
    seen, out = set(), []
    for link in links:
        p = urlparse(link)
        if p.hostname != host or not any(h in p.path.lower() for h in CONTACT_HINTS):
            continue
        clean = p._replace(fragment="", query="").geturl()
        if clean not in seen:
            seen.add(clean)
            out.append(clean)
        if len(out) >= limit:
            break
    return out
