"""
Provider de découverte abstrait : exécute des requêtes, agrége et déduplique par domaine.
Sortie intermédiaire homogène pour tout le pipeline.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator

from seed_builder_prospects.config import is_unlimited, limit_reached
from seed_builder_prospects.crawl.url_normalize import canonical_domain_from_url


@dataclass
class DiscoveryResult:
    """
    Un candidat pour la seed list (URL ou domaine cible).
    Le pipeline existant utilise .url pour fetch + scoring.
    source_name et discovery_reason servent au debug et à la traçabilité.
    """
    url: str
    title: str = ""
    snippet: str = ""
    query: str = ""
    source_name: str = ""
    discovery_reason: str = ""


class SearchProviderBase(ABC):
    """Interface pour un provider de découverte (API ou fichier)."""

    @abstractmethod
    def search(self, query: str, max_per_query: int) -> Iterator[DiscoveryResult]:
        """Exécute une requête et yield des DiscoveryResult."""
        ...

    def discover(
        self,
        queries: list[str],
        max_results: int,
        dedup_by_domain: bool = True,
    ) -> list[DiscoveryResult]:
        """
        Exécute toutes les requêtes, agrège et déduplique par domaine canonique.
        Retourne au plus max_results domaines uniques (première URL rencontrée conservée).
        """
        seen_domains: set[str] = set()
        aggregated: list[DiscoveryResult] = []
        per_query = (
            max(10, (max_results // len(queries)) + 20)
            if queries and not is_unlimited(max_results)
            else (10**9 if queries else 0)
        )

        for q in queries:
            for r in self.search(q, max_per_query=per_query):
                domain = canonical_domain_from_url(r.url)
                if not domain:
                    continue
                if dedup_by_domain and domain in seen_domains:
                    continue
                seen_domains.add(domain)
                aggregated.append(r)
                if limit_reached(len(aggregated), max_results):
                    return aggregated

        return aggregated
