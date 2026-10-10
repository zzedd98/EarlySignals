# Sources de découverte — Seed Builder Prospects

Le CLI peut combiner **`google`**, **`tranco`** et **`file_list`**. Chaque source produit des candidats (`DiscoveryResult`) ; fusion, dédup, puis pipeline crawl + scoring (sauf `--tranco-list-only`).

---

## `google`

Recherches Google via **Playwright** (HTML), avec packs de requêtes définis dans `config.py` (`--query-pack`).

**Options utiles** : `--query-pack`, `--delay-min` / `--delay-max`, `--proxy` / `--proxy-port`, `GOOGLE_PROXY`, `--capsolver-api-key` / `CAPSOLVER_API_KEY`, orchestration `--google-workers-map`, etc.

---

## `tranco`

Liste **Tranco top 1M** : téléchargement du ZIP officiel dans `--cache-dir` (ou CSV local `--tranco-csv`).

**Options** : `--tranco-csv`, `--tranco-subdomains`, `--tranco-tld` (ex. `.fr`), `--tranco-refresh`, `--tranco-list-only` (export sans crawl).

**Preset** : `--preset tranco-fr-10k` → 10 000 domaines `.fr` en CSV rapide (`./data/tranco_fr_10k.csv` par défaut). Voir `scripts/tranco_fr_10k.ps1`.

Voir aussi `seed_builder_prospects/discovery/tranco.py`.

---

## `file_list`

Fichier **CSV** (colonne `domain`) ou **TXT** (un domaine par ligne). Sert à **rescoring** d’une liste existante (ex. export Tranco).

**Scoring multi-proxy** : `--score-workers-map "101:0,102:250,..."` avec `--sources file_list` uniquement. Voir README et `scripts/score_tranco_1k_4g.ps1`.
