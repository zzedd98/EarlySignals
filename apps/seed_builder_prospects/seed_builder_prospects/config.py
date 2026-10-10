"""
Configuration du seed builder : query packs, scoring, exclusions, outils détectés.
"""
from pathlib import Path
from typing import Any

# Répertoire de base du module (pour query packs, etc.)
MODULE_DIR = Path(__file__).resolve().parent
DATA_DIR = MODULE_DIR / "data"


def _quote_keywords(keywords: list[str]) -> str:
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    deduped = list(dict.fromkeys(cleaned))
    return " OR ".join(f'"{k}"' for k in deduped)


# Keywords de requêtes pack (définis localement pour éviter les imports circulaires).
QUERY_KEYWORDS_SALES_LED = [
    "demander une démo",
    "demander une demo",
    "demander un démo",
    "contact commercial",
    "contactez nos experts",
    "parler à un expert",
    "réserver une démo",
    "book a demo",
    "request a demo",
    "schedule a demo",
    "contact sales",
    "contactez le commercial",
    "échangez avec un expert",
    "demandez une démo",
    "obtenir une démo",
]
QUERY_KEYWORDS_PRICING = [
    "tarifs",
    "tarif",
    "pricing",
    "plans",
    "plan",
    "nos tarifs",
    "prix",
    "abonnement",
    "subscription",
    "voir les tarifs",
    "comparer les offres",
    "plans et tarifs",
]
QUERY_KEYWORDS_RECRUITMENT = [
    "recrutement",
    "nous recrutons",
    "offres d'emploi",
    "offres d’emploi",
    "sales",
    "commercial",
    "marketing",
    "growth",
    "lead generation",
    "carrières",
    "careers",
    "jobs",
    "rejoignez-nous",
    "rejoignez nous",
    "postuler",
    "candidater",
    "open position",
    "hiring",
]
QUERY_KEYWORDS_CLIENTS_CASE = [
    "étude de cas",
    "etude de cas",
    "case study",
    "nos clients",
    "références",
    "references",
    "témoignages",
    "temoignages",
    "success stories",
    "clients",
    "qui nous font confiance",
]

COMMON_SITE_FILTER = "(site:.fr OR site:.io OR site:.com)"
COMMON_NEGATIVE_SITES = [
    "-site:linkedin.com",
    "-site:facebook.com",
    "-site:twitter.com",
    "-site:instagram.com",
    "-site:welcome-to-the-jungle.com",
    "-site:indeed.com",
    "-site:hellowork.com",
    "-site:monster.fr",
    "-site:sortlist.*",
    "-site:malt.*",
    "-site:lespagesjaunes.*",
    "-site:societe.com",
]
COMMON_NEGATIVE_TERMS = ["agence", "studio", "freelance", "consultant"]
COMMON_B2B_CONTEXT = ["B2B", "entreprise", "professionnels", "SaaS", "PME", "ETI"]

# --- Query pack : fr_prospects_growth_b2b ---
QUERY_PACK_FR_PROSPECTS_GROWTH_B2B = {
    "id": "fr_prospects_growth_b2b",
    "name": "Prospects B2B FR (growth / sales-led)",
    "site_filter": "(site:.fr OR site:.io OR site:.com)",
    "negative_sites": [
        "-site:linkedin.com",
        "-site:facebook.com",
        "-site:twitter.com",
        "-site:instagram.com",
        "-site:welcome-to-the-jungle.com",
        "-site:indeed.com",
        "-site:hellowork.com",
        "-site:monster.fr",
        "-site:sortlist.*",
        "-site:malt.*",
        "-site:lespagesjaunes.*",
        "-site:societe.com",
    ],
    "negative_terms": ["agence", "studio", "freelance", "consultant"],  # configurable
    "queries": [
        '("demander une démo" OR "demander une demo" OR "contact commercial" OR "contactez nos experts")',
        '("nos tarifs" OR "tarifs" OR "pricing" OR "plans") ("B2B" OR "entreprise" OR "professionnels")',
        '("recrutement" OR "nous recrutons" OR "offres d\'emploi") ("sales" OR "commercial" OR "marketing" OR "growth" OR "lead generation")',
        '("étude de cas" OR "case study" OR "nos clients" OR "références") ("SaaS" OR "B2B" OR "entreprise")',
        '("solution" OR "plateforme" OR "logiciel") ("PME" OR "ETI" OR "entreprises")',
    ],
    # Une seule requête large, en regroupant tous les signaux/keywords du domaine.
    "merge_queries": True,
    "keywords": list(
        dict.fromkeys(
            QUERY_KEYWORDS_SALES_LED
            + QUERY_KEYWORDS_PRICING
            + QUERY_KEYWORDS_RECRUITMENT
            + QUERY_KEYWORDS_CLIENTS_CASE
            + ["B2B", "entreprise", "professionnels", "SaaS", "PME", "ETI"]
        )
    ),
}

