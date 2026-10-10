"""
Tests : scoring final (règles bonus / pénalités).
"""
from seed_builder_prospects.signals.scoring import compute_score, ScoreBreakdown


def test_score_sales_led_bonus():
    score, breakdown = compute_score(sales_led_cta=True)
    assert breakdown.raw_bonus >= 30
    assert score >= 30


def test_score_pricing_bonus():
    score, _ = compute_score(pricing=True)
    assert score >= 20


def test_score_agency_penalty():
    score, breakdown = compute_score(
        sales_led_cta=True,
        agency_freelance=True,
    )
    assert breakdown.raw_penalty >= 50
    assert score == max(0, 30 - 50)


def test_score_capped_100():
    score, _ = compute_score(
        sales_led_cta=True,
        pricing=True,
        recruitment=True,
        clients_case_studies=True,
        tools_count=1,
        france_indices=True,
    )
    assert score <= 100


def test_score_capped_0():
    score, _ = compute_score(
        directory_marketplace=True,
        agency_freelance=True,
    )
    assert score == 0


def test_score_breakdown_details():
    _, breakdown = compute_score(sales_led_cta=True, pricing=True)
    assert "sales_led_cta" in breakdown.details
    assert "pricing_plans" in breakdown.details
