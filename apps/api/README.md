# Early Signals API

FastAPI backend pour Early Signals.

## Setup

### Prérequis

- Python >= 3.11
- PostgreSQL (via Docker Compose)
- Redis (via Docker Compose)

### Installation

1. **Créer un environnement virtuel**

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

2. **Installer les dépendances**

```bash
pip install -r requirements.txt
```

3. **Configurer l'environnement**

Créer un fichier `.env` à la racine de `apps/api/` :

```bash
DATABASE_URL=postgresql://earlysignals:earlysignals_dev@localhost:5432/earlysignals
REDIS_URL=redis://localhost:6379/0
MEILI_URL=http://localhost:7700
MEILI_MASTER_KEY=masterKey_dev_change_in_prod
API_SECRET_KEY=change_this_secret_key_in_production
JWT_SECRET_KEY=change_this_jwt_secret_in_production
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
CORS_ORIGINS=http://localhost:4200,http://localhost:3000
```

4. **Initialiser Alembic et créer la première migration**

```bash
# Depuis la racine du monorepo
cd apps/api
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

5. **Démarrer l'API**

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

L'API sera disponible sur `http://localhost:8000`

## Endpoints

### Health Checks

- `GET /health` - Health check
- `GET /ready` - Readiness check (vérifie la connexion DB)

### Authentication

- `POST /api/v1/auth/register` - Créer un compte
- `POST /api/v1/auth/login` - Se connecter
- `GET /api/v1/auth/me` - Obtenir l'utilisateur actuel (requiert auth)

### Organizations

- `POST /api/v1/organizations` - Créer une organisation
- `GET /api/v1/organizations/{org_id}` - Obtenir une organisation

## Documentation

Une fois l'API démarrée, la documentation interactive est disponible :

- Swagger UI : `http://localhost:8000/docs`
- ReDoc : `http://localhost:8000/redoc`

## Migrations

```bash
# Créer une nouvelle migration
alembic revision --autogenerate -m "Description"

# Appliquer les migrations
alembic upgrade head

# Revenir en arrière
alembic downgrade -1
```

## Tests

```bash
pytest
```

## Structure

```
apps/api/
├── app/
│   ├── api/           # Routes API
│   ├── core/          # Configuration, sécurité, DB
│   ├── models/        # Modèles SQLAlchemy
│   └── schemas/       # Schémas Pydantic
├── alembic/           # Migrations
├── main.py            # Point d'entrée
└── requirements.txt   # Dépendances
```
