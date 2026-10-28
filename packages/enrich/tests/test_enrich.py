from openprospect.enrich.pains import pain_points
from openprospect.enrich.signals import analyse_html, contact_pages, version_tuple

PAGE = """<!doctype html><html><head>
<title> Bright Smile Dental </title>
<meta name="description" content="Family dentist in Austin">
<meta name="viewport" content="width=device-width">
<script src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>
<link rel="stylesheet" href="/wp-content/themes/x/style.css">
</head><body>
<a href="https://facebook.com/brightsmile">Facebook</a>
<a href="https://facebook.com/sharer/share.php?u=x">Share</a>
<a href="https://x.com/brightsmile">X</a>
<a href="mailto:Front.Desk@BrightSmile.com?subject=hi">Email us</a>
<a href="/contact-us">Contact</a>
<p>Book an appointment online. Or write to info@brightsmile.com</p>
<footer>&copy; 2019 - 2021 Bright Smile Dental</footer>
</body></html>"""


def test_analyse_html_reads_signals():
    info = analyse_html(PAGE, "https://brightsmile.com/")
    assert info["title"] == "Bright Smile Dental"
    assert info["meta_description"] == "Family dentist in Austin"
    assert info["mobile_viewport"] is True
    assert info["analytics"] is True
    assert info["ads_pixel"] is False
    assert info["booking"] is True
    assert info["chat_widget"] is False
    assert "wordpress" in info["tech"]
    assert info["copyright_year"] == 2021
    assert info["socials"] == {"facebook": "https://facebook.com/brightsmile", "twitter": "https://x.com/brightsmile"}
    assert set(info["emails"]) == {"front.desk@brightsmile.com", "info@brightsmile.com"}
    assert "https://brightsmile.com/contact-us" in info["links"]


def test_analyse_html_empty_page():
    info = analyse_html("<html></html>", "https://a.com/")
    assert info["title"] == "" and info["copyright_year"] is None and info["emails"] == []


def test_contact_pages_same_host_only_and_deduped():
    links = [
        "https://acme.com/contact#form",
        "https://acme.com/contact?ref=nav",
        "https://acme.com/about-us",
        "https://other.com/contact",
        "https://acme.com/pricing",
        "https://acme.com/team",
    ]
    assert contact_pages(links, "https://acme.com/", 2) == ["https://acme.com/contact", "https://acme.com/about-us"]


def test_version_tuple():
    assert version_tuple("5.9.3") < (6, 0)
    assert version_tuple("3.5.1") >= (3, 5, 0)


def _lead(**kw):
    base = {"website": "https://acme.com", "source": "google_maps", "rating": 4.8, "reviews": 120}
    return {**base, **kw}


def test_pains_no_website(workspace):
    assert pain_points(_lead(website=""), {}) == ["no_website"]
    assert pain_points(_lead(website="", source="remote_companies"), {}) == []


def test_pains_site_errors(workspace):
    assert pain_points(_lead(), {"site_ok": False, "site_error": "ssl"}) == ["bad_ssl"]
    assert pain_points(_lead(), {"site_ok": False, "site_error": "blocked"}) == []  # works for people
    assert pain_points(_lead(), {"site_ok": False, "site_error": "down"}) == ["site_down"]


def test_pains_healthy_site_has_none(workspace):
    sig = {
        "site_ok": True,
        "https": True,
        "mobile_viewport": True,
        "load_seconds": 1.2,
        "analytics": True,
        "booking": True,
        "copyright_year": 2025,
        "http_redirects_to_https": True,
    }
    assert pain_points(_lead(), sig) == []


def test_pains_collects_fixable_problems(workspace):
    sig = {
        "site_ok": True,
        "https": True,
        "ssl_broken": False,
        "ssl_days_left": 10,
        "mobile_viewport": False,
        "load_seconds": 6.5,
        "wordpress_version": "5.8",
        "jquery_version": "1.12.4",
        "php_version": "7.4",
        "copyright_year": 2019,
        "booking": False,
        "chat_widget": False,
        "analytics": False,
        "http_redirects_to_https": False,
        "mixed_content": True,
        "tls_version": "TLSv1.1",
    }
    pts = pain_points(_lead(rating=3.5, reviews=40), sig)
    assert set(pts) == {
        "ssl_expiring",
        "old_tls",
        "no_https_redirect",
        "mixed_content",
        "outdated_wordpress",
        "old_jquery",
        "old_php",
        "not_mobile",
        "slow_site",
        "outdated_site",
        "no_booking",
        "no_analytics",
        "low_rating",
    }


def test_pains_broken_ssl_over_http(workspace):
    sig = {
        "site_ok": True,
        "ssl_broken": True,
        "https": False,
        "mobile_viewport": True,
        "analytics": True,
        "booking": True,
    }
    assert pain_points(_lead(), sig) == ["bad_ssl"]
