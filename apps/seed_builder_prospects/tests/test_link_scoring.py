"""
Tests : scoring des liens internes (choix des pages à fetcher).
"""
from seed_builder_prospects.crawl.link_graph import (
    score_link,
    score_internal_links,
    select_pages_to_fetch,
)


def test_score_link_tarifs():
    cat, score = score_link("https://example.com/tarifs", "Voir nos tarifs")
    assert cat == "tarifs"
    assert score >= 15


def test_score_link_demo():
    cat, score = score_link("https://example.com/demo", "Demander une démo")
    assert cat == "demo"
    assert score >= 15


def test_score_link_recrutement():
    cat, score = score_link("https://example.com/careers", "Carrières")
    assert cat == "recrutement"
    assert score >= 15


def test_score_link_home():
    cat, score = score_link("https://example.com/", "Accueil")
    assert cat == "home"
    assert score == 10


def test_score_internal_links_dedup():
    links = [
        ("https://example.com/tarifs", "Tarifs"),
        ("https://example.com/tarifs", "Pricing"),
    ]
    scored = score_internal_links(links)
    assert len(scored) == 1


def test_select_pages_to_fetch_includes_home():
    links = [
        ("https://example.com/", "Accueil"),
        ("https://example.com/tarifs", "Tarifs"),
        ("https://example.com/demo", "Démo"),
    ]
    selected = select_pages_to_fetch(links, "https://example.com/", max_pages=5)
    assert len(selected) >= 1
    assert any("example.com" in u and ("/" == u.rstrip("/") or u.endswith("/")) for u in selected)
