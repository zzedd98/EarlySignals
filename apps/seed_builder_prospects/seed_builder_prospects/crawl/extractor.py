"""
Extraction des preuves depuis le HTML : title, meta, h1/h2, snippets, signaux, outils.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup

from seed_builder_prospects.config import TOOLS_PATTERNS
from seed_builder_prospects.signals.detectors import (
    detect_sales_led_cta,
    detect_pricing,
    detect_recruitment,
    detect_clients_case_studies,
    detect_france_indices,
    detect_agency_freelance,
    detect_ecommerce,
    detect_tools_in_html,
)
from seed_builder_prospects.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class PageEvidence:
    """Preuves extraites d'une page."""
    url: str = ""
    title: str = ""
    meta_description: str = ""
    og_site_name: str = ""
    h1: list[str] = field(default_factory=list)
    h2: list[str] = field(default_factory=list)
    snippet: str = ""
    status_code: int = 200
    redirect_chain: list[str] = field(default_factory=list)
    # Signaux booléens
    sales_led_cta: bool = False
    pricing: bool = False
    recruitment: bool = False
    clients_case_studies: bool = False
    france_indices: bool = False
    agency_freelance: bool = False
    ecommerce: bool = False
    tools: list[str] = field(default_factory=list)
    # Texte brut pour détection
    body_text: str = ""


def _clean_text(s: str, max_len: int = 1000) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len] if len(s) > max_len else s


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """
    Extrait tous les liens <a href> internes (même domaine).
    Retourne liste de (url_normalized, anchor_text).
    """
    from seed_builder_prospects.crawl.url_normalize import normalize_url, same_domain

    base_domain = base_url
    try:
        from urllib.parse import urlparse
        base_domain = urlparse(base_url).netloc or base_url
    except Exception:
        pass

    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        full = normalize_url(href, base_domain)
        if not full.startswith("http"):
            continue
        if not same_domain(full, base_domain):
            continue
        anchor = _clean_text(a.get_text(), 200)
        if full not in seen:
            seen.add(full)
            out.append((full, anchor))
    return out


def extract_page_evidence(
    url: str,
    html: str,
    status_code: int = 200,
    redirect_chain: Optional[list[str]] = None,
) -> PageEvidence:
    """
    Parse le HTML et remplit PageEvidence : title, meta, h1/h2, snippet, signaux, outils.
    """
    evidence = PageEvidence(
        url=url,
        status_code=status_code,
        redirect_chain=redirect_chain or [],
    )
    if not html:
        return evidence

    soup = BeautifulSoup(html, "html.parser")

    # Title
    t = soup.find("title")
    evidence.title = _clean_text(t.get_text(), 200) if t else ""

    # Meta description
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    evidence.meta_description = _clean_text(meta.get("content", "") or "", 300) if meta else ""

    # og:site_name (brand)
    og_site = soup.find("meta", attrs={"property": "og:site_name"})
    evidence.og_site_name = _clean_text(og_site.get("content", "") or "", 100) if og_site else ""

    # H1 / H2
    evidence.h1 = [_clean_text(el.get_text(), 150) for el in soup.find_all("h1")]
    evidence.h2 = [_clean_text(el.get_text(), 150) for el in soup.find_all("h2")]

    # Body text (pour détections)
    body = soup.find("body")
    evidence.body_text = _clean_text(body.get_text() if body else soup.get_text(), 5000)

    # Snippet
    evidence.snippet = _clean_text(evidence.body_text, 1000)

    # Signaux
    combined = " ".join([evidence.title, evidence.meta_description] + evidence.h1 + evidence.h2 + [evidence.body_text])
    evidence.sales_led_cta = detect_sales_led_cta(combined)
    evidence.pricing = detect_pricing(combined)
    evidence.recruitment = detect_recruitment(combined)
    evidence.clients_case_studies = detect_clients_case_studies(combined)
    evidence.france_indices = detect_france_indices(combined)
    evidence.agency_freelance = detect_agency_freelance(combined)
    evidence.ecommerce = detect_ecommerce(combined)
    evidence.tools = detect_tools_in_html(html, TOOLS_PATTERNS)

    return evidence
