# Génère jusqu'à 10 000 domaines .fr depuis Tranco (export CSV sans crawl).
# Usage : depuis n'importe où
#   pwsh path\to\scripts\tranco_fr_10k.ps1
# Options supplémentaires passées au CLI, ex. :
#   pwsh .\scripts\tranco_fr_10k.ps1 --tranco-refresh --out .\data\ma_liste.csv

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m seed_builder_prospects.cli --preset tranco-fr-10k @args
