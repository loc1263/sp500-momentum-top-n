<#
.SYNOPSIS
  Levanta el backend (Python, API en /api/report) y el frontend (Svelte + Vite) a la vez.
.EXAMPLE
  .\start.ps1
  .\start.ps1 -BackendPort 9000 -FrontendPort 3000
.NOTES
  Ctrl+C detiene los dos servidores.
#>
param(
    [string]$BackendHost = '127.0.0.1',
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backendDir = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'

foreach ($cmd in 'python', 'npm') {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "No se encontró '$cmd' en el PATH."
    }
}

if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Host 'Instalando dependencias del frontend...' -ForegroundColor Cyan
    Push-Location $frontendDir
    try { npm install; if ($LASTEXITCODE) { throw 'npm install falló' } } finally { Pop-Location }
}

# El frontend redirige /api al backend
$env:BACKEND_URL = "http://${BackendHost}:$BackendPort"
$env:FRONTEND_PORT = "$FrontendPort"

$procs = @()
try {
    Write-Host "Backend  -> http://${BackendHost}:$BackendPort/api/report" -ForegroundColor Green
    $procs += Start-Process python -ArgumentList 'server.py', '--host', $BackendHost, '--port', $BackendPort `
        -WorkingDirectory $backendDir -NoNewWindow -PassThru

    Write-Host "Frontend -> http://localhost:$FrontendPort" -ForegroundColor Green
    $procs += Start-Process npm.cmd -ArgumentList 'run', 'dev' `
        -WorkingDirectory $frontendDir -NoNewWindow -PassThru

    Write-Host 'Ctrl+C para detener ambos.' -ForegroundColor DarkGray
    # Si uno de los dos termina, se corta todo
    while (-not ($procs | Where-Object { $_.HasExited })) { Start-Sleep -Seconds 1 }
    Write-Warning 'Uno de los servidores terminó; se detiene el otro.'
}
finally {
    foreach ($p in $procs) {
        if (-not $p.HasExited) { & taskkill /PID $p.Id /T /F | Out-Null }
    }
}
