# Score un CSV Tranco/domaines via proxies Lightning (fichier) — 1 terminal Windows par worker.
# Prérequis :
#   1) Copier data/proxies.lightning.example.txt -> data/proxies.lightning.txt
#   2) Renseigner le vrai mot de passe dans proxies.lightning.txt
#
# Usage (depuis apps/seed_builder_prospects) :
#   pwsh ./scripts/score_tranco_proxies_terminals.ps1
#   pwsh ./scripts/score_tranco_proxies_terminals.ps1 -InputDomains ./data/tranco_fr_1k_prefilter/keep.csv

param(
    [string]$InputDomains = "./data/tranco_fr_10k.csv",
    [string]$ProxiesFile = "./data/proxies.lightning.txt",
    [int]$Workers = 10,
    [string]$Out = "./data/seed_prospects_fr.csv"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path $ProxiesFile)) {
    Write-Error "Fichier proxy manquant: $ProxiesFile (copiez proxies.lightning.example.txt)"
}

python -m seed_builder_prospects.cli `
  --sources file_list `
  --input-domains $InputDomains `
  --proxies-file $ProxiesFile `
  --score-launch-terminals `
  --score-workers-parallel $Workers `
  --max-results 2500 `
  --max-links 2500 `
  --max-pages 5 `
  --rate-limit 30 `
  --segment-min-score-recruitment 25 `
  --segment-min-score-b2b-seller 65 `
  --segment-min-score-multinationale 55 `
  --out $Out `
  @args
