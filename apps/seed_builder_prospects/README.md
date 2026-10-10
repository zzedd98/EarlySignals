# Seed Builder Prospects — Early Signals

CLI pour construire une **seed list** de domaines : découverte via **Google** (Playwright) et/ou **Tranco** (top 1M), puis crawl HTTP, scoring et export CSV.

**Sources** (`--sources`, une ou plusieurs) :

- **`google`** : requêtes avancées, packs dans `config.py`
- **`tranco`** : classement Tranco (ZIP mis en cache ou fichier CSV local)
- **`file_list`** : CSV/TXT de domaines (`--input-domains`), pour rescoring sans Google

Détail : **[docs/SOURCES.md](docs/SOURCES.md)**.

## Prérequis

- Python 3.10+
- `playwright install chromium` après `pip install -r requirements.txt`
- Source **google** : pas de clé API Google ; optionnel CapSolver pour captchas (`CAPSOLVER_API_KEY`)

## Installation

```bash
cd apps/seed_builder_prospects
pip install -r requirements.txt
playwright install chromium
```

## Une commande : 10 000 domaines `.fr` (Tranco)

Sans crawl HTTP (instantané une fois le ZIP en cache) ; CSV compatible `import_seed_to_api.py`.

```bash
cd apps/seed_builder_prospects
python -m seed_builder_prospects.cli --preset tranco-fr-10k
```

Sortie par défaut : `./data/tranco_fr_10k.csv`. Le top 1M Tranco ne contient qu’un **nombre limité** de `.fr` : si moins de 10 000, un avertissement s’affiche et le fichier contient tout ce qui a été trouvé.

Sous Windows, depuis le dossier du projet :

```powershell
pwsh apps/seed_builder_prospects/scripts/tranco_fr_10k.ps1
```

Options utiles : `--tranco-refresh` (retélécharger la liste), `--out chemin.csv`, `--cache-dir ...`.

### Scorer un CSV Tranco sur 4 proxies (4G → `127.0.0.1:101` … `:104`)

Découpage **250 + 250 + 250 + 250** domaines (indices `0–249`, `250–499`, …). Chaque worker envoie le **crawl HTTP** via `http://127.0.0.1:PORT`. Fusion finale : dédup par domaine, meilleur score conservé.

```bash
cd apps/seed_builder_prospects
python -m seed_builder_prospects.cli \
  --sources file_list \
  --input-domains ./data/tranco_fr_1k.csv \
  --score-workers-map "101:0,102:250,103:500,104:750" \
  --max-links 1000 \
  --max-results 2000 \
  --out ./data/tranco_fr_1k_scored.csv
```

Raccourci PowerShell : `pwsh ./scripts/score_tranco_1k_4g.ps1`

Les lignes du CSV final respectent `--min-score` (défaut 60) : seuls les domaines assez bien scorés sont exportés (comme pour Google). Le crawl utilise **httpx** avec le proxy indiqué (pas Playwright).

Équivalent explicite du preset :

`--sources tranco --tranco-tld .fr --max-links 10000 --max-results 10000 --tranco-list-only`

## Exemples

**Tranco seul** (`.fr`, cache sous `./.cache/seed_builder_prospects`) :

```bash
python -m seed_builder_prospects.cli \
  --sources tranco \
  --tranco-tld .fr \
  --max-links 200 \
  --max-results 50 \
  --min-score 60 \
  --out ./data/seed.csv
```

**Google seul** :

```bash
python -m seed_builder_prospects.cli \
  --sources google \
  --query-pack fr_prospects_growth_b2b \
  --max-links 50 \
  --max-results 20 \
  --out ./data/seed.csv
```

**Les deux** (fusion + dédup) :

```bash
python -m seed_builder_prospects.cli \
  --sources tranco,google \
  --tranco-tld .fr \
  --query-pack fr_prospects_growth_b2b \
  --max-links 300 \
  --out ./data/seed.csv
```

## Options principales

| Option | Description |
|--------|-------------|
| `--sources` | `google`, `tranco` (virgule) |
| `--provider` | [Rétrocompat] une seule : `google` ou `tranco` |
| `--query-pack` | Pack de requêtes pour **google** |
| `--tranco-csv` / `--tranco-tld` / `--tranco-subdomains` / `--tranco-refresh` | **tranco** |
| `--max-links` | Max de domaines à crawler |
| `--max-results` | Max de lignes valides dans le CSV |
| `--min-score` | Score minimal (0–100, défaut 60) |
| `--out` | CSV de sortie |
| `--cache-dir` | Cache HTML + Tranco |
| `--debug-jsonl` | Trace détaillée |
| `--delay-min` / `--delay-max` | Délais entre requêtes Google |
| `--headless` | Navigateur sans fenêtre (Google) |
| `--proxy` / `--proxy-port` | Proxy pour Google |

## Query packs

Définis dans `seed_builder_prospects/config.py` (`QUERY_PACK_*`, `get_full_queries`). Ex. : `fr_prospects_growth_b2b`, `fr_prospects_growth_b2b_recruitment`, etc.

## Scoring & sortie

Règles dans `config.py` (`SCORING_BONUS`, `SCORING_PENALTY`), filtres dans `signals/filters.py`. Colonnes CSV : `domain`, `brand_name`, `country`, `category`, `confidence_score`, `evidence`, etc.

## Tests

```bash
cd apps/seed_builder_prospects
python -m pytest tests/ -v
```

## Arborescence (aperçu)

```
seed_builder_prospects/
  cli.py, config.py, cache.py
  providers/     base, google_playwright, tranco
  discovery/     tranco (téléchargement liste)
  crawl/, signals/, output/
tests/
```
