"""The words: the personalised first line ("icebreaker"), the subject and the problem phrase
for each pain point, plus optional local-AI first lines via Ollama (https://ollama.com).

Every line is built only from things a visitor can see on the lead's own website or Google
listing, so each claim in the email is true and checkable."""

from __future__ import annotations

import requests

from openprospect.core import db
from openprospect.core.config import settings
from openprospect.core.text import possessive, short_name

from .model import PAIN_WEIGHT

ICEBREAKERS = {
    "no_website": "I found {name} on Google Maps ({rating_text}) but couldn't find a website, "
    "so people searching for you online have nowhere to go.",
    "site_down": "I tried to visit your website today and it didn't load, so people finding you "
    "on Google may be hitting a dead end.",
    "bad_ssl": 'I tried to open your website and my browser showed a "Your connection is not private" '
    "warning. That scares a lot of visitors away before they ever call.",
    "ssl_expiring": "I noticed the security certificate on your website expires in {ssl_days} days. "
    'Once it lapses, every visitor gets a full-page "not secure" warning.',
    "old_tls": "I noticed your website still uses an old encryption setting ({tls_version}) that modern "
    "browsers flag as insecure.",
    "outdated_wordpress": "I noticed your website runs WordPress {wp_version}, which is several years out of date. "
    "Old versions are one of the most common ways small business sites get hacked.",
    "old_php": "I noticed your website's server runs PHP {php_version}, which no longer gets security updates, "
    "so known security holes stay open.",
    "old_jquery": "I noticed your website loads jQuery {jq_version}, an old version with publicly known "
    "security issues.",
    "no_https_redirect": 'When I typed your web address without https, the page opened as "Not secure" '
    "instead of switching to the secure version.",
    "mixed_content": "Your website loads some of its parts over an insecure connection, so browsers block them "
    "and parts of the page may not work for visitors.",
    "no_https": 'Your website shows a "Not secure" warning in Chrome, which makes some visitors '
    "leave before they call.",
    "not_mobile": "I opened your website on my phone and it isn't set up for mobile, which is where "
    "most people search for a {category_lc}.",
    "slow_site": "Your website took about {load_seconds} seconds to load for me, long enough for most "
    "phone visitors to give up.",
    "outdated_site": "I was on your website and noticed the footer still says {copyright_year}, "
    "so it looks like it's due a refresh.",
    "no_booking": "I noticed there's no way to book or send an enquiry on your website, so new "
    "customers have to call during working hours.",
    "no_analytics": "I had a look at your website and it doesn't seem to have any tracking set up, "
    "so it's hard to know which visitors turn into customers.",
    "low_rating": "I noticed you're at {rating} stars on Google, and a few unhappy reviews are "
    "probably hiding a lot of happy customers who never left one.",
    "default": "I came across you on Google Maps, and {rating_text} is seriously impressive.",
    "default_no_reviews": "I came across {name} while looking at {category_lc}s in {city}.",
}


NOT_CLAIMED = {"no_analytics"}

# Step-1 subject per main problem: 2-4 words, lowercase, reads like a personal note.
SUBJECTS = {
    "no_website": "{short} on google",
    "site_down": "{short} website is down",
    "bad_ssl": "{short} website warning",
    "ssl_expiring": "{short} certificate expiring",
    "old_tls": "{short} website security",
    "outdated_wordpress": "{short} website security",
    "old_php": "{short} website security",
    "old_jquery": "{short} website security",
    "no_https_redirect": "{short} website warning",
    "mixed_content": "{short} website issue",
    "no_https": "{short} website warning",
    "not_mobile": "{short} site on mobile",
    "slow_site": "{short} website speed",
    "outdated_site": "{short} website",
    "no_booking": "online bookings for {short}",
    "no_analytics": "{short} website enquiries",
    "low_rating": "{short} google reviews",
    "default": "quick idea for {short}",
}

PROBLEM_TEXT = {
    "no_website": "getting {short} a website",
    "site_down": "the website",
    "bad_ssl": "the website warning",
    "no_https": "the website warning",
    "ssl_expiring": "the certificate",
    "old_tls": "the website security",
    "outdated_wordpress": "the website security",
    "old_php": "the website security",
    "old_jquery": "the website security",
    "no_https_redirect": "the website warning",
    "mixed_content": "the website",
    "not_mobile": "the mobile site",
    "slow_site": "the website speed",
    "outdated_site": "the website",
    "no_booking": "online bookings",
    "no_analytics": "website enquiries",
    "low_rating": "your Google reviews",
    "default": "this",
}


def _fmt_vars(lead) -> dict:
    sig = db.loads(lead["signals"], {})
    rating = lead["rating"]
    reviews = lead["reviews"]
    rating_text = f"{reviews:,} reviews at {rating} stars" if rating and reviews else "your reviews"
    category = (lead["category"] or "business").split(",")[0].strip()
    name = short_name(lead["name"]) or "your business"
    return {
        "name": name,
        "names": possessive(name),
        "city": lead["city"] or "your area",
        "rating": rating or "",
        "rating_text": rating_text,
        "category_lc": category.lower(),
        "load_seconds": sig.get("load_seconds") or "several",
        "copyright_year": sig.get("copyright_year") or "an old year",
        "ssl_days": sig.get("ssl_days_left"),
        "tls_version": sig.get("tls_version"),
        "wp_version": sig.get("wordpress_version"),
        "php_version": sig.get("php_version"),
        "jq_version": sig.get("jquery_version"),
    }


def ai_icebreaker(lead, pain: str, offer: str) -> str | None:
    ai = settings().get("ai", {})
    if not ai.get("enabled"):
        return None
    sig = db.loads(lead["signals"], {})
    prompt = (
        "Write ONE short, friendly, specific opening sentence for a cold email to a local business owner. "
        "No greeting, no flattery overload, no emojis, max 35 words. Mention one concrete observation.\n"
        f"Business: {lead['name']} ({lead['category']}) in {lead['city'] or ''}.\n"
        f"Google rating: {lead['rating']} from {lead['reviews']} reviews.\n"
        f"Website title: {sig.get('title', '')}\nObservation to mention: {pain.replace('_', ' ')}.\n"
        f"What we can help with: {offer}."
    )
    try:
        r = requests.post(
            f"{ai.get('ollama_url', 'http://localhost:11434').rstrip('/')}/api/generate",
            json={"model": ai.get("model", "llama3.2"), "prompt": prompt, "stream": False},
            timeout=60,
        )
        text = (r.json().get("response") or "").strip().strip('"')
        return text or None
    except (requests.RequestException, ValueError):
        return None


def icebreaker_and_offer(lead) -> tuple[str, str, str]:
    pains = db.loads(lead["pain_points"], [])
    offers = settings().get("offers", {})
    # most "sellable" problem first. Some problems count toward the score but are never
    # claimed in an email, because a page can't prove them reliably (tracking can load many ways).
    claimable = [p for p in pains if p not in NOT_CLAIMED]
    pain = max(claimable, key=lambda p: PAIN_WEIGHT.get(p, 0)) if claimable else "default"
    offer = offers.get(pain) or offers.get("default", "")
    line = ai_icebreaker(lead, pain, offer)
    if not line:
        key = pain
        if pain == "default" and not (lead["reviews"] and lead["reviews"] >= 20):
            key = "default_no_reviews"
        line = ICEBREAKERS.get(key, ICEBREAKERS["default"]).format(**_fmt_vars(lead))
    return line, offer, pain
