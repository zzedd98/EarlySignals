# Lance N terminaux scraper ou workers signaux.
# Usage : .\launch.ps1 scraper 30
#         .\launch.ps1 scraper 30 -Cache
#         .\launch.ps1 worker 10

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('scraper', 'worker')]
    [string]$Type,

    [Parameter(Position = 1)]
    [int]$Count = 10,

    [switch]$Cache
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

if ($Count -lt 1) {
    Write-Error "Le nombre de terminaux doit être >= 1"
}

$args = @($Type, $Count)
if ($Cache) {
    $args += '--cache'
}

node (Join-Path $Root "scripts\launch.mjs") @args
exit $LASTEXITCODE