# Query packs spécialisés par famille de keywords (pour découverte ciblée)
QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_SALES_LED = {
    "id": "fr_prospects_growth_b2b_sales_led",
    "name": "Prospects B2B FR - Sales-led only",
    "site_filter": COMMON_SITE_FILTER,
    "negative_sites": COMMON_NEGATIVE_SITES,
    "negative_terms": COMMON_NEGATIVE_TERMS,
    "queries": [
        '("demander une démo" OR "demander une demo" OR "contact commercial" OR "contactez nos experts") ("B2B" OR "entreprise" OR "professionnels")',
    ],
    "merge_queries": True,
    "keywords": list(dict.fromkeys(QUERY_KEYWORDS_SALES_LED + COMMON_B2B_CONTEXT)),
}

QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_PRICING = {
    "id": "fr_prospects_growth_b2b_pricing",
    "name": "Prospects B2B FR - Pricing only",
    "site_filter": COMMON_SITE_FILTER,
    "negative_sites": COMMON_NEGATIVE_SITES,
    "negative_terms": COMMON_NEGATIVE_TERMS,
    "queries": [
        '("nos tarifs" OR "tarifs" OR "pricing" OR "plans") ("B2B" OR "entreprise" OR "professionnels")',
    ],
    "merge_queries": True,
    "keywords": list(dict.fromkeys(QUERY_KEYWORDS_PRICING + COMMON_B2B_CONTEXT)),
}

QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_RECRUITMENT = {
    "id": "fr_prospects_growth_b2b_recruitment",
    "name": "Prospects B2B FR - Recruitment only",
    "site_filter": COMMON_SITE_FILTER,
    "negative_sites": COMMON_NEGATIVE_SITES,
    "negative_terms": COMMON_NEGATIVE_TERMS,
    "queries": [
        '("recrutement" OR "nous recrutons" OR "offres d\'emploi") ("sales" OR "commercial" OR "marketing" OR "growth" OR "lead generation")',
    ],
    "merge_queries": True,
    "keywords": list(dict.fromkeys(QUERY_KEYWORDS_RECRUITMENT + COMMON_B2B_CONTEXT)),
}

QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_CLIENTS_CASE = {
    "id": "fr_prospects_growth_b2b_clients_case",
    "name": "Prospects B2B FR - Clients/Case studies only",
    "site_filter": COMMON_SITE_FILTER,
    "negative_sites": COMMON_NEGATIVE_SITES,
    "negative_terms": COMMON_NEGATIVE_TERMS,
    "queries": [
        '("étude de cas" OR "case study" OR "nos clients" OR "références") ("SaaS" OR "B2B" OR "entreprise")',
    ],
    "merge_queries": True,
    "keywords": list(dict.fromkeys(QUERY_KEYWORDS_CLIENTS_CASE + COMMON_B2B_CONTEXT)),
}

# Query pack de test avec seulement 2 requêtes pour des tests plus rapides
QUERY_PACK_FR_PROSPECTS_GROWTH_B2B_TEST = {
    "id": "fr_prospects_growth_b2b_test",
    "name": "Prospects B2B FR - Test (2 requêtes)",
    "site_filter": "(site:.fr OR site:.io OR site:.com)",
    "negative_sites": [
        "-site:linkedin.com",
        "-site:facebook.com",
        "-site:twitter.com",
        "-site:instagram.com",
        "-site:welcome-to-the-jungle.com",
        "-site:indeed.com",
        "-site:hellowork.com",
        "-site:monster.fr",
        "-site:sortlist.*",
        "-site:malt.*",
        "-site:lespagesjaunes.*",
        "-site:societe.com",
    ],
    "negative_terms": ["agence", "studio", "freelance", "consultant"],
    "queries": [
        '("demander une démo" OR "demander une demo" OR "contact commercial" OR "contactez nos experts")',
        '("nos tarifs" OR "tarifs" OR "pricing" OR "plans") ("B2B" OR "entreprise" OR "professionnels")',
    ],
    "merge_queries": True,
    "keywords": list(
        dict.fromkeys(
            QUERY_KEYWORDS_SALES_LED
            + QUERY_KEYWORDS_PRICING
            + QUERY_KEYWORDS_RECRUITMENT
            + QUERY_KEYWORDS_CLIENTS_CASE
            + ["B2B", "entreprise", "professionnels", "SaaS", "PME", "ETI"]
        )
    ),
}

