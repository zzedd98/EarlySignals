## 🚀 Lancer l’application pour la tester **à la main**

Ce fichier explique **comment démarrer chaque partie de l’app** pour la voir/cliquer dessus, **sans lancer aucun test automatique** (`pytest`, `ng test`, etc.).

---

### 1. Pré‑requis communs (une fois)
- **Installer les dépendances JS (monorepo)** :
```bash
pnpm install
```

- **Démarrer l’infrastructure Docker (Postgres, Redis, Meilisearch, MailHog)** :
```bash
pnpm docker:up
```

- **Préparer l’environnement Python partagé API/worker** :
```bash
cd apps/api
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

### 2. API FastAPI – backend (`apps/api`)
- **Démarrer l’API** :
```bash
cd apps/api
venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- **Vérifier visuellement** :
  - Docs Swagger : `http://localhost:8000/docs`
  - ReDoc : `http://localhost:8000/redoc`

---

### 3. Frontend Angular – dashboard web (`apps/web`)
- **Démarrer le front** :
```bash
cd apps/web
pnpm install       # si pas déjà fait
pnpm start         # équivalent à: ng serve --host 0.0.0.0 --port 4200
```

- **Utiliser l’UI** :
  - Application dispo sur `http://localhost:4200`
  - Tu peux créer un compte, te connecter, naviguer dans le dashboard, etc.

---

### 4. Scraper TypeScript – crawl de sites (`apps/scraper`)
- **Installer et lancer le scraper** :
```bash
cd apps/scraper
pnpm install                # première fois
npx playwright install chromium   # première fois pour le navigateur
pnpm dev                    # mode développement (watch)
```

- **Ce que tu peux observer** :
  - Le scraper va appeler l'API pour récupérer les domaines actifs
  - Il va crawler les pages et créer des snapshots en base
  - Suis les logs dans le terminal pour voir ce qu'il fait

- **Options de normalisation HTML** (pour réduire les faux positifs de changement) :
  
  Dans le fichier `.env` à la racine du projet, tu peux activer deux options :
  
  ```bash
  # Normalisation HTML : supprime timestamps, IDs aléatoires, nonces, etc.
  # Utile pour éviter que le même contenu soit considéré comme différent à cause de timestamps
  SCRAPER_NORMALIZE_HTML=true
  
  # Extraction de contenu stable : utilise uniquement le contenu principal (main, article, etc.)
  # Ignore headers, footers, sidebars, ads qui changent souvent
  SCRAPER_EXTRACT_STABLE_CONTENT=true
  ```
  
  **Mode par défaut (recommandé pour stocker le maximum de data)** :
  ```bash
  SCRAPER_NORMALIZE_HTML=false
  SCRAPER_EXTRACT_STABLE_CONTENT=false
  ```
  
  **Mode optimisé (moins de doublons, mais peut ignorer certains changements)** :
  ```bash
  SCRAPER_NORMALIZE_HTML=true
  SCRAPER_EXTRACT_STABLE_CONTENT=true
  ```
  
  Le HTML brut est **toujours stocké** dans la base de données, seul le **hash** (utilisé pour détecter les doublons) utilise le HTML normalisé/extrait.

---

### 5. Worker Python – détection de signaux & opportunités (`apps/worker`)
Prérequis :
- Infra Docker démarrée (`pnpm docker:up`)
- API déjà en route (`uvicorn main:app ...`)
- Fichier `.env` dans `apps/worker` avec au minimum :
  - `API_URL=http://localhost:8000`
  - `API_EMAIL=admin@example.com`
  - `API_PASSWORD=mot_de_passe_admin`

- **Démarrer le worker** :
```bash
cd apps/api
venv\Scripts\activate      # réutilise le même venv
cd ../worker
pip install -r requirements.txt   # première fois seulement
python main.py
```

- **Ce que tu peux observer** :
  - Logs dans le terminal : snapshots traités, signaux détectés, opportunités créées
  - Opportunités visibles ensuite dans le front (dashboard) et dans Meilisearch

---

### 6. Seed Builder Prospects – génération de domaines (`apps/seed_builder_prospects`)
C’est une brique **CLI**, pas d’UI, mais utile pour alimenter l’API en domaines.

- **Installer les dépendances** :
```bash
cd apps/api
venv\Scripts\activate
cd ../seed_builder_prospects
pip install -r requirements.txt
```

- **Générer une seed list (exemple)** :
```bash
cd apps/seed_builder_prospects
python -m seed_builder_prospects.cli --sources google --max-links 10
# ou uniquement Tranco :
# python -m seed_builder_prospects.cli --sources tranco --tranco-tld .fr --max-links 50
```

