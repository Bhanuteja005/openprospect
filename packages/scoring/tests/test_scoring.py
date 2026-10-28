from openprospect.scoring.copy import icebreaker_and_offer
from openprospect.scoring.model import category_points, score_lead, tier_for


def test_category_points_uses_best_keyword_match(workspace):
    assert category_points("Cosmetic Dentist") == 25
    assert category_points("Cafe") == 6
    assert category_points("Plumber") == 8  # default
    assert category_points(None) == 8


def test_score_lead_parts_and_total(make_lead):
    lead = make_lead(
        reviews=1000,
        rating=4.7,
        price_range="$$$",
        email_status="site_mx_ok",
        signals={"ads_pixel": True, "analytics": True, "booking": True, "chat_widget": True},
        pain_points=["no_website", "slow_site"],
    )
    total, parts = score_lead(lead)
    assert parts == {
        "category": 25,
        "demand": 20,
        "reputation": 10,
        "price": 8,
        "budget": 10,
        "opportunity": 20,
        "reachability": 5,
    }
    assert total == 98
    assert tier_for(total) == "A"


def test_score_lead_empty_lead_is_low(make_lead):
    total, parts = score_lead(make_lead(category="Cafe"))
    assert parts["demand"] == 0 and parts["reachability"] == 0
    assert tier_for(total) == "C"


def test_tier_thresholds(workspace):
    assert tier_for(70) == "A"
    assert tier_for(69) == "B"
    assert tier_for(50) == "B"
    assert tier_for(49) == "C"


def test_icebreaker_uses_heaviest_claimable_pain(make_lead):
    lead = make_lead(pain_points=["slow_site", "bad_ssl", "no_analytics"], signals={"load_seconds": 7.1})
    line, offer, pain = icebreaker_and_offer(lead)
    assert pain == "bad_ssl"
    assert offer == "I fix certificates."
    assert "not private" in line


def test_icebreaker_never_claims_no_analytics(make_lead):
    line, offer, pain = icebreaker_and_offer(make_lead(pain_points=["no_analytics"], reviews=5))
    assert pain == "default"
    assert offer == "I build things."
    assert "tracking" not in line
    assert "Bright Smile Dental" in line  # default_no_reviews line names the business


def test_icebreaker_default_mentions_reviews(make_lead):
    line, _, pain = icebreaker_and_offer(make_lead(reviews=250, rating=4.9))
    assert pain == "default"
    assert "250 reviews at 4.9 stars" in line
