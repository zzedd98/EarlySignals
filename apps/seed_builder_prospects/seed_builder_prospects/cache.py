"""
Cache HTML par URL (hash) avec TTL 7 jours.
Stockage fichier : .cache/seed_builder_prospects/<hash>.html
"""
import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from .logging_utils import get_logger

logger = get_logger(__name__)

TTL_DAYS = 7
TTL_SECONDS = TTL_DAYS * 24 * 3600


def is_cacheable_http_response(status_code: int, html: str) -> bool:
    """Ne met en cache que les réponses HTTP exploitables (200 + corps non vide)."""
    return status_code == 200 and bool((html or "").strip())


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def get_cached_html(cache_dir: Path, url: str) -> Optional[tuple[str, int, list[str]]]:
    """
    Retourne (html, status_code, redirect_chain) si en cache et non expiré, sinon None.
    """
    if not cache_dir:
        return None
    h = _url_hash(url)
    meta_path = cache_dir / f"{h}.meta.json"
    html_path = cache_dir / f"{h}.html"
    if not meta_path.exists() or not html_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if time.time() - meta.get("ts", 0) > TTL_SECONDS:
            return None
        status_code = int(meta.get("status_code", 0) or 0)
        html = html_path.read_text(encoding="utf-8", errors="replace")
        if not is_cacheable_http_response(status_code, html):
            return None
        return (html, status_code, meta.get("redirect_chain", []))
    except Exception as e:
        logger.debug("Cache read error for %s: %s", url[:80], e)
        return None


def set_cached_html(
    cache_dir: Path,
    url: str,
    html: str,
    status_code: int = 200,
    redirect_chain: Optional[list[str]] = None,
) -> None:
    """Enregistre la réponse en cache (uniquement si status 200 et HTML non vide)."""
    if not cache_dir:
        return
    if not is_cacheable_http_response(status_code, html):
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    h = _url_hash(url)
    meta_path = cache_dir / f"{h}.meta.json"
    html_path = cache_dir / f"{h}.html"
    meta = {
        "url": url,
        "ts": time.time(),
        "status_code": status_code,
        "redirect_chain": redirect_chain or [],
    }
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        html_path.write_text(html, encoding="utf-8", errors="replace")
    except Exception as e:
        logger.debug("Cache write error for %s: %s", url[:80], e)