def get_full_queries(pack: dict[str, Any]) -> list[str]:
    """Construit les requêtes complètes.

    Si merge_queries=True, retourne une seule requête fusionnée.
    """
    site = pack.get("site_filter", "")
    prefix = site.strip() if site else ""
    if pack.get("merge_queries", False):
        keywords = pack.get("keywords", [])
        if keywords:
            merged_core = f"({_quote_keywords(list(keywords))})"
        else:
            query_blocks = [q.strip() for q in pack.get("queries", []) if q and q.strip()]
            merged_core = f"({' OR '.join(query_blocks)})" if query_blocks else ""
        merged_query = f"{prefix} {merged_core}".strip() if prefix else merged_core
        return [merged_query] if merged_query else []

    return [f"{prefix} {q}".strip() if prefix else q for q in pack["queries"]]


# --- Domaines blacklist (hard exclude) ---
BLACKLIST_DOMAINS = [
    "linkedin.com", "facebook.com", "twitter.com", "instagram.com",
    "welcome-to-the-jungle.com", "indeed.com", "hellowork.com", "monster.fr",
    "sortlist.com", "malt.com", "lespagesjaunes.fr", "societe.com",
    "google.com", "youtube.com", "wikipedia.org", "github.com",
]


# --- Outils détectés (scripts / regex) ---
TOOLS_PATTERNS = [
    ("stripe", r"stripe\.com|js\.stripe\.com"),
    ("hubspot", r"hubspot|hs-scripts|hs-analytics"),
    ("intercom", r"intercom\.io|intercomcdn\.com"),
    ("segment", r"segment\.(io|com)|analytics\.js"),
    ("ga4", r"googletagmanager\.com/gtag|gtag\s*\(|GA4|G-[A-Z0-9]+"),
    ("gtm", r"googletagmanager\.com/gtm\.js"),
    ("meta_pixel", r"connect\.facebook\.net|fbq\s*\("),
    ("hotjar", r"hotjar\.com|hj\.js"),
    ("crisp", r"client\.crisp\.chat|crisp\.chat"),
    ("salesforce", r"salesforce\.com|salesforceliveagent"),
]


# --- Scoring (bonus / pénalités) ---
SCORING_BONUS = {
    "sales_led_cta": 30,   # demo / contact sales / parler à un expert
    "pricing_plans": 20,   # tarifs / pricing / plans
    "recruitment": 25,     # recrutement sales/marketing/growth
    "clients_case_studies": 15,
    "tools_marketing_sales": 10,  # HubSpot, Intercom, Segment, GA4, GTM, etc.
    "france_indices": 10,  # SIRET/SIREN, adresse FR, mentions légales FR
}

SCORING_PENALTY = {
    "ecommerce": 40,       # Shopify/Prestashop/WooCommerce + vocabulaire boutique
    "directory_marketplace": 60,  # hard exclude
    "agency_freelance": 50,
    "blocked_or_empty": 30,
    "non_fr_no_indices": 25,
}

MIN_SCORE_DEFAULT = 60
MAX_PAGES_PER_DOMAIN = 7
MIN_PAGES_PER_DOMAIN = 4

# --max-links / --max-results : 0 = illimité (traiter tout le fichier / toute la découverte).
UNLIMITED_MAX = 0


def is_unlimited(limit: int) -> bool:
    return limit <= 0


def limit_reached(count: int, limit: int) -> bool:
    return limit > 0 and count >= limit


def format_pipeline_limit(limit: int) -> str:
    return "illimité" if is_unlimited(limit) else str(limit)
