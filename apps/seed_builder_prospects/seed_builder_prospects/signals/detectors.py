"""
Détection de signaux dans le texte ou le HTML (regex + mots-clés).
"""
import re
from typing import Sequence

from .keywords import (
    SALES_LED_CTA,
    PRICING_KEYWORDS,
    RECRUITMENT_KEYWORDS,
    CLIENTS_CASE_KEYWORDS,
    FRANCE_INDICES,
    AGENCY_FREELANCE_KEYWORDS,
    ECOMMERCE_KEYWORDS,
    SIRET_SIREN_RE,
)


def _contains_any(text: str, phrases: Sequence[str]) -> bool:
    t = (text or "").lower()
    return any(p.lower() in t for p in phrases)


def detect_sales_led_cta(text: str) -> bool:
    return _contains_any(text, SALES_LED_CTA)


def detect_pricing(text: str) -> bool:
    return _contains_any(text, PRICING_KEYWORDS)


def detect_recruitment(text: str) -> bool:
    return _contains_any(text, RECRUITMENT_KEYWORDS)


def detect_clients_case_studies(text: str) -> bool:
    return _contains_any(text, CLIENTS_CASE_KEYWORDS)


def detect_france_indices(text: str) -> bool:
    if _contains_any(text, FRANCE_INDICES):
        return True
    if SIRET_SIREN_RE.search(text or ""):
        return True
    return False


def detect_agency_freelance(text: str) -> bool:
    return _contains_any(text, AGENCY_FREELANCE_KEYWORDS)


def detect_ecommerce(text: str) -> bool:
    return _contains_any(text, ECOMMERCE_KEYWORDS)


def detect_tools_in_html(
    html: str,
    tools_patterns: Sequence[tuple[str, str]],
) -> list[str]:
    """
    Détecte les outils via regex sur le HTML (scripts, etc.).
    tools_patterns = [(name, regex_pattern), ...]
    """
    found: list[str] = []
    for name, pattern in tools_patterns:
        if re.search(pattern, html or "", re.I):
            found.append(name)
    return found
