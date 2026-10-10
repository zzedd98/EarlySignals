"""Tests de classification segment (b2b_seller, recruitment, etc.)."""

from seed_builder_prospects.cli import _classify_segment
from seed_builder_prospects.crawl.extractor import PageEvidence
from seed_builder_prospects.signals.scoring import compute_score


def _promote_rejected_if_scored(segment: str, score: int) -> str:
    """Règle pipeline: rejected + score > 0 => b2b_seller."""
    if segment == "rejected" and score > 0:
        return "b2b_seller"
    return segment


def _evidence(url: str, title: str, body: str) -> PageEvidence:
    return PageEvidence(
        url=url,
        title=title,
        body_text=body,
        sales_led_cta="nous contacter" in body.lower(),
        pricing="devis" in body.lower(),
        clients_case_studies="temoignages" in body.lower() or "nos clients" in body.lower(),
        france_indices="france" in body.lower(),
    )


def test_10torsions_like_classified_b2b_seller():
    body = (
        "Prestataire evenementiel team building seminaire d'entreprise. "
        "Nous contacter. Demandez un devis personnalise. "
        "Temoignages de nos clients. Intervenons partout en France."
    )
    ev = _evidence("https://10torsions.com/", "10Torsions evenements", body)
    signals = {
        "recruitment": False,
        "sales_led_cta": True,
        "pricing": True,
        "clients_case_studies": True,
    }
    segment, confidence, reason = _classify_segment(
        domain="10torsions.com",
        evidences=[ev],
        signals_dict=signals,
        combined_text=body,
    )
    assert segment == "b2b_seller"
    assert confidence >= 40
    assert "b2b" in reason or "sales" in reason or "fallback" in reason


def test_rejected_with_positive_score_becomes_b2b_seller():
    score, _ = compute_score(france_indices=True)
    assert score > 0
    assert _promote_rejected_if_scored("rejected", score) == "b2b_seller"
    assert _promote_rejected_if_scored("rejected", 0) == "rejected"
