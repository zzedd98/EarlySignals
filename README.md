# Early Signals

**Early Signals** est un outil de veille business qui aide les agences et freelances B2B à détecter des opportunités business **AVANT** les autres via des signaux publics observables sur des sites web (recrutements, pricing, structuration, ajout d'outils/stack, nouveaux sites).

## 🎯 Vision Produit

Ne PAS être une base de leads. Être un **"radar"** : signaux → opportunités actionnables.

Qualité > quantité (5–10 opportunités/jour).

## 🏗️ Architecture

Monorepo avec :
- **apps/web** : Angular (dashboard + onboarding + billing + settings + admin)
- **apps/api** : FastAPI Python (auth, orgs, domaines, opportunités, notifications, billing/webhooks)
- **apps/scraper** : Node.js TypeScript Playwright (crawl/fetch pages, snapshots, probing routes)
- **apps/worker** : Python (processing: normalisation, dédup, détection signaux, scoring, enrichissement IA, notifications)
- **packages/shared** : schémas partagés (Zod côté TS, Pydantic côté Python) + types communs

### Infrastructure

- **PostgreSQL** : source de vérité + historique
- **Redis** : queue
- **Meilisearch** : recherche full-text + facettes
- **Docker Compose** : orchestration locale
- **MailHog** : emails locaux (dev)

## 🚀 Setup Local

### Prérequis

- Node.js >= 18
- pnpm >= 8
- Python >= 3.11
- Docker & Docker Compose
- **Important** : Docker Desktop doit être démarré avant de lancer `pnpm docker:up`

### Installation

1. **Cloner et installer les dépendances**

```bash
pnpm install
```

2. **Configurer l'environnement**

```bash
# Sur Windows PowerShell
Copy-Item env.example .env
# Sur Linux/Mac
cp env.example .env

# Éditer .env selon vos besoins
```

3. **Démarrer l'infrastructure**

```bash
pnpm docker:up
```

Cela démarre :
- PostgreSQL (port 5432)
- Redis (port 6379)
- Meilisearch (port 7700)
- MailHog (ports 1025 SMTP, 8025 Web UI)

Vérifier que tout est OK :

```bash
pnpm docker:logs
```

4. **Initialiser la base de données** (après Milestone 1)

```bash
pnpm db:migrate
```

5. **Démarrer les services** (après chaque milestone)

```bash
# API (FastAPI)
cd apps/api
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Worker (Python)
cd apps/worker
python -m worker.main

# Scraper (Node.js)
cd apps/scraper
pnpm dev

# Web (Angular)
cd apps/web
pnpm start
```

## 📁 Structure du Projet

```
EarlySignals/
├── apps/
│   ├── api/          # FastAPI backend
│   ├── web/          # Angular frontend
│   ├── scraper/      # Playwright scraper
│   └── worker/       # Python worker
├── packages/
│   └── shared/       # Schémas partagés (Zod/Pydantic)
├── docker-compose.yml
├── turbo.json
├── pnpm-workspace.yaml
└── package.json
```

## 🔧 Commandes Utiles

```bash
# Infrastructure
pnpm docker:up          # Démarrer l'infra
pnpm docker:down        # Arrêter l'infra
pnpm docker:logs        # Voir les logs

# Développement
pnpm dev                # Démarrer tous les services en dev
pnpm build              # Build tous les packages
pnpm lint               # Linter tous les packages
pnpm test               # Tests

# Base de données
pnpm db:migrate         # Appliquer les migrations
pnpm db:revision        # Créer une nouvelle migration
```

## 📊 Milestones

- ✅ **Milestone 0** : Scaffolding (monorepo, docker compose, README)
- ✅ **Milestone 1** : API foundation (FastAPI, DB, Alembic, auth)
- ✅ **Milestone 2** : Web foundation (Angular, routing, design system, auth UI)
- ✅ **Milestone 3** : Domain management (Admin API + UI pour CSV import)
- ✅ **Milestone 4** : Scraper service (Playwright TS, crawl + snapshots)
- ✅ **Milestone 5** : Worker processing (détection signaux, scoring, opportunities, Meili)
- ✅ **Milestone 6** : Dashboard opportunities (UI liste, filtres, recherche, détail)
- ✅ **Milestone 7** : Notifications (structure prête pour email digest, instant, Slack)
- ✅ **Milestone 8** : Billing + Trial (structure prête pour Stripe)
- ✅ **Milestone 9** : Hardening (docs déploiement, structure prête)

## 🔐 Sécurité

- Ne jamais commiter `.env`
- Changer tous les secrets en production
- Validation stricte des inputs (Pydantic)
- Rate limiting sur l'API
- CORS configuré

## 📝 Notes

- UI / emails en français
- Code (variables, fonctions, dossiers) en anglais
- Pas de scraping réseaux sociaux (LinkedIn, Twitter/X, Facebook, Instagram)
- Pas de collecte de données personnelles sur réseaux
- Design inspiré de earlysignals.io (premium minimal)

## 📄 License

Proprietary
