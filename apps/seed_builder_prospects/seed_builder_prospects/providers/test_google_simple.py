"""
Script de test simple pour Google avec Playwright
Recherche à vitesse humaine sans captcha
"""
import asyncio
import random
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async


async def test_google_search():
    """Test simple de recherche Google avec vitesse humaine"""
    
    print("=" * 60)
    print("Script de test Google avec Playwright")
    print("Mode: Visible (non headless)")
    print("=" * 60)
    
    # Terme de recherche
    search_term = "startup"
    print(f"[*] Recherche sélectionnée: '{search_term}'")
    
    async with async_playwright() as p:
        print("[*] Lancement du navigateur Chromium...")
        
        # Lancer le navigateur avec anti-détection
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--lang=fr-FR",
            ],
        )
        
        # Créer un contexte avec user-agent réaliste
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        
        page = await context.new_page()
        
        try:
            # Étape 1: Aller sur la page d'accueil Google
            print("[*] Navigation vers Google...")
            await page.goto("https://www.google.com", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # Étape 2: Trouver la barre de recherche
            print("[*] Recherche de la barre de recherche...")
            search_box = page.locator('textarea[name="q"], input[name="q"]')
            await search_box.wait_for(state="visible", timeout=10000)
            
            # Étape 3: Cliquer sur la barre de recherche
            print("[*] Clic sur la barre de recherche...")
            await search_box.click()
            await asyncio.sleep(random.uniform(0.3, 0.6))
            
            # Étape 4: Taper à vitesse humaine
            print(f"[*] Saisie de la recherche '{search_term}' à vitesse humaine...")
            await search_box.type(search_term, delay=random.uniform(80, 150))
            
            # Étape 5: Attendre un peu avant d'appuyer sur Entrée
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            # Étape 6: Appuyer sur Entrée
            print("[*] Appui sur Entrée...")
            await search_box.press("Enter")
            
            # Étape 7: Attendre que les résultats se chargent
            print("[*] Attente du chargement des résultats...")
            await page.wait_for_selector("div.g, div[data-sokoban-container]", timeout=15000)
            await asyncio.sleep(random.uniform(2.0, 3.0))
            
            # Étape 8: Vérifier les résultats
            print("[*] Vérification des résultats...")
            results = await page.locator("div.g").count()
            print(f"[*] Nombre de résultats trouvés: {results}")
            
            # Afficher les premiers résultats
            if results > 0:
                print("\n[*] Premiers résultats:")
                for i in range(min(5, results)):
                    try:
                        result = page.locator("div.g").nth(i)
                        title = await result.locator("h3").first.inner_text()
                        link = await result.locator("a").first.get_attribute("href")
                        print(f"  [{i+1}] {title[:60]}")
                        print(f"      {link[:80] if link else 'N/A'}")
                    except Exception as e:
                        print(f"  [{i+1}] Erreur: {e}")
            
            # Afficher le titre de la page
            title = await page.title()
            print(f"\n[*] Titre de la page: {title[:80]}")
            
            # Afficher l'URL
            url = page.url
            print(f"[*] URL actuelle: {url[:100]}")
            
            # Vérifier s'il y a un captcha
            captcha_elements = await page.locator(
                '[class*="captcha"], [id*="captcha"], iframe[src*="recaptcha"], iframe[src*="challenges"]'
            ).count()
            if captcha_elements > 0:
                print("[!] ATTENTION: Captcha détecté sur la page!")
            else:
                print("[*] Aucun captcha détecté")
            
            print("\n[*] Test terminé. Le navigateur restera ouvert pendant 10 secondes...")
            await asyncio.sleep(10)
            
        except Exception as e:
            print(f"[ERREUR] Erreur lors de l'exécution: {e}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(5)
        
        finally:
            print("[*] Fermeture du navigateur...")
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_google_search())
