"""
Provider Google via crawl HTML (Playwright) — pas d'API.
Recherches avancées Google, parsing des résultats, avec fingerprint spoofing / anti-détection.
"""

import asyncio
import json
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import parse_qs, unquote, urlparse

import aiohttp

from seed_builder_prospects.config import format_pipeline_limit, is_unlimited, limit_reached
from seed_builder_prospects.logging_utils import get_logger
from seed_builder_prospects.providers.base import DiscoveryResult, SearchProviderBase
from seed_builder_prospects.providers.browser_fingerprint import (
    build_extra_http_headers,
    chromium_launch_args,
    choose_browser_fingerprint,
    stealth_init_script,
)

logger = get_logger(__name__)

GOOGLE_SEARCH_URL = "https://www.google.com/search"
# Délai entre requêtes (secondes) pour limiter la détection
MIN_DELAY = 8
MAX_DELAY = 20


def _load_resume_state(state_file: Optional[str]) -> dict:
    if not state_file:
        return {}
    p = Path(state_file)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_resume_state(state_file: Optional[str], state: dict) -> None:
    if not state_file:
        return
    p = Path(state_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def _clear_resume_state(state_file: Optional[str]) -> None:
    if not state_file:
        return
    p = Path(state_file)
    if p.exists():
        p.unlink()


def _extract_proxy_port(proxy: Optional[dict]) -> Optional[int]:
    if not proxy:
        return None
    server = proxy.get("server")
    if not server:
        return None
    try:
        parsed = urlparse(server)
        return parsed.port
    except Exception:
        return None


def _find_reset_script() -> Optional[Path]:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "reset_modem.py"
        if candidate.exists():
            return candidate
    return None


def _run_modem_reset(proxy_port: int) -> bool:
    script = _find_reset_script()
    if not script:
        logger.error(
            "[Google] reset_modem.py introuvable dans l'arborescence du projet"
        )
        return False
    logger.info("[Google] Lancement reset modem via %s (port=%d)", script, proxy_port)
    try:
        result = subprocess.run(
            [sys.executable, str(script), str(proxy_port)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout:
            logger.info("[Google][reset_modem] stdout:\n%s", result.stdout.strip())
        if result.stderr:
            logger.warning("[Google][reset_modem] stderr:\n%s", result.stderr.strip())
        if result.returncode == 0:
            logger.info("[Google] Reset modem terminé avec succès")
            return True
        logger.error("[Google] Reset modem échoué (code=%d)", result.returncode)
        return False
    except Exception as exc:
        logger.error("[Google] Erreur lors de l'exécution reset_modem.py: %s", exc)
        return False


def _extract_real_url(href: str) -> str:
    """Extrait l'URL réelle depuis le redirect Google /url?q=..."""
    if not href or not href.strip():
        return ""
    href = href.strip()
    if href.startswith("http") and "google.com" not in href:
        return href
    if "/url?" in href or href.startswith("/url?"):
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        if "q" in qs:
            return unquote(qs["q"][0])
    return href


def _parse_google_results(html: str, query: str) -> list[DiscoveryResult]:
    """Parse le HTML des résultats Google (div.g, liens, titres, snippets)."""
    from bs4 import BeautifulSoup
    from seed_builder_prospects.config import BLACKLIST_DOMAINS
    from seed_builder_prospects.crawl.url_normalize import canonical_domain_from_url

    results: list[DiscoveryResult] = []
    soup = BeautifulSoup(html, "html.parser")

    # Essayer plusieurs sélecteurs pour les conteneurs de résultats
    # Google utilise différentes structures selon le type de résultat
    result_containers = soup.select(
        "div.g, "  # Résultats organiques classiques
        "div[data-sokoban-container] > div, "  # Conteneur principal
        "div.tF2Cxc, "  # Autre format de résultat
        "div.g-blk, "  # Blocs de résultats
        "div[data-ved]"  # Résultats avec attribut data-ved
    )

    # Si aucun conteneur trouvé avec les sélecteurs spécifiques, essayer de trouver tous les liens /url?q=
    if not result_containers:
        logger.debug(
            "[Google] Aucun conteneur div.g trouvé, recherche alternative de liens..."
        )
        # Chercher directement tous les liens de résultats Google
        all_result_links = soup.select('a[href^="/url?q="], a[href*="/url?q="]')
        seen_urls = set()

        for link in all_result_links:
            href = link.get("href", "")
            if not href:
                continue

            url = _extract_real_url(href)
            if not url or "google.com" in url or url.startswith("/"):
                continue

            # Éviter les doublons
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Filtrer les domaines blacklistés
            domain = canonical_domain_from_url(url)
            if domain:
                domain_lower = domain.lower()
                if any(
                    blacklisted in domain_lower for blacklisted in BLACKLIST_DOMAINS
                ):
                    continue

            # Chercher le titre dans le parent ou proche parent
            parent = link.find_parent(["div", "article", "section"])
            title = ""
            if parent:
                title_el = parent.select_one("h3, h2, .LC20lb, .DKV0Md")
                if title_el:
                    title = title_el.get_text(strip=True)
                else:
                    # Si pas de titre trouvé, utiliser le texte du lien
                    title = link.get_text(strip=True)

            # Chercher le snippet
            snippet = ""
            if parent:
                snippet_el = parent.select_one(
                    ".VwiC3b, .yXK7lf, [data-sncf], .IsZvec, .s, .st"
                )
                if snippet_el:
                    snippet = snippet_el.get_text(strip=True)[:300]

            results.append(
                DiscoveryResult(
                    url=url,
                    title=title,
                    snippet=snippet,
                    query=query,
                    source_name="google",
                )
            )

        return results

    # Parser les conteneurs trouvés
    for block in result_containers:
        # Chercher le lien de plusieurs façons
        link_el = (
            block.select_one(".yuRUbf a")  # Structure classique
            or block.select_one("a[href^='/url?']")  # Lien avec redirect Google
            or block.select_one(
                "a[href*='/url?q=']"
            )  # Lien avec redirect Google (variante)
            or block.select_one("a[href^='http']")  # Lien direct
            or block.select_one("cite")  # URL affichée
            or block.select_one("h3 a")  # Lien dans le titre
            or block.select_one("h2 a")  # Lien dans le titre h2
            or block.select_one("a[data-ved]")  # Lien avec attribut data-ved
        )

        if not link_el:
            continue

        # Extraire l'URL
        href = link_el.get("href", "")
        if not href and link_el.name == "cite":
            # Si c'est un cite, l'URL est dans le texte
            href = link_el.get_text(strip=True)

        if not href:
            continue

        url = _extract_real_url(href)
        if not url or "google.com" in url or url.startswith("/"):
            continue

        # Filtrer les domaines blacklistés (au lieu de les exclure dans la requête)
        domain = canonical_domain_from_url(url)
        if domain:
            domain_lower = domain.lower()
            # Vérifier si le domaine est dans la blacklist
            if any(blacklisted in domain_lower for blacklisted in BLACKLIST_DOMAINS):
                continue

        # Extraire le titre
        title_el = (
            block.select_one("h3")
            or block.select_one("h2")
            or block.select_one(".LC20lb")
            or block.select_one(".DKV0Md")
            or block.select_one(".CCgQ5")  # Titre pour résultats sponsorisés
        )
        title = title_el.get_text(strip=True) if title_el else ""

        # Extraire le snippet/description
        snippet_el = (
            block.select_one(".VwiC3b")  # Snippet classique
            or block.select_one(".yXK7lf")  # Autre format
            or block.select_one("[data-sncf]")  # Format alternatif
            or block.select_one(".IsZvec")  # Format alternatif
            or block.select_one(".s")  # Format simple
            or block.select_one(".st")  # Format simple alternatif
            or block.select_one(".p4wth")  # Snippet pour résultats sponsorisés
        )
        snippet = snippet_el.get_text(strip=True)[:300] if snippet_el else ""

        results.append(
            DiscoveryResult(
                url=url, title=title, snippet=snippet, query=query, source_name="google"
            )
        )

    return results


async def _detect_captcha(page) -> bool:
    """Détecte si un captcha est présent sur la page."""
    try:
        html = await page.content()
        html_lower = html.lower()
        captcha_indicators = [
            "captcha",
            "recaptcha",
            "hcaptcha",
            "turnstile",
            "verify you are human",
            "verify you're not a robot",
            "challenge",
            "security check",
        ]
        if any(indicator in html_lower for indicator in captcha_indicators):
            return True
        captcha_iframes = await page.locator(
            "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='turnstile']"
        ).count()
        if captcha_iframes > 0:
            return True
        captcha_elements = await page.locator(
            ".g-recaptcha, #captcha, .h-captcha, .cf-turnstile"
        ).count()
        if captcha_elements > 0:
            return True
        return False
    except Exception as e:
        logger.debug("[Google] Erreur lors de la détection de captcha: %s", e)
        return False


async def _solve_captcha_with_capsolver(page, api_key: str) -> bool:
    """Résout un captcha avec CapSolver."""
    try:
        logger.info("[Google] Détection d'un captcha, résolution avec CapSolver...")
        html = await page.content()
        html_lower = html.lower()
        captcha_type = None
        site_key = None

        if "recaptcha" in html_lower:
            site_key_match = await page.evaluate(
                """
                () => {
                    const scripts = Array.from(document.querySelectorAll('script'));
                    for (const script of scripts) {
                        const match = script.textContent?.match(/['"]?sitekey['"]?\\s*[:=]\\s*['"]([^'"]+)['"]/i);
                        if (match) return match[1];
                    }
                    const iframe = document.querySelector('iframe[src*="recaptcha"]');
                    if (iframe) {
                        const match = iframe.src.match(/[?&]k=([^&]+)/);
                        if (match) return match[1];
                    }
                    return null;
                }
            """
            )
            if site_key_match:
                site_key = site_key_match
                captcha_type = "ReCaptchaV2TaskProxyLess"
        elif "hcaptcha" in html_lower:
            site_key_match = await page.evaluate(
                """
                () => {
                    const iframe = document.querySelector('iframe[src*="hcaptcha"]');
                    if (iframe) {
                        const match = iframe.src.match(/[?&]sitekey=([^&]+)/);
                        if (match) return match[1];
                    }
                    return null;
                }
            """
            )
            if site_key_match:
                site_key = site_key_match
                captcha_type = "HCaptchaTaskProxyLess"
        elif "turnstile" in html_lower or "cf-turnstile" in html_lower:
            site_key_match = await page.evaluate(
                """
                () => {
                    const element = document.querySelector('[data-sitekey], .cf-turnstile');
                    if (element) {
                        return element.getAttribute('data-sitekey') || element.dataset.sitekey;
                    }
                    return null;
                }
            """
            )
            if site_key_match:
                site_key = site_key_match
                captcha_type = "AntiTurnstileTaskProxyLess"

        if not captcha_type or not site_key:
            logger.warning(
                "[Google] Type de captcha non détecté ou site key introuvable"
            )
            return False

        logger.info(
            "[Google] Type de captcha détecté: %s, site key: %s",
            captcha_type,
            site_key[:20] + "...",
        )
        page_url = page.url

        async with aiohttp.ClientSession() as session:
            create_task_url = "https://api.capsolver.com/createTask"
            task_data = {
                "clientKey": api_key,
                "task": {
                    "type": captcha_type,
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                },
            }
            async with session.post(create_task_url, json=task_data) as resp:
                create_result = await resp.json()
            if create_result.get("errorId") != 0:
                logger.error(
                    "[Google] Erreur CapSolver: %s",
                    create_result.get("errorDescription"),
                )
                return False

            task_id = create_result.get("taskId")
            logger.info("[Google] Tâche CapSolver créée: %s", task_id)
            get_result_url = "https://api.capsolver.com/getTaskResult"
            max_attempts = 60
            attempt = 0

            while attempt < max_attempts:
                await asyncio.sleep(2)
                attempt += 1
                async with session.post(
                    get_result_url, json={"clientKey": api_key, "taskId": task_id}
                ) as resp:
                    result = await resp.json()

                if result.get("status") == "ready":
                    solution = result.get("solution", {})
                    token = (
                        solution.get("gRecaptchaResponse")
                        or solution.get("token")
                        or solution.get("turnstileToken")
                    )
                    if token:
                        logger.info("[Google] Captcha résolu avec succès!")
                        if captcha_type == "ReCaptchaV2TaskProxyLess":
                            await page.evaluate(
                                f"""
                                (token) => {{
                                    const textarea = document.querySelector('textarea[name="g-recaptcha-response"]');
                                    if (textarea) {{
                                        textarea.value = token;
                                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    }}
                                    window.grecaptcha?.callback?.(token);
                                }}
                            """,
                                token,
                            )
                        elif captcha_type == "HCaptchaTaskProxyLess":
                            await page.evaluate(
                                f"""
                                (token) => {{
                                    const textarea = document.querySelector('textarea[name="h-captcha-response"]');
                                    if (textarea) {{
                                        textarea.value = token;
                                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    }}
                                }}
                            """,
                                token,
                            )
                        elif captcha_type == "AntiTurnstileTaskProxyLess":
                            await page.evaluate(
                                f"""
                                (token) => {{
                                    const input = document.querySelector('input[name="cf-turnstile-response"]');
                                    if (input) {{
                                        input.value = token;
                                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    }}
                                }}
                            """,
                                token,
                            )
                        await asyncio.sleep(1)
                        submit_btn = await page.query_selector(
                            'button[type="submit"], input[type="submit"], button:has-text("Submit"), button:has-text("Verify")'
                        )
                        if submit_btn:
                            await submit_btn.click()
                            await asyncio.sleep(2)
                        return True
                elif result.get("status") == "processing":
                    if attempt % 10 == 0:
                        logger.info(
                            "[Google] Résolution du captcha en cours... (tentative %d/%d)",
                            attempt,
                            max_attempts,
                        )
                    continue
                else:
                    logger.error(
                        "[Google] Erreur lors de la résolution: %s",
                        result.get("errorDescription"),
                    )
                    return False

            logger.error("[Google] Timeout lors de la résolution du captcha")
            return False
    except Exception as e:
        logger.error(
            "[Google] Erreur lors de la résolution du captcha avec CapSolver: %s", e
        )
        return False


async def _random_mouse_movement(page, num_movements: int = 3):
    """Fait bouger la souris de manière aléatoire pour simuler un comportement humain."""
    try:
        viewport_size = page.viewport_size
        if not viewport_size:
            viewport_size = {"width": 1920, "height": 1080}

        width = viewport_size["width"]
        height = viewport_size["height"]

        # Position initiale aléatoire
        current_x = random.randint(100, width - 100)
        current_y = random.randint(100, height - 100)

        for _ in range(num_movements):
            # Nouvelle position aléatoire
            target_x = random.randint(100, width - 100)
            target_y = random.randint(100, height - 100)

            # Mouvement avec courbe naturelle (pas en ligne droite)
            steps = random.randint(5, 15)
            for step in range(steps):
                # Interpolation avec courbe légère
                t = step / steps
                # Courbe ease-in-out
                ease_t = t * t * (3 - 2 * t)
                x = int(current_x + (target_x - current_x) * ease_t)
                y = int(current_y + (target_y - current_y) * ease_t)

                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.01, 0.03))

            current_x = target_x
            current_y = target_y
            await asyncio.sleep(random.uniform(0.1, 0.3))

        logger.debug("[Google] Mouvements de souris aléatoires effectués")
    except Exception as e:
        logger.debug("[Google] Erreur lors des mouvements de souris: %s", e)


async def _accept_google_cookies(page) -> bool:
    """Accepte les cookies Google si la page de consentement est présente."""
    try:
        # Attendre un peu pour que la page se charge
        await asyncio.sleep(random.uniform(1.0, 2.0))

        # Vérifier si on est sur la page de consentement
        if "consent.google" not in page.url:
            # Vérifier si le bouton d'acceptation est présent même si l'URL n'est pas consent.google
            accept_button = await page.query_selector(
                'button:has-text("Tout accepter"), '
                'button:has-text("Accept all"), '
                'button:has-text("J\'accepte"), '
                'button:has-text("I agree"), '
                'button[id*="accept"], '
                'button[aria-label*="Accept"], '
                'button[aria-label*="accepter"], '
                "#L2AGLb, "
                'button:has-text("Accepter")'
            )
            if not accept_button:
                return False
        else:
            # Sur la page consent.google, chercher le bouton
            accept_button = await page.query_selector(
                'button:has-text("Tout accepter"), '
                'button:has-text("Accept all"), '
                'button:has-text("J\'accepte"), '
                'button:has-text("I agree"), '
                'button[id*="accept"], '
                'button[aria-label*="Accept"], '
                'button[aria-label*="accepter"], '
                "#L2AGLb, "
                'button:has-text("Accepter")'
            )
            if not accept_button:
                return False

        logger.info(
            "[Google] Page de consentement détectée, acceptation des cookies..."
        )

        # Faire bouger la souris avant de cliquer
        await _random_mouse_movement(page, num_movements=random.randint(2, 4))
        await asyncio.sleep(random.uniform(0.5, 1.0))

        # Obtenir la position du bouton et déplacer la souris vers lui
        box = await accept_button.bounding_box()
        if box:
            await page.mouse.move(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
            await asyncio.sleep(random.uniform(0.2, 0.4))

        # Cliquer sur le bouton
        await accept_button.click(delay=random.uniform(100, 200))
        logger.info("[Google] Cookies acceptés")

        # Attendre que la page se mette à jour
        await asyncio.sleep(random.uniform(1.5, 2.5))

        return True
    except Exception as e:
        logger.debug("[Google] Erreur lors de l'acceptation des cookies: %s", e)
        return False


async def _run_search(
    page,
    query: str,
    max_per_query: int,
    delay_min: float,
    delay_max: float,
    timeout_ms: int = 25000,
    capsolver_api_key: Optional[str] = None,
    speed_mode: str = "fast",
    start_offset: int = 0,
    page_limit_per_run: int = 10,
) -> tuple[list[DiscoveryResult], int, bool, bool]:
    """Exécute une recherche Google et parse la première page (éventuellement suivantes)."""
    # D'abord, aller sur la page d'accueil de Google (comportement humain)
    # Avec retries pour les erreurs de proxy/connexion
    max_retries = 3
    retry_delay = 2.0
    for attempt in range(max_retries):
        try:
            logger.info(
                "[Google] Navigation vers la page d'accueil Google... (tentative %d/%d)",
                attempt + 1,
                max_retries,
            )

            navigation_timeout = max(timeout_ms, 60000)  # Au moins 60 secondes
            await page.goto(
                "https://www.google.com",
                wait_until="domcontentloaded",
                timeout=navigation_timeout,
            )
            await asyncio.sleep(random.uniform(1.5, 2.5))
            await _accept_google_cookies(page)
            break  # Succès, sortir de la boucle

        except Exception as e:
            error_msg = str(e)
            is_proxy_error = (
                "ERR_PROXY" in error_msg
                or "proxy" in error_msg.lower()
                or "connection" in error_msg.lower()
            )

            if attempt < max_retries - 1:
                if is_proxy_error:
                    logger.warning(
                        "[Google] Erreur proxy/connexion (tentative %d/%d): %s",
                        attempt + 1,
                        max_retries,
                        error_msg[:100],
                    )
                    logger.info(
                        "[Google] Nouvelle tentative dans %.1fs...", retry_delay
                    )
                else:
                    logger.warning(
                        "[Google] Erreur navigation (tentative %d/%d): %s",
                        attempt + 1,
                        max_retries,
                        error_msg[:100],
                    )
                    logger.info(
                        "[Google] Nouvelle tentative dans %.1fs...", retry_delay
                    )
                await asyncio.sleep(retry_delay)
                retry_delay *= 1.5  # Backoff exponentiel
            else:
                # Dernière tentative échouée
                if is_proxy_error:
                    logger.error(
                        "[Google] Échec de connexion proxy après %d tentatives",
                        max_retries,
                    )
                    logger.error(
                        "[Google] Vérifiez que le proxy est actif et accessible: %s",
                        error_msg[:200],
                    )
                else:
                    logger.error(
                        "[Google] Échec de navigation après %d tentatives: %s",
                        max_retries,
                        error_msg[:200],
                    )
                return [], start_offset, False, False

    # Faire bouger la souris avant de lancer la recherche (comportement humain)
    await _random_mouse_movement(page, num_movements=random.randint(2, 4))
    await asyncio.sleep(random.uniform(0.5, 1.0))

    try:
        if start_offset > 0:
            logger.info(
                "[Google] Reprise via recherche standard + paramètre start=%d",
                start_offset,
            )
            search_box = page.locator('input[name="q"], textarea[name="q"], #APjFqb')
            await search_box.wait_for(state="visible", timeout=10000)
            await search_box.click()
            await asyncio.sleep(random.uniform(0.2, 0.4))
            if speed_mode == "human":
                await search_box.type(query, delay=random.uniform(80, 150))
                await asyncio.sleep(random.uniform(0.5, 1.0))
            else:
                await search_box.fill(query)
                await asyncio.sleep(random.uniform(0.3, 0.6))

            # Soumettre une recherche "normale" en injectant start dans le formulaire.
            submit_ok = await page.evaluate(
                """
                (startValue) => {
                    const qInput =
                        document.querySelector('input[name="q"], textarea[name="q"], #APjFqb');
                    if (!qInput) return false;
                    const form = qInput.form || document.querySelector('form[action*="/search"]') || qInput.closest('form');
                    if (!form) return false;
                    let startInput = form.querySelector('input[name="start"]');
                    if (!startInput) {
                        startInput = document.createElement("input");
                        startInput.type = "hidden";
                        startInput.name = "start";
                        form.appendChild(startInput);
                    }
                    startInput.value = String(startValue);
                    if (typeof form.requestSubmit === "function") {
                        form.requestSubmit();
                    } else {
                        form.submit();
                    }
                    return true;
                }
                """,
                start_offset,
            )
            if not submit_ok:
                logger.warning(
                    "[Google] Reprise start=%d: échec injection/soumission formulaire",
                    start_offset,
                )
                return [], start_offset, False, False
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            current_url = page.url
            if f"start={start_offset}" not in current_url:
                logger.warning(
                    "[Google] Reprise start=%d non confirmée dans l'URL (%s)",
                    start_offset,
                    current_url,
                )
                return [], start_offset, False, False
        else:
            logger.info(
                "[Google] Recherche de la barre de recherche pour: %s", query[:50]
            )
            search_box = page.locator('input[name="q"], textarea[name="q"], #APjFqb')
            await search_box.wait_for(state="visible", timeout=10000)
            await search_box.click()
            await asyncio.sleep(random.uniform(0.2, 0.4))
            if speed_mode == "human":
                await search_box.type(query, delay=random.uniform(80, 150))
                await asyncio.sleep(random.uniform(0.5, 1.0))
            else:
                await search_box.fill(query)
                await asyncio.sleep(random.uniform(0.3, 0.6))
            logger.info("[Google] Lancement de la recherche...")
            await search_box.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            await asyncio.sleep(random.uniform(1.5, 2.0))

        title = await page.title()
        html = await page.content()

        # Diagnostic: vérifier ce qui est dans le HTML
        from bs4 import BeautifulSoup

        soup_temp = BeautifulSoup(html, "html.parser")
        div_g_count = len(soup_temp.select("div.g"))
        url_links_count = len(
            soup_temp.select('a[href^="/url?q="], a[href*="/url?q="]')
        )
        logger.debug(
            "[Google] Diagnostic HTML: div.g=%d, liens /url?q==%d",
            div_g_count,
            url_links_count,
        )

        # Vérifier si un captcha est présent et le résoudre si nécessaire
        has_captcha = await _detect_captcha(page)
        if has_captcha:
            logger.warning("[Google] Captcha détecté sur la page")
            return [], start_offset, False, True

        logger.info(
            "[Google] Page chargée | titre=%s | HTML len=%d",
            title[:80] if title else "",
            len(html),
        )
        if "consent.google" in page.url:
            logger.warning(
                "[Google] Redirection vers consent.google détectée — accepter les cookies manuellement si besoin"
            )
        if (
            "sorry" in html.lower()
            or "captcha" in html.lower()
            or "unusual traffic" in html.lower()
        ):
            logger.warning(
                "[Google] Contenu 'sorry/captcha/unusual traffic' détecté dans la page"
            )
    except Exception as e:
        logger.warning("[Google] Erreur fetch pour requête %s: %s", query[:50], e)
        return [], start_offset, False, False

    out = _parse_google_results(html, query)
    try:
        blocks_g = await page.locator("div.g").count()
    except Exception:
        blocks_g = -1
    logger.info(
        "[Google] div.g trouvés (page)=%s | Résultats parsés (BS4)=%d",
        blocks_g,
        len(out),
    )
    if len(out) == 0:
        logger.warning("[Google] Aucun résultat parsé — diagnostic en cours...")
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        n_links_url = len(soup.select("a[href^='/url?']")) + len(
            soup.select("a[href*='/url?q=']")
        )
        n_links_http = len(soup.select("a[href^='http']"))
        n_div_g = len(soup.select("div.g"))
        n_div_sokoban = len(soup.select("div[data-sokoban-container]"))
        logger.info(
            "[Google] Diagnostic: liens /url?q==%d, liens http=%d, div.g=%d, div[data-sokoban-container]=%d",
            n_links_url,
            n_links_http,
            n_div_g,
            n_div_sokoban,
        )

        # Afficher un échantillon du HTML pour debug
        body_content = soup.find("body")
        if body_content:
            body_text = body_content.get_text(strip=True)[:500]
            logger.debug(
                "[Google] Extrait du body (500 premiers caractères): %s", body_text
            )
    for i, r in enumerate(out[:15]):
        logger.info("  [%d] %s", i + 1, r.url[:70] if r.url else "")
    if len(out) > 15:
        logger.info("  ... et %d autres", len(out) - 15)
    collected = len(out)
    pages_scraped = 1
    current_start = start_offset

    # Pagination : page 2 si besoin (start=10)
    while collected < max_per_query:
        if page_limit_per_run > 0 and pages_scraped >= page_limit_per_run:
            logger.info(
                "[Google] Limite de %d pages atteinte pour ce run, arrêt volontaire",
                page_limit_per_run,
            )
            return out[:max_per_query], current_start + 10, True, False

        next_btn = await page.query_selector(
            'a[aria-label="Page suivante"], a#pnnext, a[id="pnnext"]'
        )
        if not next_btn:
            logger.info("[Google] Pas de lien 'Page suivante' — fin pagination")
            break
        logger.info("[Google] Clic 'Page suivante'...")
        await asyncio.sleep(random.uniform(0.8, 2.0))
        try:
            await next_btn.click()
            await asyncio.sleep(random.uniform(2, 5))
            current_start += 10
            pages_scraped += 1
            if await _detect_captcha(page):
                logger.warning("[Google] Captcha détecté pendant la pagination")
                return out[:max_per_query], current_start, False, True
            html = await page.content()
            more = _parse_google_results(html, query)
            logger.info(
                "[Google] Page suivante: %d nouveaux résultats parsés", len(more)
            )
            for r in more:
                if r.url and not any(x.url == r.url for x in out):
                    out.append(r)
                    collected += 1
                    if collected >= max_per_query:
                        break
            if len(more) == 0:
                break
        except Exception:
            break

    return out[:max_per_query], current_start + 10, False, False


class GooglePlaywrightProvider(SearchProviderBase):
    """
    Découverte via Google en crawl HTML avec Playwright.
    Fingerprint spoofing : playwright-stealth + args Chromium + viewport/locale/headers réalistes.
    """

    def __init__(
        self,
        headless: bool = True,
        delay_min: float = MIN_DELAY,
        delay_max: float = MAX_DELAY,
        timeout: float = 30.0,
        proxy: dict | None = None,
        capsolver_api_key: Optional[str] = None,
        speed_mode: str = "fast",
        page_limit_per_run: int = 0,
        resume_state_file: str = "./.cache/seed_builder_prospects/google_resume_state.json",
        force_start_offset: Optional[int] = None,
    ):
        self.headless = headless
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.timeout_ms = int(timeout * 1000)
        self.proxy = proxy
        self.capsolver_api_key = capsolver_api_key
        self.speed_mode = speed_mode
        self.page_limit_per_run = max(0, int(page_limit_per_run))
        self.resume_state_file = resume_state_file
        self.force_start_offset = (
            int(force_start_offset) if force_start_offset is not None else None
        )
        self._force_start_consumed = False
        self._last_fingerprint_user_agent: Optional[str] = None

    def search(self, query: str, max_per_query: int = 10) -> Iterator[DiscoveryResult]:
        """Sync wrapper : run async search once."""
        results = asyncio.run(self._search_async(query, max_per_query))
        for r in results:
            yield r

    async def _search_async(
        self, query: str, max_per_query: int
    ) -> list[DiscoveryResult]:
        """Lance le navigateur avec stealth, exécute la recherche, parse les résultats."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "playwright requis: pip install playwright && playwright install chromium"
            )

        # Utiliser async_playwright directement, sans playwright-stealth (plus simple = moins détecté)
        async with async_playwright() as p:
            fp = choose_browser_fingerprint(
                exclude_user_agent=self._last_fingerprint_user_agent
            )
            self._last_fingerprint_user_agent = fp.user_agent
            chromium_args = chromium_launch_args(fp.locale)

            launch_opts = dict(
                headless=self.headless,
                args=chromium_args,
            )
            # Ajout du proxy si configuré
            if self.proxy:
                launch_opts["proxy"] = self.proxy
                logger.info(
                    "[Google] Proxy configuré: %s", self.proxy.get("server", "N/A")
                )
            logger.info("[Google] Lancement navigateur headless=%s", self.headless)
            try:
                browser = await p.chromium.launch(**launch_opts)
            except Exception as e:
                error_msg = str(e)
                if "proxy" in error_msg.lower() or "connection" in error_msg.lower():
                    logger.error(
                        "[Google] Impossible de lancer le navigateur avec le proxy: %s",
                        error_msg[:200],
                    )
                    logger.error(
                        "[Google] Vérifiez que le proxy est actif et accessible"
                    )
                else:
                    logger.error(
                        "[Google] Erreur lors du lancement du navigateur: %s",
                        error_msg[:200],
                    )
                return []

            try:
                context = await browser.new_context(
                    user_agent=fp.user_agent,
                    viewport=fp.viewport,
                    locale=fp.locale,
                    timezone_id=fp.timezone_id,
                    color_scheme=fp.color_scheme,
                    extra_http_headers=build_extra_http_headers(fp),
                )
                await context.add_init_script(stealth_init_script(fp))
                logger.info(
                    "[Google] Fingerprint: locale=%s timezone=%s viewport=%sx%s",
                    fp.locale,
                    fp.timezone_id,
                    fp.viewport["width"],
                    fp.viewport["height"],
                )
                page = await context.new_page()
                logger.info("[Google] Nouvelle page ouverte")
                try:
                    return await _run_search(
                        page,
                        query,
                        max_per_query,
                        self.delay_min,
                        self.delay_max,
                        self.timeout_ms,
                        capsolver_api_key=self.capsolver_api_key,
                        speed_mode=self.speed_mode,
                    )
                finally:
                    await page.close()
                    await context.close()
            finally:
                await browser.close()
                logger.info("[Google] Session navigateur fermée (fin de cycle)")

        return []

    async def _discover_async_single_session(
        self,
        queries: list[str],
        max_results: int,
        per_query: int,
        existing_count: int = 0,
    ) -> list[DiscoveryResult]:
        """Exécute toutes les requêtes dans UNE session navigateur (cookies/session conservés)."""
        from seed_builder_prospects.crawl.url_normalize import (
            canonical_domain_with_path_from_url,
        )
        from playwright.async_api import async_playwright

        seen: set[str] = set()
        aggregated: list[DiscoveryResult] = []

        async with async_playwright() as p:
            fp = choose_browser_fingerprint()
            chromium_args = chromium_launch_args(fp.locale)
            launch_opts = {
                "headless": self.headless,
                "args": chromium_args,
            }
            if self.proxy:
                launch_opts["proxy"] = self.proxy
                logger.info(
                    "[Google] Proxy configuré: %s", self.proxy.get("server", "N/A")
                )

            logger.info(
                "[Google] Lancement navigateur unique (session persistante) headless=%s",
                self.headless,
            )
            browser = await p.chromium.launch(**launch_opts)
            try:
                context = await browser.new_context(
                    user_agent=fp.user_agent,
                    viewport=fp.viewport,
                    locale=fp.locale,
                    timezone_id=fp.timezone_id,
                    color_scheme=fp.color_scheme,
                    extra_http_headers=build_extra_http_headers(fp),
                )
                await context.add_init_script(stealth_init_script(fp))
                logger.info(
                    "[Google] Fingerprint: locale=%s timezone=%s viewport=%sx%s",
                    fp.locale,
                    fp.timezone_id,
                    fp.viewport["width"],
                    fp.viewport["height"],
                )
                page = await context.new_page()
                logger.info("[Google] Nouvelle page ouverte")
                logger.info(
                    "[Google] Compteur global avant ce cycle: %d/%d",
                    existing_count,
                    max_results,
                )
                try:
                    use_forced_start = (
                        self.force_start_offset is not None
                        and not self._force_start_consumed
                    )
                    if use_forced_start:
                        resume_state = {}
                        resume_query_idx = 0
                        resume_start = max(0, self.force_start_offset)
                        logger.info(
                            "[Google] Reprise forcée via --google-start=%d (fichier d'état ignoré)",
                            resume_start,
                        )
                        # Le start forcé ne doit servir qu'au démarrage manuel.
                        self._force_start_consumed = True
                    else:
                        resume_state = _load_resume_state(self.resume_state_file)
                        resume_query_idx = (
                            int(resume_state.get("query_index", 0))
                            if resume_state
                            else 0
                        )
                        resume_start = (
                            int(resume_state.get("start", 0)) if resume_state else 0
                        )
                    for i, q in enumerate(queries):
                        if limit_reached(len(aggregated), max_results):
                            break
                        if resume_state and i < resume_query_idx:
                            logger.info(
                                "[Google] Requête %d/%d ignorée (déjà traitée avant reprise)",
                                i + 1,
                                len(queries),
                            )
                            continue
                        if use_forced_start and i == 0:
                            start_offset = resume_start
                        else:
                            start_offset = (
                                resume_start
                                if (resume_state and i == resume_query_idx)
                                else 0
                            )
                        logger.info(
                            "[Google] Requête %d/%d: %s (start=%d)",
                            i + 1,
                            len(queries),
                            q[:70],
                            start_offset,
                        )
                        if i > 0:
                            delay = random.uniform(self.delay_min, self.delay_max)
                            logger.info(
                                "[Google] Délai anti-détection %.1fs avant la requête suivante",
                                delay,
                            )
                            await asyncio.sleep(delay)

                        results, next_start, batch_limit_reached, captcha_detected = (
                            await _run_search(
                                page,
                                q,
                                per_query,
                                self.delay_min,
                                self.delay_max,
                                self.timeout_ms,
                                capsolver_api_key=self.capsolver_api_key,
                                speed_mode=self.speed_mode,
                                start_offset=start_offset,
                                page_limit_per_run=self.page_limit_per_run,
                            )
                        )
                        logger.info(
                            "[Google] Requête terminée: %d résultats bruts",
                            len(results),
                        )

                        for r in results:
                            if limit_reached(len(aggregated), max_results):
                                break
                            domain = canonical_domain_with_path_from_url(r.url)
                            if not domain or domain in seen:
                                continue
                            seen.add(domain)
                            aggregated.append(r)
                            logger.info(
                                "[Google] Candidat ajouté: %s (total=%d/%d)",
                                domain,
                                existing_count + len(aggregated),
                                max_results,
                            )
                        # Une fois la requête de reprise consommée, revenir au comportement normal
                        resume_state = {}
                        if captcha_detected:
                            _save_resume_state(
                                self.resume_state_file,
                                {
                                    "query_index": i,
                                    "query": q,
                                    "start": next_start,
                                    "reason": "captcha",
                                    "updated_at": time.time(),
                                },
                            )
                            logger.warning(
                                "[Google] Arrêt immédiat: captcha détecté. Reprise possible avec start=%d",
                                next_start,
                            )
                            return aggregated
                        if batch_limit_reached and self.page_limit_per_run > 0:
                            _save_resume_state(
                                self.resume_state_file,
                                {
                                    "query_index": i,
                                    "query": q,
                                    "start": next_start,
                                    "reason": "page_batch_limit",
                                    "updated_at": time.time(),
                                },
                            )
                            logger.info(
                                "[Google] Arrêt volontaire après lot de pages. Reprise possible avec start=%d",
                                next_start,
                            )
                            return aggregated
                finally:
                    await page.close()
                    await context.close()
            finally:
                await browser.close()

        _clear_resume_state(self.resume_state_file)
        return aggregated


def _run_discover_async(
    provider: "GooglePlaywrightProvider", queries: list[str], max_results: int
) -> list[DiscoveryResult]:
    """Exécute les requêtes Google par lots.

    Comportement:
    - Par défaut: scrape en continu jusqu'au captcha puis stop.
    - Optionnel: si page_limit_per_run > 0, cycle par lots + reset modem.
    """
    from seed_builder_prospects.crawl.url_normalize import (
        canonical_domain_with_path_from_url,
    )

    per_query = (
        max(80, max_results * 2)
        if queries and not is_unlimited(max_results)
        else (10**9 if queries else 0)
    )
    logger.info(
        "[Google] %d requêtes à exécuter, max %s domaines uniques au total (limite globale)",
        len(queries),
        format_pipeline_limit(max_results),
    )
    aggregated: list[DiscoveryResult] = []
    seen_domains: set[str] = set()
    last_state_signature: tuple | None = None
    cycle = 0

    while not limit_reached(len(aggregated), max_results):
        cycle += 1
        logger.info("[Google] Cycle de scraping #%d", cycle)
        cycle_results = asyncio.run(
            provider._discover_async_single_session(
                queries,
                max_results,
                per_query,
                existing_count=len(aggregated),
            )
        )

        for r in cycle_results:
            domain = canonical_domain_with_path_from_url(r.url)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            aggregated.append(r)
            if limit_reached(len(aggregated), max_results):
                break

        state = _load_resume_state(provider.resume_state_file)
        if not state:
            # Pas d'état de reprise => run terminé normalement.
            break

        reason = state.get("reason")
        state_signature = (
            state.get("query_index"),
            state.get("start"),
            reason,
        )
        if state_signature == last_state_signature:
            logger.warning(
                "[Google] État de reprise inchangé entre deux cycles (%s), arrêt de sécurité",
                state_signature,
            )
            break
        last_state_signature = state_signature

        if reason == "captcha":
            logger.warning(
                "[Google] Arrêt du workflow: captcha détecté (reprise manuelle possible via state file)"
            )
            break
        if reason == "page_batch_limit" and provider.page_limit_per_run > 0:
            proxy_port = _extract_proxy_port(provider.proxy)
            if proxy_port is None:
                logger.warning(
                    "[Google] Lot terminé (%d pages) mais port proxy introuvable; pause 30s",
                    provider.page_limit_per_run,
                )
                time.sleep(30)
                continue
            logger.info(
                "[Google] Lot terminé (%d pages). Reset connexion modem puis reprise...",
                provider.page_limit_per_run,
            )
            if _run_modem_reset(proxy_port):
                continue
            logger.error(
                "[Google] Échec reset modem: arrêt du workflow pour éviter un état incohérent"
            )
            break

        logger.warning("[Google] Motif d'arrêt inconnu (%s), arrêt du workflow", reason)
        break

    logger.info(
        "[Google] Découverte terminée: %d candidats uniques (limite: %d)",
        len(aggregated),
        max_results,
    )
    return aggregated


# Patch discover pour Google Playwright : utiliser délais entre requêtes
def _google_playwright_discover(
    self: GooglePlaywrightProvider,
    queries: list[str],
    max_results: int,
    dedup_by_domain: bool = True,
) -> list[DiscoveryResult]:
    return _run_discover_async(self, queries, max_results)


# Remplacer la méthode discover pour ce provider
GooglePlaywrightProvider.discover = _google_playwright_discover  # type: ignore