- **Importer une seed list dans l’API** (si tu as un CSV prêt) :
```bash
cd apps/seed_builder_prospects
python scripts/import_seed_to_api.py data/seed_prospects_grenouillemoi.csv `
  --api-url http://localhost:8000 `
  --email admin@example.com `
  --password 321321
```

Les domaines importés seront ensuite visibles dans l’interface admin/web et utilisés par le scraper.

---

### 7. Résumé ultra‑rapide (commandes à retenir)

cd C:\Users\User\Desktop\EarlySignals
cd apps/seed_builder_prospects



- **Infra Docker** : `pnpm docker:up`
- **BACK** : `cd apps/api ; venv\Scripts\activate ; uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- **FRONT** : `cd apps/web && pnpm start`
- **Scraper** : `cd apps/scraper && pnpm dev`
- **Worker** : `cd apps/api ; venv\Scripts\activate ; cd ../worker ; python main.py`
- **Seed Builder (CLI)** : `cd apps/seed_builder_prospects ; python -m seed_builder_prospects.cli --sources google --max-links 10` (sources possibles : `google`, `tranco`)


**Scoring Tranco — proxies Lightning + 1 terminal par worker** (recommandé) :

1. Copier `data/proxies.lightning.example.txt` → `data/proxies.lightning.txt` et mettre le vrai mot de passe.
2. Lancer :

```powershell
cd apps/seed_builder_prospects
python -m seed_builder_prospects.cli `
  --sources file_list `
  --input-domains "./data/tranco_fr_10k.csv" `
  --proxies-file "./data/proxies.lightning.txt" `
  --score-launch-terminals `
  --score-workers-parallel 10 `
  --max-results 2500 `
  --max-links 2500 `
  --max-pages 5 `
  --rate-limit 30 `
  --segment-min-score-recruitment 25 `
  --segment-min-score-b2b-seller 65 `
  --segment-min-score-multinationale 55 `
  --out "./data/seed_prospects_fr.csv"
```

Raccourci : `pwsh ./scripts/score_tranco_proxies_terminals.ps1`

Les workers tournent dans des fenêtres `cmd` séparées ; le terminal principal attend les fichiers `.done` puis fusionne le CSV final.

**Ancien mode (4G locale, threads dans le même terminal)** :

```powershell
python -m seed_builder_prospects.cli --sources file_list --input-domains "./data/tranco_fr_10k.csv" --score-workers-ports "101,102,103,104" --score-workers-parallel 4 --max-results 2500 --max-links 2500 --max-pages 5 --rate-limit 30 --segment-min-score-recruitment 25 --segment-min-score-b2b-seller 65 --segment-min-score-multinationale 55 --out "./data/seed_prospects_fr.csv"
```

COMMANDES POUR LANCER EN 10 TERMINAUX : 

SEEDBUILDER : 

cd apps/seed_builder_prospects

python -m seed_builder_prospects.cli `
  --sources file_list `
  --input-domains "./data/lespepitestech_domains.csv" `
  --score-launch-terminals `
  --score-workers-parallel 10 `
  --max-pages 5 `
  --segment-min-score-recruitment 20 `
  --segment-min-score-b2b-seller 20 `
  --segment-min-score-multinationale 20 `
  --out "./data/seed_prospects_pepites.csv"


SCRAPER / WORKERS (N terminaux au choix) :

```powershell
cd C:\Users\User\Desktop\EarlySignals

# Option 1 — la plus simple (PowerShell)
.\launch.ps1 scraper 30
.\launch.ps1 scraper 30 -Cache    # avec cache hash (plus lent au démarrage)
.\launch.ps1 worker 10

# Option 2 — sans pnpm
node scripts/launch.mjs scraper 30
node scripts/launch.mjs scraper 30 --cache
node scripts/launch.mjs worker 10

# Option 3 — via pnpm (le nombre après --)
pnpm run scraper -- 30
pnpm run scraper -- 30 --cache
pnpm run worker -- 10
```

- **scraper N** : N terminaux scraper, résumé à la fin, fenêtres ouvertes
- **cache** : désactivé par défaut (démarrage rapide). `--cache` ou `-Cache` charge les hashes depuis l'API pour skip les pages inchangées
- **worker N** : N terminaux signaux, fin quand plus de snapshots (2×15s), résumé agrégé, fenêtres ouvertes
- Défaut si omis : **10** terminaux