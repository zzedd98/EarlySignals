# Score jusqu'à 1000 domaines depuis tranco_fr_1k.csv sur 4 proxies locaux (ports 101-104), ~250 domaines chacun.
# Prérequis : forward HTTP des clés 4G vers 127.0.0.1:101 .. :104
# Usage (depuis apps/seed_builder_prospects) :
#   pwsh ./scripts/score_tranco_1k_4g.ps1
# Options supplémentaires : --debug-jsonl ./data/score.debug.jsonl --min-score 50

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m seed_builder_prospects.cli `
  --sources file_list `
  --input-domains ./data/tranco_fr_1k.csv `
  --score-workers-map "101:0,102:250,103:500,104:750" `
  --max-links 1000 `
  --max-results 2000 `
  --out ./data/tranco_fr_1k_scored.csv `
  @args
