"""
Normalisation et canonicalisation des domaines/URLs.
- Enlever scheme, www, trailing slash
- Résoudre redirects côté appelant (http_client)
- Préférer apex domain quand c'est le site officiel
"""
import re
from urllib.parse import urlparse, urlunparse

from seed_builder_prospects.logging_utils import get_logger

logger = get_logger(__name__)

# Sous-domaines courants à ignorer pour obtenir l'apex
STRIP_SUBDOMAINS = {"www", "www2", "m", "mobile", "app", "api", "blog", "careers", "jobs", "recrutement", "demo", "support", "help", "docs", "status"}


def normalize_url(url: str, base_domain: str | None = None) -> str:
    """
    Normalise une URL : scheme https, pas de trailing slash, pas de fragment.
    Si base_domain fourni, force le host au base_domain (pour liens relatifs).
    """
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith(("http://", "https://")):
        return url  # lien relatif ou mailto etc.
    try:
        p = urlparse(url)
        netloc = (p.netloc or "").lower()
        path = (p.path or "/").rstrip("/") or "/"
        if base_domain and not netloc:
            netloc = base_domain.lower()
        return urlunparse(("https", netloc, path, "", p.query or "", ""))
    except Exception:
        return url


def _apex_domain(host: str) -> str:
    """
    Retourne le domaine "enregistrable" (apex) quand c'est plausible.
    On ne fait pas de liste TLD exhaustive : on enlève www et sous-domaines courants.
    """
    host = host.lower().strip()
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) <= 1:
        return host
    # Enlever premier segment si c'est un sous-domaine connu
    if parts[0] in STRIP_SUBDOMAINS and len(parts) >= 2:
        return ".".join(parts[1:])
    return host


def canonical_domain_from_url(url: str) -> str:
    """
    Domain canonique : scheme enlevé, www/sous-domaines courants enlevés, pas de path.
    Retourne "" si URL invalide.
    """
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        if not host:
            return ""
        return _apex_domain(host)
    except Exception:
        return ""


def canonical_domain_with_path_from_url(url: str) -> str:
    """
    Domain canonique avec préfixe /fr si présent dans le chemin.
    Utilisé pour préserver les sites multilingues où /fr est nécessaire pour accéder au contenu.
    Exemples:
    - https://example.com/fr/page -> example.com/fr
    - https://example.com/en/page -> example.com
    - https://example.com/page -> example.com
    """
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        if not host:
            return ""
        domain = _apex_domain(host)
        
        # Vérifier si le chemin commence par /fr
        path = (p.path or "").strip()
        if path.startswith("/fr") and (len(path) == 3 or path[3] in ["/", "?", "#", ""]):
            # Préserver /fr dans le domaine
            return f"{domain}/fr"
        
        return domain
    except Exception:
        return ""


def same_domain(url: str, domain: str) -> bool:
    """True si l'URL appartient au même domaine (ou sous-domaine) que domain."""
    d = (domain or "").lower()
    canonical = canonical_domain_from_url(url)
    if not canonical:
        return False
    return canonical == d or canonical.endswith("." + d)
