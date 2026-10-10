# Lance ceil(active_domains / batch_size) terminaux scraper (400 domaines chacun par défaut).
# Prérequis : API sur http://localhost:8000 + SCRAPER_API_* dans .env racine
#
# Usage (depuis apps/scraper) :
#   pwsh ./scripts/launch_scraper_terminals.ps1
#   pwsh ./scripts/launch_scraper_terminals.ps1 -BatchSize 400

param(
    [int]$BatchSize = 400
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "Orchestrateur scraper — batch=$BatchSize" -ForegroundColor Cyan
npx tsx src/index.ts --launch-terminals --batch-size $BatchSize
