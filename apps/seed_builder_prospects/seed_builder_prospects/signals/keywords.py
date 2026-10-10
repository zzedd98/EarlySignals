"""
Mots-clés et patterns pour la détection de signaux (FR/EN).
"""
import re
from typing import Sequence

# CTA sales-led
SALES_LED_CTA = [
    "demander une démo", "demander une demo", "demander un démo",
    "contact commercial", "contactez nos experts", "parler à un expert",
    "réserver une démo", "book a demo", "request a demo", "schedule a demo",
    "contact sales", "contactez le commercial", "échangez avec un expert",
    "demandez une démo", "obtenir une démo",
    "nous contacter", "contactez-nous", "contactez nous",
    "obtenir un devis", "demandez un devis", "demandez votre devis",
    "devis personnalisé", "devis personnalise", "devis gratuit",
    "essayer gratuitement", "free trial", "start free trial",
    "réserver une démo", "planifier une démo", "planifier une demo",
]

# Tarifs / pricing
PRICING_KEYWORDS = [
    "nos tarifs",
    "grille tarifaire",
    "tarification",
    "pricing",
    "pricing plans",
    "plans and pricing",
    "request pricing",
    "demander un devis",
    "demander un prix",
    "abonnement mensuel",
    "abonnement annuel",
    "voir les tarifs",
    "nos offres",
    "nos formules",
    "à partir de",
    "a partir de",
    "forfait",
    "forfaits",
]

# Recrutement (strict: carrière, offres, candidature)
RECRUITMENT_KEYWORDS = [
    "recrutement",
    "nous recrutons",
    "offres d'emploi",
    "offres d’emploi",
    "offres de poste",
    "postes ouverts",
    "carrières",
    "career opportunities",
    "careers",
    "join our team",
    "rejoignez-nous",
    "rejoignez nous",
    "postuler",
    "candidater",
    "open positions",
    "job openings",
    "hiring now",
]

# Clients / case studies
CLIENTS_CASE_KEYWORDS = [
    "étude de cas",
    "etude de cas",
    "cas client",
    "case study",
    "case studies",
    "nos clients",
    "references clients",
    "références clients",
    "témoignages clients",
    "temoignages clients",
    "témoignages de nos clients",
    "temoignages de nos clients",
    "témoignages",
    "temoignages",
    "success stories",
    "ils nous font confiance",
    "qui nous font confiance",
]

# Indices France
FRANCE_INDICES = [
    "siret", "siren", "société française", "societe française",
    "siège social", "siege social", "rance", "france", "paris", "lyon", "marseille",
    "bordeaux", "lille", "toulouse", "nantes", "strasbourg",
    "mentions légales", "mentions legales", "rcs ", "rcs paris", "rcs lyon",
    "sarl", "sas", "sasu", "sci ", "société par actions",
]
# Pattern SIRET/SIREN
SIRET_SIREN_RE = re.compile(r"\b\d{9}\b|\b\d{14}\b", re.I)

# Agence / freelance (pénalité)
AGENCY_FREELANCE_KEYWORDS = [
    "agence ", "agence de", "agence digitale", "agence web",
    "studio ", "studio de", "freelance", "consultant indépendant",
    "consultant independant", "cabinet de conseil",
]

# E-commerce (pénalité)
ECOMMERCE_KEYWORDS = [
    "shopify", "prestashop", "woocommerce", "panier", "ajouter au panier",
    "boutique en ligne", "commander", "livraison gratuite",
    "acheter", "prix par unité", "stock",
]
