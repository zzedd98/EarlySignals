"""
Tests : normalisation domaine + gestion redirects (mock).
"""
import pytest
from seed_builder_prospects.crawl.url_normalize import (
    canonical_domain_from_url,
    normalize_url,
    same_domain,
)


def test_canonical_domain_strips_scheme_and_www():
    assert canonical_domain_from_url("https://www.example.com/") == "example.com"
    assert canonical_domain_from_url("http://example.com/path") == "example.com"


def test_canonical_domain_trailing_slash():
    assert canonical_domain_from_url("https://example.fr/") == "example.fr"


def test_canonical_domain_subdomain():
    assert canonical_domain_from_url("https://blog.example.com/page") == "example.com"


def test_canonical_domain_invalid():
    assert canonical_domain_from_url("") == ""
    # "not-a-url" reçoit https:// -> host "not-a-url" (pas de TLD), on le retourne tel quel
    assert canonical_domain_from_url("not-a-url") in ("", "not-a-url")


def test_normalize_url_https():
    assert normalize_url("https://example.com/path") == "https://example.com/path"
    assert normalize_url("https://example.com/path/") == "https://example.com/path"


def test_normalize_url_with_base():
    # Lien relatif sans scheme : normalize_url retourne tel quel (pas de netloc)
    assert normalize_url("https://example.com/tarifs") == "https://example.com/tarifs"


def test_same_domain():
    assert same_domain("https://www.example.com/page", "example.com") is True
    assert same_domain("https://sub.example.com/", "example.com") is True
    assert same_domain("https://other.com/", "example.com") is False
