"""
Robots.txt : optionnel. Vérification respect crawling (désactivé par défaut pour ne pas ralentir).
Si activé, on peut vérifier avant fetch si l'URL est disallowed.
"""
from urllib.parse import urlparse
from typing import Optional

# Placeholder : pas d'implémentation complète pour garder le module simple.
# Une implémentation complète parserait robots.txt et testerait path.


def is_allowed(_url: str, _user_agent: str = "EarlySignals") -> bool:
    """Pour l'instant toujours True. À étendre avec un vrai parseur robots.txt si besoin."""
    return True
