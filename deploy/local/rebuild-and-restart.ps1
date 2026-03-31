# Quick rebuild and restart for development (Windows / PowerShell)
# Usage: .\rebuild-and-restart.ps1 [backend|worker|frontend|all]
param([string]$Component = "all")

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Rebuild-Component {
    param([string]$Comp)
    Write-Host "Rebuilding $Comp..." -ForegroundColor Blue
    docker compose build $Comp
    docker compose up -d $Comp
    Write-Host "$Comp rebuilt and restarted" -ForegroundColor Green
}

if ($Component -eq "all") {
    # Rotate App ID
    $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(16)
    $newAppId = [System.BitConverter]::ToString($bytes).Replace("-", "").ToLower()
    Write-Host "Rotating App ID: $newAppId" -ForegroundColor Yellow
    if (Test-Path .env) {
        (Get-Content .env) -replace '^SECURITY_APP_ID=.*', "SECURITY_APP_ID=$newAppId" |
            Set-Content .env
    }

    docker compose build

    # Start postgres first so migrations can run against it
    docker compose up -d postgres
    Write-Host "Waiting for postgres to be ready..." -ForegroundColor Blue
    do {
        Start-Sleep -Seconds 1
        docker compose exec -T postgres pg_isready -U kitabim -d kitabim-ai 2>$null | Out-Null
    } until ($LASTEXITCODE -eq 0)
    Write-Host "Postgres ready" -ForegroundColor Green

    # Apply all migrations (IF NOT EXISTS guards make these idempotent)
    Write-Host "Applying migrations..." -ForegroundColor Blue
    Get-ChildItem "packages\backend-core\migrations\*.sql" | Sort-Object Name | ForEach-Object {
        Write-Host "  -> $($_.Name)"
        Get-Content $_.FullName | docker compose exec -T postgres psql -U kitabim -d kitabim-ai
    }

    docker compose up -d
} elseif ($Component -in @("backend", "worker", "frontend")) {
    Rebuild-Component $Component
} else {
    Write-Host "Unknown component: $Component" -ForegroundColor Red
    Write-Host "Usage: .\rebuild-and-restart.ps1 [backend|worker|frontend|all]"
    exit 1
}

Write-Host ""
Write-Host "Service status:" -ForegroundColor Blue
docker compose ps
