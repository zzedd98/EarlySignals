"""
Filtres et exclusions : blacklist domaines, hard exclude contenu.
"""
from seed_builder_prospects.config import BLACKLIST_DOMAINS
from seed_builder_prospects.crawl.url_normalize import canonical_domain_from_url


def is_blacklisted_domain(url_or_domain: str) -> bool:
    """True si le domaine est dans la blacklist (annuaires, job boards, social)."""
    domain = canonical_domain_from_url(url_or_domain) or url_or_domain.lower()
    for bl in BLACKLIST_DOMAINS:
        if domain == bl or domain.endswith("." + bl):
            return True
    return False


def should_hard_exclude(
    content_lower: str,
    *,
    exclude_agency: bool = False,  # Par défaut, on n'exclut plus les agences
) -> tuple[bool, str]:
    """
    True seulement si le site est littéralement non scrappable (antibot, bloqué, etc.).
    On ne filtre plus les marketplace/agence car on veut récupérer toutes les données possibles.
    Retourne (excluded, reason).
    """
    if not content_lower:
        return False, ""
    
    # Seulement les vrais problèmes de scraping :
    # - Pages complètement vides ou erreurs serveur
    # - Messages d'antibot explicites
    if len(content_lower.strip()) < 50:  # Page vraiment vide
        return True, "empty_page"
    
    # Messages d'antibot explicites
    antibot_keywords = [
        "access denied",
        "access forbidden",
        "blocked",
        "bot detected",
        "captcha required",
        "cloudflare",
        "ddos protection",
        "forbidden",
        "not authorized",
        "rate limit",
        "too many requests",
        "unauthorized access",
    ]
    for keyword in antibot_keywords:
        if keyword in content_lower:
            return True, f"antibot_{keyword.replace(' ', '_')}"
    
    # On ne filtre plus marketplace/agence - on veut toutes les données scrappables
    return False, ""
