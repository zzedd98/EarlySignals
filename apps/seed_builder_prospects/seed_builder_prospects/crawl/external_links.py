"""
Extraction et classification des liens externes pertinents depuis une homepage.
Détecte les domaines associés (recrutement, etc.) et les classe avec des tags.
"""
from typing import Any, Optional
from bs4 import BeautifulSoup
from seed_builder_prospects.crawl.url_normalize import (
    canonical_domain_from_url,
    normalize_url,
    same_domain,
)
from seed_builder_prospects.signals.filters import is_blacklisted_domain


def extract_external_links(html: str, base_url: str) -> list[tuple[str, str, str]]:
    """
    Extrait les liens externes pertinents depuis une homepage.
    Retourne liste de (url, anchor_text, domain).
    """
    soup = BeautifulSoup(html, "html.parser")
    base_domain = canonical_domain_from_url(base_url)
    out: list[tuple[str, str, str]] = []
    seen_domains: set[str] = set()
    
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        
        # Normaliser l'URL
        full_url = normalize_url(href, base_domain)
        if not full_url.startswith("http"):
            continue
        
        # Vérifier que c'est un domaine externe
        domain = canonical_domain_from_url(full_url)
        if not domain or same_domain(full_url, base_domain):
            continue
        
        # Ignorer les domaines blacklistés
        if is_blacklisted_domain(domain):
            continue
        
        # Éviter les doublons
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        
        anchor = (a.get_text() or "").strip()[:200]
        out.append((full_url, anchor, domain))
    
    return out


def classify_domain_type(html: str, url: str, anchor_text: str = "") -> list[str]:
    """
    Classifie un domaine avec des tags basés sur son contenu.
    Retourne liste de tags : ['agence_recrutement', 'agence_growth', etc.]
    """
    tags: list[str] = []
    text_lower = (html or "").lower()
    anchor_lower = (anchor_text or "").lower()
    url_lower = (url or "").lower()
    combined = f"{text_lower} {anchor_lower} {url_lower}"
    
    # Détection recrutement (mots-clés + domaines connus de plateformes de recrutement)
    recruitment_keywords = [
        "recrutement", "recruitment", "carrières", "careers", "jobs", 
        "offres d'emploi", "job openings", "hiring", "postuler", "candidater",
        "apply", "candidate", "open position", "we are hiring", "nous recrutons"
    ]
    recruitment_domains = [
        "teamtailor", "workable", "lever", "greenhouse", "bamboohr",
        "smartrecruiters", "jobvite", "icims", "taleo"
    ]
    if any(kw in combined for kw in recruitment_keywords) or any(dom in url_lower for dom in recruitment_domains):
        tags.append("agence_recrutement")
    
    # Détection growth/sales (basé sur les signaux existants)
    growth_keywords = [
        "demander une démo", "demander une demo", "contact commercial",
        "tarifs", "pricing", "nos tarifs", "plans",
        "recrutement sales", "recrutement marketing", "recrutement growth",
        "case study", "étude de cas", "nos clients", "références"
    ]
    if any(kw in combined for kw in growth_keywords):
        tags.append("agence_growth")
    
    # Détection SaaS/B2B
    saas_keywords = [
        "saas", "software", "logiciel", "plateforme", "solution",
        "api", "cloud", "subscription", "abonnement"
    ]
    if any(kw in combined for kw in saas_keywords):
        tags.append("saas_b2b")
    
    # Si aucun tag spécifique, on garde quand même le domaine
    if not tags:
        tags.append("domaine_associe")
    
    return tags


def classify_domain_from_content(html: str, url: str, anchor_text: str = "") -> list[str]:
    """
    Alias pour classify_domain_type (pour compatibilité).
    """
    return classify_domain_type(html, url, anchor_text)


def extract_and_classify_external_domains(
    html: str, 
    base_url: str
) -> list[dict[str, Any]]:
    """
    Extrait les liens externes et les classe avec des tags.
    Retourne liste de dicts avec: url, domain, anchor_text, tags
    """
    external_links = extract_external_links(html, base_url)
    classified: list[dict[str, any]] = []
    
    for url, anchor, domain in external_links:
        # Classifier le domaine (on fetch juste la homepage pour classifier)
        tags = classify_domain_type(html, url, anchor)
        
        classified.append({
            "url": url,
            "domain": domain,
            "anchor_text": anchor,
            "tags": tags,
        })
    
    return classified
