"""Turns website signals into "pain points": problems a freelancer or agency can fix.
Each one has a weight in scoring, a first line and a subject in openprospect.scoring.copy,
and an offer sentence in settings.yaml (`offers:`)."""

from __future__ import annotations

from openprospect.core.config import settings

from .signals import version_tuple


def pain_points(lead, sig: dict) -> list[str]:
    cfg = settings().get("enrich", {})
    pts: list[str] = []
    if not lead["website"]:
        return ["no_website"] if lead["source"] == "google_maps" else []
    if not sig.get("site_ok"):
        err = sig.get("site_error")
        if err == "ssl":
            return ["bad_ssl"]
        if err == "blocked":  # it works for people, it just blocks our reader
            return []
        return ["site_down"]
    if sig.get("ssl_broken"):
        pts.append("bad_ssl")
    elif not sig.get("https"):
        pts.append("no_https")
    else:
        days = sig.get("ssl_days_left")
        if days is not None and 0 <= days <= 21:
            pts.append("ssl_expiring")
        if sig.get("tls_version") in ("TLSv1", "TLSv1.1", "SSLv3"):
            pts.append("old_tls")
        if sig.get("http_redirects_to_https") is False:
            pts.append("no_https_redirect")
        if sig.get("mixed_content"):
            pts.append("mixed_content")
    wp = sig.get("wordpress_version")
    if wp and version_tuple(wp) < (6, 0):
        pts.append("outdated_wordpress")
    jq = sig.get("jquery_version")
    if jq and version_tuple(jq) < (3, 5, 0):
        pts.append("old_jquery")
    php = sig.get("php_version")
    if php and version_tuple(php) < (8, 1):
        pts.append("old_php")
    if not sig.get("mobile_viewport"):
        pts.append("not_mobile")
    if sig.get("load_seconds") and sig["load_seconds"] > float(cfg.get("slow_site_seconds", 4)):
        pts.append("slow_site")
    yr = sig.get("copyright_year")
    if yr and yr < int(cfg.get("outdated_year_before", 2023)):
        pts.append("outdated_site")
    if not sig.get("booking") and not sig.get("chat_widget") and lead["source"] == "google_maps":
        pts.append("no_booking")
    if not sig.get("analytics"):
        pts.append("no_analytics")
    if lead["rating"] and lead["reviews"] and lead["rating"] < 4.0 and lead["reviews"] >= 5:
        pts.append("low_rating")
    return pts
