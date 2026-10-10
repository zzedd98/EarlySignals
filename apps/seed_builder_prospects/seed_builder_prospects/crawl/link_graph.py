"""
Scoring des liens internes pour sélectionner les pages à fetcher (sans tâtonnement).
On ne devine pas les URLs : on sélectionne à partir des liens réellement présents.
"""
import re
from urllib.parse import urlparse
from typing import Optional

# Patterns URL + ancres pour catégories de pages (FR/EN)
PAGE_CATEGORIES = [
    # (nom_catégorie, patterns_url, patterns_anchor)
    ("offre", ["/solution", "/produit", "/plateforme", "/product", "/solutions", "/offre", "/logiciel", "/software"], ["solution", "produit", "plateforme", "offre", "product"]),
    ("tarifs", ["/tarifs", "/pricing", "/plans", "/prix", "/offres", "/abonnement"], ["tarifs", "pricing", "plans", "prix", "offres"]),
    ("demo", ["/demo", "/demander-une-demo", "/contact", "/contact-commercial", "/request-demo", "/book-demo", "/demo"], ["démo", "demo", "contact", "commercial", "expert"]),
    ("recrutement", ["/recrutement", "/careers", "/jobs", "/offres", "/carrieres", "/emploi", "/nous-rejoindre"], ["recrutement", "carrières", "jobs", "emploi", "rejoignez"]),
    ("clients", ["/clients", "/case-studies", "/etudes-de-cas", "/references", "/temoignages", "/success-stories", "/nos-clients"], ["clients", "études de cas", "références", "témoignages"]),
    ("mentions", ["/mentions-legales", "/legal", "/privacy", "/confidentialite", "/cgv", "/cgu"], ["mentions légales", "legal", "privacy", "confidentialité"]),
]


def _normalize_path(url: str) -> str:
    try:
        p = urlparse(url)
        path = (p.path or "/").lower().rstrip("/") or "/"
        return path
    except Exception:
        return ""


def _anchor_lower(anchor: str) -> str:
    return (anchor or "").lower().strip()


def score_link(url: str, anchor: str) -> tuple[str, int]:
    """
    Score un lien (url + ancre). Retourne (category, score).
    score plus élevé = plus pertinent pour notre objectif.
    """
    path = _normalize_path(url)
    anchor = _anchor_lower(anchor)
    best_cat = "other"
    best_score = 0

    for cat_name, url_patterns, anchor_patterns in PAGE_CATEGORIES:
        path_match = any(p in path for p in url_patterns)
        anchor_match = any(p in anchor for p in anchor_patterns)
        if path_match and anchor_match:
            s = 30
        elif path_match or anchor_match:
            s = 15
        else:
            continue
        if cat_name == "tarifs" or cat_name == "demo":
            s += 5
        if s > best_score:
            best_score = s
            best_cat = cat_name

    if best_score == 0:
        # Page d'accueil ou autre
        if path in ("/", ""):
            best_cat = "home"
            best_score = 10
    return best_cat, best_score


def score_internal_links(links: list[tuple[str, str]]) -> list[tuple[str, str, int]]:
    """
    Pour chaque (url, anchor), retourne (url, category, score).
    Trié par score décroissant.
    """
    scored: list[tuple[str, str, int]] = []
    seen_urls: set[str] = set()
    for url, anchor in links:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        cat, score = score_link(url, anchor)
        scored.append((url, cat, score))
    scored.sort(key=lambda x: -x[2])
    return scored


def select_pages_to_fetch(
    links: list[tuple[str, str]],
    base_url: str,
    max_pages: int = 7,
    min_pages: int = 4,
) -> list[str]:
    """
    Sélectionne les URLs à fetcher : home + pages les mieux scorées par catégorie.
    On prend au plus une page par catégorie (meilleure score), puis on remplit
    jusqu'à max_pages avec les suivantes. Au moins min_pages (home + autres).
    """
    scored = score_internal_links(links)
    from seed_builder_prospects.crawl.url_normalize import normalize_url
    try:
        base_domain = urlparse(base_url).netloc or ""
    except Exception:
        base_domain = ""
    home = normalize_url(base_url, base_domain)
    if not home.startswith("http"):
        home = base_url

    to_fetch: list[str] = [home]
    best_by_cat: dict[str, tuple[str, int]] = {}  # cat -> (url, score)

    for url, cat, score in scored:
        if url in to_fetch:
            continue
        if cat == "home":
            continue
        if cat not in best_by_cat or best_by_cat[cat][1] < score:
            best_by_cat[cat] = (url, score)

    # Ajouter la meilleure URL par catégorie (ordre de priorité)
    for cat in ("demo", "tarifs", "recrutement", "clients", "offre", "mentions", "other"):
        if cat in best_by_cat and len(to_fetch) < max_pages:
            u = best_by_cat[cat][0]
            if u not in to_fetch:
                to_fetch.append(u)

    # Remplir avec les autres bien scorées
    for url, cat, score in scored:
        if len(to_fetch) >= max_pages:
            break
        if url not in to_fetch and score >= 10:
            to_fetch.append(url)

    return to_fetch[:max_pages]
