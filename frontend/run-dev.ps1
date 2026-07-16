$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .\node_modules)) { npm install }
Write-Host "Nuxt: http://127.0.0.1:3008" -ForegroundColor Green
npm run dev
