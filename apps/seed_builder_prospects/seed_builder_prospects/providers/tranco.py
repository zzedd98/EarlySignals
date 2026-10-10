"""
Provider Tranco : classement top 1M (fichier local ou téléchargement mis en cache).
Produit des DiscoveryResult pour le pipeline existant (URL https://domaine).
"""
import csv
from pathlib import Path
from typing import Iterator, Optional

from seed_builder_prospects.config import limit_reached
from seed_builder_prospects.crawl.url_normalize import canonical_domain_from_url, normalize_url
from seed_builder_prospects.discovery.tranco import ensure_tranco_csv
from seed_builder_prospects.logging_utils import get_logger
from seed_builder_prospects.providers.base import DiscoveryResult, SearchProviderBase

logger = get_logger(__name__)

SOURCE_NAME = "tranco"


def _normalize_tld_suffix(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if not s.startswith("."):
        s = "." + s
    return s


class TrancoProvider(SearchProviderBase):
    """
    Lit rank,domain depuis un CSV Tranco (dézipé ou fourni par --tranco-csv).
    Optionnel : filtre par suffixe (ex. .fr). S'arrête à max_results candidats acceptés.
    """

    def __init__(
        self,
        csv_path: Optional[Path],
        *,
        cache_dir: Optional[Path] = None,
        subdomains: bool = False,
        tld_suffix: Optional[str] = None,
        refresh: bool = False,
    ):
        self._explicit_csv = Path(csv_path) if csv_path else None
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.subdomains = subdomains
        self.tld_suffix = _normalize_tld_suffix(tld_suffix)
        self.refresh = refresh

    def _resolved_csv(self) -> Path:
        if self._explicit_csv is not None:
            return self._explicit_csv
        if not self.cache_dir:
            raise RuntimeError("cache_dir requis pour Tranco sans --tranco-csv")
        return ensure_tranco_csv(
            self.cache_dir, subdomains=self.subdomains, refresh=self.refresh
        )

    def search(self, query: str, max_per_query: int = 0) -> Iterator[DiscoveryResult]:
        return iter([])

    def discover(
        self,
        queries: list[str],
        max_results: int,
        dedup_by_domain: bool = True,
    ) -> list[DiscoveryResult]:
        return list(self._iter_discover(max_results, dedup_by_domain))

    def _iter_discover(
        self,
        max_results: int,
        dedup_by_domain: bool,
    ) -> Iterator[DiscoveryResult]:
        path = self._resolved_csv()
        if not path.exists():
            logger.warning("Fichier Tranco introuvable: %s", path)
            return

        seen: set[str] = set()
        count = 0
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 2:
                    continue
                rank_s, domain = row[0].strip(), row[1].strip()
                if not domain:
                    continue
                d = domain.lower().strip(".")
                if self.tld_suffix and not d.endswith(self.tld_suffix):
                    continue
                url = normalize_url("https://" + d)
                if not url:
                    continue
                canon = canonical_domain_from_url(url)
                if not canon:
                    continue
                if dedup_by_domain and canon in seen:
                    continue
                seen.add(canon)
                count += 1
                reason = f"Tranco #{rank_s}"
                if self.tld_suffix:
                    reason += f" ({self.tld_suffix})"
                yield DiscoveryResult(
                    url=url,
                    title="",
                    snippet="",
                    query="",
                    source_name=SOURCE_NAME,
                    discovery_reason=reason,
                )
                if limit_reached(count, max_results):
                    break
