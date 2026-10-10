"""
Script de reset des cles 4G via Playwright.

Reset la connexion 4G en accedant a l'interface web du modem
via un proxy local sur le port specifie.

Version synchrone : pas d'asyncio, donc pas de boucle d'evenements ni socketpair
par processus, pour eviter la saturation des sockets (WinError 10055).
"""

import logging
import sys
import re
import time
import httpx
from playwright.sync_api import sync_playwright

# Configuration du logging - niveau ERROR pour réduire les logs
logging.basicConfig(
    level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# URL de l'interface web des modems Huawei
MODEM_WEB_URL = "http://192.168.8.1/#/mobileconnection"


def _safe_print(message: str) -> None:
    """Affichage robuste sous Windows cp1252/UTF-8 sans crash UnicodeEncodeError."""
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        sanitized = message.encode("ascii", errors="replace").decode("ascii")
        print(sanitized, flush=True)


def _get_modem_ip(proxy_port: int) -> str | None:
    """Récupère l'IP publique du modem via son proxy (synchrone)."""
    proxy_url = f"http://127.0.0.1:{proxy_port}"
    services = ["https://api.ipify.org", "https://ifconfig.me", "https://icanhazip.com"]

    for service in services:
        try:
            with httpx.Client(proxy=proxy_url, timeout=10.0) as client:
                response = client.get(service)
                if response.status_code == 200:
                    ip = response.text.strip()
                    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                        return ip
        except Exception:
            continue
    return None


def reset_modem_by_port(proxy_port: int) -> bool:
    """
    Reset un modem via son proxy local en utilisant Playwright (synchrone).

    Args:
        proxy_port: Port du proxy local (101, 102, etc.)

    Returns:
        True si le reset Playwright a réussi **et** que l'IP publique a changé,
        False sinon
    """
    playwright = None
    browser = None
    context = None

    try:
        _safe_print(f"[RESET] Starting Playwright reset for proxy port {proxy_port}...")

        # 1) Récupérer l'IP publique AVANT le reset
        old_ip = _get_modem_ip(proxy_port)
        if old_ip:
            _safe_print(
                f"[RESET] Current IP before reset (port {proxy_port}): {old_ip}"
            )
        else:
            _safe_print(
                f"[RESET] Unable to read current IP before reset (port {proxy_port})"
            )

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        proxy_config = {"server": f"http://127.0.0.1:{proxy_port}"}
        context = browser.new_context(proxy=proxy_config)
        page = context.new_page()

        _safe_print(f"[RESET] Opening modem web UI through proxy {proxy_port}...")
        # Le modem peut renvoyer ERR_EMPTY_RESPONSE ou ne pas émettre "load" : on utilise domcontentloaded et des retries
        goto_ok = False
        for attempt in range(1, 4):
            try:
                page.goto(
                    MODEM_WEB_URL,
                    timeout=30000,
                    wait_until="domcontentloaded",
                )
                goto_ok = True
                break
            except Exception as goto_err:
                if attempt < 3 and (
                    "ERR_EMPTY_RESPONSE" in str(goto_err) or "Timeout" in str(goto_err)
                ):
                    _safe_print(
                        f"[RESET] Attempt {attempt}/3 failed, retrying in 3s..."
                    )
                    page.wait_for_timeout(3000)
                else:
                    raise
        if not goto_ok:
            _safe_print("[RESET] Could not load modem web UI after retries")
            return False
        page.wait_for_timeout(2000)

        _safe_print("[RESET] Selecting profile...")
        page.locator("tr.table-data:nth-child(3)").click()
        page.wait_for_timeout(1000)

        _safe_print("[RESET] Enabling default profile...")
        page.evaluate(
            """() => {
            document.querySelector('#defaultProfile input[type="checkbox"]').click();
        }"""
        )

        page.wait_for_timeout(500)

        _safe_print("[RESET] Saving settings...")
        page.get_by_role("button", name="Save").click()
        page.wait_for_timeout(2000)

        _safe_print(
            f"[RESET] Playwright sequence completed, checking IP change (port {proxy_port})..."
        )

        # 2) Fermeture explicite pour libérer ressources tout de suite
        page.close()
        context.close()
        context = None
        browser.close()
        browser = None
        playwright.stop()
        playwright = None

        # 3) Vérifier que l'IP a bien changé après le reset
        max_attempts = 12
        for attempt in range(1, max_attempts + 1):
            time.sleep(5)
            new_ip = _get_modem_ip(proxy_port)

            if not new_ip:
                _safe_print(
                    f"[RESET] Attempt {attempt}/{max_attempts}: unable to read IP (port {proxy_port})"
                )
                continue

            if old_ip is None:
                _safe_print(
                    f"[RESET] IP obtained after reset (port {proxy_port}): {new_ip}"
                )
                return True

            if new_ip != old_ip:
                _safe_print(
                    f"[RESET] IP changed for port {proxy_port}: {old_ip} -> {new_ip}"
                )
                return True

            _safe_print(
                f"[RESET] Attempt {attempt}/{max_attempts}: IP still unchanged ({new_ip})"
            )

        _safe_print(
            f"[RESET] IP did not change after reset (port {proxy_port}). "
            f"Previous IP: {old_ip or 'unknown'}"
        )
        return False

    except Exception as e:
        _safe_print(f"[RESET] Error while resetting port {proxy_port}: {str(e)}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Libération garantie pour ne pas garder Chromium/sockets ouverts en cas d'exception
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        _safe_print("Usage: python reset_modem.py <proxy_port>")
        _safe_print("Example: python reset_modem.py 101")
        sys.exit(1)

    port = int(sys.argv[1])
    success = reset_modem_by_port(port)
    sys.exit(0 if success else 1)
