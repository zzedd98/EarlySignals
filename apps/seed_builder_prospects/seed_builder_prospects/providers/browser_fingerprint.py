"""
Profils navigateur réalistes pour Playwright (UA, locale, timezone, viewport, headers).
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserFingerprint:
    user_agent: str
    locale: str
    timezone_id: str
    viewport: dict[str, int]
    platform: str
    languages: list[str]
    hardware_concurrency: int
    device_memory: int
    color_scheme: str


_PROFILES: list[BrowserFingerprint] = [
    BrowserFingerprint(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="fr-FR",
        timezone_id="Europe/Paris",
        viewport={"width": 1920, "height": 1080},
        platform="Win32",
        languages=["fr-FR", "fr", "en-US", "en"],
        hardware_concurrency=8,
        device_memory=8,
        color_scheme="light",
    ),
    BrowserFingerprint(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        locale="fr-FR",
        timezone_id="Europe/Paris",
        viewport={"width": 1536, "height": 864},
        platform="Win32",
        languages=["fr-FR", "fr", "en-US", "en"],
        hardware_concurrency=12,
        device_memory=8,
        color_scheme="light",
    ),
    BrowserFingerprint(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="fr-FR",
        timezone_id="Europe/Paris",
        viewport={"width": 1680, "height": 1050},
        platform="MacIntel",
        languages=["fr-FR", "fr", "en-US", "en"],
        hardware_concurrency=8,
        device_memory=8,
        color_scheme="light",
    ),
    BrowserFingerprint(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ),
        locale="fr-FR",
        timezone_id="Europe/Paris",
        viewport={"width": 1366, "height": 768},
        platform="Linux x86_64",
        languages=["fr-FR", "fr", "en-US", "en"],
        hardware_concurrency=8,
        device_memory=8,
        color_scheme="light",
    ),
]


def choose_browser_fingerprint(
    exclude_user_agent: str | None = None,
) -> BrowserFingerprint:
    """Retourne un profil aléatoire parmi des profils desktop cohérents.

    Si `exclude_user_agent` est fourni, essaie d'éviter de reprendre exactement
    le même profil qu'au cycle précédent.
    """
    if exclude_user_agent:
        filtered = [p for p in _PROFILES if p.user_agent != exclude_user_agent]
        if filtered:
            return random.choice(filtered)
    return random.choice(_PROFILES)


def chromium_launch_args(locale: str) -> list[str]:
    """Args Chromium raisonnables pour limiter les flags d'automatisation visibles."""
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-first-run",
        "--no-default-browser-check",
        f"--lang={locale}",
    ]


def build_extra_http_headers(fp: BrowserFingerprint) -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
    }


def stealth_init_script(fp: BrowserFingerprint) -> str:
    languages_js = ", ".join([f"'{lang}'" for lang in fp.languages])
    return f"""
    (() => {{
      const nav = window.navigator;
      try {{
        Object.defineProperty(nav, 'webdriver', {{ get: () => undefined, configurable: true }});
      }} catch (e) {{}}
      try {{
        Object.defineProperty(nav, 'languages', {{ get: () => [{languages_js}], configurable: true }});
      }} catch (e) {{}}
      try {{
        Object.defineProperty(nav, 'platform', {{ get: () => '{fp.platform}', configurable: true }});
      }} catch (e) {{}}
      try {{
        Object.defineProperty(nav, 'hardwareConcurrency', {{ get: () => {fp.hardware_concurrency}, configurable: true }});
      }} catch (e) {{}}
      try {{
        Object.defineProperty(nav, 'deviceMemory', {{ get: () => {fp.device_memory}, configurable: true }});
      }} catch (e) {{}}
      try {{
        Object.defineProperty(nav, 'maxTouchPoints', {{ get: () => 0, configurable: true }});
      }} catch (e) {{}}
      try {{
        const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
        if (originalQuery) {{
          window.navigator.permissions.query = (parameters) => (
            parameters && parameters.name === 'notifications'
              ? Promise.resolve({{ state: Notification.permission }})
              : originalQuery(parameters)
          );
        }}
      }} catch (e) {{}}
      if (!window.chrome) {{
        window.chrome = {{ runtime: {{}}, app: {{}}, csi: () => ({{}}), loadTimes: () => ({{}}) }};
      }}
    }})();
    """
