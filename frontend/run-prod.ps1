# Production frontend (после npm run build)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.output\server\index.mjs")) {
    Write-Host "Сначала выполните: npm run build" -ForegroundColor Red
    exit 1
}

$env:NITRO_PORT = "3008"
$env:NITRO_HOST = "0.0.0.0"
Write-Host "Medical frontend: http://127.0.0.1:3008/medical/" -ForegroundColor Green
node .\.output\server\index.mjs
