"""Lead scoring: who is most likely to be a high-paying client.

Score 0-100 from:
  category value   0-25  dentists, lawyers, real estate... pay more than cafes (settings.yaml)
  demand           0-20  many Google reviews = many customers = revenue
  reputation       0-10  good rating = established business
  price level      0-10  $$$ on Google Maps
  budget signals   0-10  ad pixels / analytics / paid booking tools = they already spend on marketing
  opportunity      0-20  problems on their site you can fix (pain points)
  reachability     0-5   a verified email
Tier A >= 70, B >= 50, else C (thresholds in settings.yaml).

The first line and subject of each email come from copy.py."""

from __future__ import annotations

import math

from openprospect.core import db
from openprospect.core.config import settings

PAIN_WEIGHT = {
    "no_website": 18,
    "site_down": 16,
    "bad_ssl": 12,
    "ssl_expiring": 11,
    "old_tls": 9,
    "outdated_wordpress": 10,
    "old_php": 10,
    "old_jquery": 7,
    "no_https_redirect": 7,
    "mixed_content": 6,
    "no_https": 8,
    "not_mobile": 9,
    "slow_site": 6,
    "outdated_site": 6,
    "no_booking": 5,
    "no_analytics": 3,
    "low_rating": 7,
}


def category_points(category: str) -> int:
    cfg = settings().get("scoring", {})
    cat = (category or "").lower()
    best = 0
    for key, pts in (cfg.get("category_points") or {}).items():
        if key.lower() in cat:
            best = max(best, int(pts))
    return best or int(cfg.get("default_category_points", 8))


def score_lead(lead) -> tuple[int, dict]:
    sig = db.loads(lead["signals"], {})
    pains = db.loads(lead["pain_points"], [])
    parts = {}
    parts["category"] = category_points(lead["category"])
    reviews = lead["reviews"] or 0
    # 10 reviews ~ 7 pts, 100 ~ 13, 1000 ~ 20
    parts["demand"] = min(20, round(math.log10(reviews + 1) * 6.7)) if reviews else 0
    rating = lead["rating"] or 0
    parts["reputation"] = 10 if rating >= 4.5 else 7 if rating >= 4.2 else 4 if rating >= 3.8 else 0
    pr = (lead["price_range"] or "").count("$") or (lead["price_range"] or "").count("₹")
    parts["price"] = {0: 0, 1: 2, 2: 5, 3: 8}.get(pr, 10)
    budget = 0
    budget += 4 if sig.get("ads_pixel") else 0
    budget += 2 if sig.get("analytics") else 0
    budget += 2 if sig.get("booking") else 0
    budget += 2 if sig.get("chat_widget") else 0
    if lead["source"] == "remote_companies":
        budget += {"large": 8, "medium": 6, "small": 4}.get(str(sig.get("company_size") or "").lower(), 3)
    parts["budget"] = min(10, budget)
    parts["opportunity"] = min(20, sum(PAIN_WEIGHT.get(p, 0) for p in pains))
    parts["reachability"] = 5 if lead["email_status"] in ("safe", "site_mx_ok", "risky") else 0
    return min(100, sum(parts.values())), parts


def tier_for(score: int) -> str:
    tiers = settings().get("scoring", {}).get("tiers", {"A": 70, "B": 50})
    if score >= int(tiers.get("A", 70)):
        return "A"
    if score >= int(tiers.get("B", 50)):
        return "B"
    return "C"
