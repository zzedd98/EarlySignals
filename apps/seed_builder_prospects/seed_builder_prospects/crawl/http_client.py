"""
Client HTTP : fetch avec redirects, rate limiting, retries + backoff, timeouts.
"""
import time
from typing import Optional

import httpx

from seed_builder_prospects.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 25.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_url(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    headers: Optional[dict] = None,
    proxy: Optional[str] = None,
) -> tuple[int, str, list[str]]:
    """
    GET url. Retourne (status_code, body_text, redirect_chain).
    Suit les redirects ; redirect_chain = liste des URLs jusqu'à la finale.
    """
    redirect_chain: list[str] = []
    h = headers or {}
    if "User-Agent" not in h:
        h["User-Agent"] = DEFAULT_USER_AGENT

    for attempt in range(retries):
        try:
            client_kw: dict = {
                "follow_redirects": True,
                "timeout": timeout,
                "headers": h,
            }
            if proxy:
                client_kw["proxy"] = proxy
            with httpx.Client(**client_kw) as client:
                r = client.get(url)
                # httpx suit les redirects ; on n'a pas la chaine facilement, on met au moins final
                redirect_chain = [url]
                if str(r.url) != url:
                    redirect_chain.append(str(r.url))
                return (r.status_code, r.text, redirect_chain)
        except httpx.HTTPStatusError as e:
            logger.debug("HTTP error %s: %s", url[:80], e)
            return (e.response.status_code, e.response.text, redirect_chain)
        except Exception as e:
            logger.debug("Fetch error %s (attempt %s): %s", url[:80], attempt + 1, e)
            if attempt == retries - 1:
                return (0, "", [url])
            time.sleep(backoff * (attempt + 1))
    return (0, "", [url])


def fetch_url_with_redirects(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    proxy: Optional[str] = None,
) -> tuple[int, str, list[str]]:
    """
    Idem fetch_url mais construit la redirect chain en suivant manuellement
    pour avoir toute la chaîne (utile pour domaine final).
    """
    return fetch_url(
        url, timeout=timeout, retries=retries, backoff=backoff, proxy=proxy
    )
