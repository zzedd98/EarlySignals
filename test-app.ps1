# Script de test rapide pour Early Signals
# Usage: .\test-app.ps1

Write-Host "🚀 Test de l'application Early Signals" -ForegroundColor Green
Write-Host ""

# 1. Vérifier Docker
Write-Host "1. Vérification de Docker..." -ForegroundColor Yellow
try {
    docker --version | Out-Null
    Write-Host "   ✓ Docker installé" -ForegroundColor Green
} catch {
    Write-Host "   ✗ Docker n'est pas installé ou Docker Desktop n'est pas démarré" -ForegroundColor Red
    Write-Host "   Veuillez démarrer Docker Desktop et réessayer" -ForegroundColor Yellow
    exit 1
}

# 2. Vérifier que l'infrastructure est démarrée
Write-Host "2. Vérification de l'infrastructure..." -ForegroundColor Yellow
$containers = docker compose ps --format json | ConvertFrom-Json
if ($containers.Count -eq 0) {
    Write-Host "   ⚠ Infrastructure non démarrée. Démarrage..." -ForegroundColor Yellow
    docker compose up -d
    Start-Sleep -Seconds 5
}

# 3. Vérifier les services
Write-Host "3. Vérification des services..." -ForegroundColor Yellow

# PostgreSQL
try {
    $pgTest = docker compose exec -T postgres psql -U earlysignals -d earlysignals -c "SELECT 1;" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✓ PostgreSQL fonctionne" -ForegroundColor Green
    } else {
        Write-Host "   ✗ PostgreSQL ne répond pas" -ForegroundColor Red
    }
} catch {
    Write-Host "   ⚠ PostgreSQL non accessible (normal si pas encore initialisé)" -ForegroundColor Yellow
}

# Redis
try {
    $redisTest = docker compose exec -T redis redis-cli ping 2>&1
    if ($redisTest -match "PONG") {
        Write-Host "   ✓ Redis fonctionne" -ForegroundColor Green
    } else {
        Write-Host "   ✗ Redis ne répond pas" -ForegroundColor Red
    }
} catch {
    Write-Host "   ✗ Redis non accessible" -ForegroundColor Red
}

# Meilisearch
try {
    $meiliTest = Invoke-WebRequest -Uri "http://localhost:7700/health" -UseBasicParsing -TimeoutSec 2
    if ($meiliTest.StatusCode -eq 200) {
        Write-Host "   ✓ Meilisearch fonctionne" -ForegroundColor Green
    }
} catch {
    Write-Host "   ✗ Meilisearch non accessible" -ForegroundColor Red
}

# MailHog
try {
    $mailhogTest = Invoke-WebRequest -Uri "http://localhost:8025" -UseBasicParsing -TimeoutSec 2
    if ($mailhogTest.StatusCode -eq 200) {
        Write-Host "   ✓ MailHog fonctionne" -ForegroundColor Green
    }
} catch {
    Write-Host "   ✗ MailHog non accessible" -ForegroundColor Red
}

# 4. Vérifier l'API
Write-Host "4. Vérification de l'API..." -ForegroundColor Yellow
try {
    $apiHealth = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2
    if ($apiHealth.StatusCode -eq 200) {
        Write-Host "   ✓ API fonctionne" -ForegroundColor Green
        Write-Host "   📖 Documentation: http://localhost:8000/docs" -ForegroundColor Cyan
    }
} catch {
    Write-Host "   ⚠ API non démarrée" -ForegroundColor Yellow
    Write-Host "   Pour démarrer: cd apps/api && uvicorn main:app --reload" -ForegroundColor Yellow
}

# 5. Vérifier l'application web
Write-Host "5. Vérification de l'application web..." -ForegroundColor Yellow
try {
    $webTest = Invoke-WebRequest -Uri "http://localhost:4200" -UseBasicParsing -TimeoutSec 2
    if ($webTest.StatusCode -eq 200) {
        Write-Host "   ✓ Application web fonctionne" -ForegroundColor Green
    }
} catch {
    Write-Host "   ⚠ Application web non démarrée" -ForegroundColor Yellow
    Write-Host "   Pour démarrer: cd apps/web && pnpm start" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✅ Vérifications terminées!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Prochaines étapes:" -ForegroundColor Cyan
Write-Host "   1. Démarrer l'API: cd apps/api && uvicorn main:app --reload" -ForegroundColor White
Write-Host "   2. Démarrer l'app web: cd apps/web && pnpm start" -ForegroundColor White
Write-Host "   3. Ouvrir http://localhost:4200 dans votre navigateur" -ForegroundColor White
Write-Host "   4. Consulter TEST_GUIDE.md pour les tests détaillés" -ForegroundColor White
