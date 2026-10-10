"""
Crawl : client HTTP, normalisation URL, extraction, graphe de liens.
"""
from .http_client import fetch_url, fetch_url_with_redirects
from .url_normalize import canonical_domain_from_url, canonical_domain_with_path_from_url, normalize_url
from .extractor import extract_links, extract_page_evidence
from .link_graph import score_internal_links, select_pages_to_fetch

__all__ = [
    "fetch_url",
    "fetch_url_with_redirects",
    "canonical_domain_from_url",
    "normalize_url",
    "extract_links",
    "extract_page_evidence",
    "score_internal_links",
    "select_pages_to_fetch",
]
