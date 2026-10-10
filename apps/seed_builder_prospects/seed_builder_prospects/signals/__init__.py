"""
Signaux : mots-clés, détection, scoring, filtres.
"""
from .keywords import (
    SALES_LED_CTA,
    PRICING_KEYWORDS,
    RECRUITMENT_KEYWORDS,
    CLIENTS_CASE_KEYWORDS,
    FRANCE_INDICES,
    AGENCY_FREELANCE_KEYWORDS,
    ECOMMERCE_KEYWORDS,
)
from .detectors import (
    detect_sales_led_cta,
    detect_pricing,
    detect_recruitment,
    detect_clients_case_studies,
    detect_france_indices,
    detect_agency_freelance,
    detect_ecommerce,
    detect_tools_in_html,
)
from .scoring import compute_score, score_breakdown
from .filters import is_blacklisted_domain, should_hard_exclude

__all__ = [
    "SALES_LED_CTA",
    "PRICING_KEYWORDS",
    "RECRUITMENT_KEYWORDS",
    "CLIENTS_CASE_KEYWORDS",
    "FRANCE_INDICES",
    "AGENCY_FREELANCE_KEYWORDS",
    "ECOMMERCE_KEYWORDS",
    "detect_sales_led_cta",
    "detect_pricing",
    "detect_recruitment",
    "detect_clients_case_studies",
    "detect_france_indices",
    "detect_agency_freelance",
    "detect_ecommerce",
    "detect_tools_in_html",
    "compute_score",
    "score_breakdown",
    "is_blacklisted_domain",
    "should_hard_exclude",
]
