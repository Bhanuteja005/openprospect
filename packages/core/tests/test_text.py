from openprospect.core.text import (
    city_from_address,
    clean_emails,
    domain_of,
    normalize_url,
    pick_best_email,
    possessive,
    short_name,
    subject_name,
)


def test_clean_emails_lowercases_dedupes_and_drops_junk():
    text = """Contact: Info@BrightSmile.com, info@brightsmile.com.
    sentry@abc.ingest.sentry.io noreply@brightsmile.com logo@2x.png user@example.com
    dr.jones@brightsmile.com"""
    assert clean_emails(text) == ["info@brightsmile.com", "dr.jones@brightsmile.com"]


def test_clean_emails_accepts_lists():
    assert clean_emails(["a@shop.io", "A@SHOP.IO", None]) == ["a@shop.io"]


def test_pick_best_email_prefers_personal_on_own_domain():
    emails = ["clinic@gmail.com", "info@smile.com", "sarah@smile.com", "hello@other.com"]
    assert pick_best_email(emails, "smile.com") == "sarah@smile.com"


def test_pick_best_email_role_order_then_free_mail():
    assert pick_best_email(["support@smile.com", "info@smile.com"], "smile.com") == "info@smile.com"
    assert pick_best_email(["owner@gmail.com", "x@unrelated.org"], "smile.com") == "owner@gmail.com"
    assert pick_best_email([], "smile.com") == ""


def test_short_name_strips_keyword_stuffing():
    assert short_name("Bright Smile Dental - Downtown - Implants & Aligners") == "Bright Smile Dental"
    assert short_name("Acme Law | Personal Injury") == "Acme Law"
    assert short_name("DR. SMITH'S DENTAL CARE") == "Dr. Smith's Dental Care"
    assert short_name(None) == ""


def test_subject_name_shortens_long_names():
    assert subject_name("Lakeside Family Dental & Orthodontics Center") == "Lakeside Family"
    assert subject_name("Dr J Patel Dental Studio and Implants") == "Dr J Patel"
    assert subject_name("Joe's") == "Joe"
    assert subject_name("Acme Dental") == "Acme Dental"


def test_possessive():
    assert possessive("Acme") == "Acme's"
    assert possessive("Smiles") == "Smiles'"


def test_city_from_address():
    assert city_from_address("500 Main St, Austin, TX 78701") == "Austin"
    assert city_from_address("Camden, NW1 7JR") == "Camden"
    assert city_from_address("") == ""


def test_urls_and_domains():
    assert normalize_url("acme.com") == "http://acme.com"
    assert normalize_url(" https://acme.com ") == "https://acme.com"
    assert normalize_url(None) == ""
    assert domain_of("https://www.Acme.com/contact?x=1") == "acme.com"
    assert domain_of("") == ""
