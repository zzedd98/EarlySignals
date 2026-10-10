"""
Téléchargement et mise en cache de la liste standard Tranco (top 1M).
URLs officielles : https://tranco-list.eu/ (ZIP quotidien, format type Alexa : rang,domaine).
"""
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx

from seed_builder_prospects.logging_utils import get_logger

logger = get_logger(__name__)

TRANCO_TOP_1M_ZIP = "https://tranco-list.eu/top-1m.csv.zip"
TRANCO_TOP_1M_SUB_ZIP = "https://tranco-list.eu/top-1m-incl-subdomains.csv.zip"
ZIP_INNER_CSV = "top-1m.csv"


def _meta_write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ensure_tranco_csv(
    cache_dir: Path,
    *,
    subdomains: bool = False,
    refresh: bool = False,
) -> Path:
    """
    Télécharge le ZIP Tranco si besoin, extrait top-1m.csv dans le cache.
    Deux variantes (standard vs sous-domaines) sont stockées séparément.
    """
    base = Path(cache_dir) / "tranco"
    base.mkdir(parents=True, exist_ok=True)
    variant = "subdomains" if subdomains else "standard"
    csv_path = base / f"top-1m-{variant}.csv"
    meta_path = base / f".meta-{variant}.json"
    url = TRANCO_TOP_1M_SUB_ZIP if subdomains else TRANCO_TOP_1M_ZIP

    if csv_path.exists() and not refresh:
        logger.info("Tranco : utilisation du cache %s", csv_path)
        return csv_path

    logger.info("Tranco : téléchargement %s", url)
    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        last_modified = r.headers.get("last-modified", "")
        data = r.content

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        if ZIP_INNER_CSV not in names:
            raise RuntimeError(
                f"ZIP Tranco inattendu (pas de {ZIP_INNER_CSV}): {names[:5]}"
            )
        with zf.open(ZIP_INNER_CSV) as zsrc:
            csv_path.write_bytes(zsrc.read())

    _meta_write(
        meta_path,
        {
            "url": url,
            "last_modified": last_modified,
            "variant": variant,
        },
    )
    logger.info("Tranco : CSV extrait -> %s (%s)", csv_path, last_modified or "sans Last-Modified")
    return csv_path
