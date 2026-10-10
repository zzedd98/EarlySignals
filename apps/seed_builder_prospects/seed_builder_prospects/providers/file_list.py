"""
Provider file_list : lit domaines / URLs depuis un CSV (colonne domain) ou TXT.
"""
import csv
from pathlib import Path
from typing import Iterator, Optional

from seed_builder_prospects.config import limit_reached
from seed_builder_prospects.crawl.url_normalize import canonical_domain_from_url, normalize_url
from seed_builder_prospects.logging_utils import get_logger
from seed_builder_prospects.providers.base import DiscoveryResult, SearchProviderBase

logger = get_logger(__name__)

SOURCE_NAME = "file_list"
INPUT_FORMATS = ("auto", "domain", "grenouillemoi")


def _resolve_csv_value_key(fieldnames: list[str], input_format: str) -> str:
    """Colonne CSV à lire selon le format (grenouillemoi => colonne URL)."""
    lower_map = {fn.lower(): fn for fn in fieldnames if fn}
    fmt = (input_format or "auto").strip().lower()
    if fmt == "grenouillemoi":
        url_key = lower_map.get("url")
        if not url_key:
            raise ValueError(
                "Format grenouillemoi: colonne 'URL' introuvable dans l'en-tête CSV"
            )
        return url_key
    if fmt == "domain":
        return lower_map.get("domain") or fieldnames[0]
    # auto
    if "domain" in lower_map:
        return lower_map["domain"]
    if "url" in lower_map:
        return lower_map["url"]
    return fieldnames[0]


def iter_domains_from_seed_file(
    path: Path, *, input_format: str = "auto"
) -> Iterator[str]:
    """Extrait domaines/URLs depuis CSV (domain, URL/grenouillemoi) ou TXT."""
    path = Path(path)
    if not path.is_file():
        return
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return
            value_key = _resolve_csv_value_key(list(reader.fieldnames), input_format)
            for row in reader:
                raw = (row.get(value_key) or "").strip()
                if not raw and row:
                    raw = next((v.strip() for v in row.values() if v and str(v).strip()), "")
                if raw and not raw.startswith("#"):
                    yield raw
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            line = line.split(",")[0].strip()
        yield line


class FileListProvider(SearchProviderBase):
    def __init__(self, input_path: str | Path, *, input_format: str = "auto"):
        self.input_path = Path(input_path)
        self.input_format = input_format

    def search(self, query: str, max_per_query: int = 0) -> Iterator[DiscoveryResult]:
        if not self.input_path.exists():
            logger.warning("Input file not found: %s", self.input_path)
            return
        count = 0
        cap = max_per_query if max_per_query > 0 else 10**9
        for raw in iter_domains_from_seed_file(
            self.input_path, input_format=self.input_format
        ):
            if count >= cap:
                break
            line = raw.strip()
            if not line.startswith(("http://", "https://")):
                line = "https://" + line
            url = normalize_url(line)
            if not url:
                continue
            count += 1
            yield DiscoveryResult(
                url=url,
                title="",
                snippet="",
                query="file_list",
                source_name=SOURCE_NAME,
                discovery_reason=(
                    "grenouillemoi"
                    if self.input_format == "grenouillemoi"
                    else "fichier seed"
                ),
            )

    def discover(
        self,
        queries: list[str],
        max_results: int,
        dedup_by_domain: bool = True,
    ) -> list[DiscoveryResult]:
        seen: set[str] = set()
        out: list[DiscoveryResult] = []
        search_cap = max_results if max_results > 0 else 0
        for r in self.search("file_list", max_per_query=search_cap):
            d = canonical_domain_from_url(r.url)
            if not d:
                continue
            if dedup_by_domain and d in seen:
                continue
            seen.add(d)
            out.append(r)
            if limit_reached(len(out), max_results):
                break
        return out


def load_discovery_from_seed_csv(
    path: str | Path,
    *,
    offset: int = 0,
    limit: Optional[int] = None,
    input_format: str = "auto",
) -> list[DiscoveryResult]:
    """Charge des DiscoveryResult depuis un CSV/TXT, avec découpe [offset:offset+limit]."""
    path = Path(path)
    fmt = (input_format or "auto").strip().lower()
    domains: list[str] = []
    for raw in iter_domains_from_seed_file(path, input_format=fmt):
        domains.append(raw.strip())
    slice_ = domains[offset:] if limit is None else domains[offset : offset + limit]
    out: list[DiscoveryResult] = []
    seen: set[str] = set()
    for raw in slice_:
        line = raw if raw.startswith(("http://", "https://")) else "https://" + raw
        url = normalize_url(line)
        if not url:
            continue
        d = canonical_domain_from_url(url)
        if not d or d in seen:
            continue
        seen.add(d)
        out.append(
            DiscoveryResult(
                url=url,
                title="",
                snippet="",
                query="file_list",
                source_name=SOURCE_NAME,
                discovery_reason=(
                    "grenouillemoi"
                    if fmt == "grenouillemoi"
                    else f"csv offset {offset}"
                ),
            )
        )
    return out
