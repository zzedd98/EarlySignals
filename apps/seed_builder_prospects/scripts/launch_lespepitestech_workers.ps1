# Lance 10 workers Les Pepites Tech (1 terminal / worker, proxy Lightning fixe).
# Usage (depuis apps/seed_builder_prospects) :
#   pwsh ./scripts/launch_lespepitestech_workers.ps1
#   pwsh ./scripts/launch_lespepitestech_workers.ps1 -Workers 10 -Delay 0.1
#
# Apres la fin de tous les workers :
#   python scripts/scrape_lespepitestech_domains.py --merge

param(
    [int]$Workers = 10,
    [string]$ProxiesFile = "./data/proxies.lightning.txt",
    [string]$WorkerDir = "./data/lespepitestech_workers",
    [double]$Delay = 0.15,
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path $ProxiesFile)) {
    Write-Warning "Fichier proxy manquant: $ProxiesFile — crawl en IP directe"
}

$resumeArg = if ($Resume) { "--resume" } else { "--no-resume" }

python scripts/scrape_lespepitestech_domains.py `
  --launch-terminals `
  --worker-count $Workers `
  --proxies-file $ProxiesFile `
  --worker-dir $WorkerDir `
  --delay $Delay `
  $resumeArg
