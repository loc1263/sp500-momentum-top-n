<#
.SYNOPSIS
  Levanta el frontend (Svelte + Vite). La página lee frontend/public/data/report.json, que dejan los scripts de
  Python (backend/run_pipeline.py); no necesita el backend en marcha.
.EXAMPLE
  .\start.ps1
  .\start.ps1 -FrontendPort 3000
.NOTES
  Ctrl+C detiene el servidor.
#>
param(
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$frontendDir = Join-Path $root 'frontend'

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "No se encontró 'npm' en el PATH."
}

if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Host 'Instalando dependencias del frontend...' -ForegroundColor Cyan
    Push-Location $frontendDir
    try { npm install; if ($LASTEXITCODE) { throw 'npm install falló' } } finally { Pop-Location }
}

if (-not (Test-Path (Join-Path $frontendDir 'public/data/report.json'))) {
    Write-Warning "Falta frontend/public/data/report.json. Ejecute 'python run_pipeline.py' en backend/ para generarlo."
}

$env:FRONTEND_PORT = "$FrontendPort"
Write-Host "Frontend -> http://localhost:$FrontendPort   (Ctrl+C para detener)" -ForegroundColor Green
Set-Location $frontendDir
npm.cmd run dev
