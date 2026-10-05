<#
.SYNOPSIS
    Starts LandslideGuard AI locally (FastAPI backend + Vite frontend).

.DESCRIPTION
    Launches the backend on port 8000 and the Vite dev server on 5173, waits for
    the backend to report healthy, then prints the URLs to open. Both processes
    are killed when this script exits or Ctrl+C is pressed.

    The backend port must match the Vite proxy target (default
    http://127.0.0.1:8000). Override with -BackendPort / -VitePort.

.EXAMPLE
    .\run.ps1
    .\run.ps1 -BackendPort 8010 -VitePort 5180
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$VitePort    = 5173
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $root 'backend\.venv\Scripts\python.exe'

Write-Host ''
Write-Host 'LandslideGuard AI' -ForegroundColor Cyan
Write-Host '=================' -ForegroundColor Cyan

# --- Preflight -------------------------------------------------------------
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "ERROR: backend virtualenv not found at $venvPython" -ForegroundColor Red
    Write-Host 'Create it first:' -ForegroundColor Yellow
    Write-Host '  python -m venv backend\.venv' -ForegroundColor Yellow
    Write-Host '  backend\.venv\Scripts\pip install -r backend\requirements.txt' -ForegroundColor Yellow
    exit 1
}

$frontendDir = Join-Path $root 'frontend'
if (-not (Test-Path -LiteralPath (Join-Path $frontendDir 'node_modules'))) {
    Write-Host 'ERROR: frontend/node_modules is missing.' -ForegroundColor Red
    Write-Host 'Run:  cd frontend; npm install' -ForegroundColor Yellow
    exit 1
}

# Reuse the port for the Vite proxy so a custom backend port keeps working.
$env:VITE_PROXY_TARGET = "http://127.0.0.1:$BackendPort"

$backend = $null
$frontend = $null

try {
    # --- Backend ----------------------------------------------------------
    Write-Host "Starting backend on port $BackendPort ..." -ForegroundColor Cyan
    $backend = Start-Process -PassThru -NoNewWindow -FilePath $venvPython `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
        -WorkingDirectory (Join-Path $root 'backend')

    $healthUrl = "http://127.0.0.1:$BackendPort/api/health"
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
            $ready = $true
            break
        } catch {
            if ($backend.HasExited) { break }
        }
    }

    if (-not $ready) {
        Write-Host ''
        Write-Host 'ERROR: backend did not become healthy in 60s.' -ForegroundColor Red
        Write-Host 'Check the backend output above for the failure reason.' -ForegroundColor Red
        exit 1
    }

    Write-Host ("  backend healthy  : {0}  (db={1}, model={2}, mode={3})" -f `
        $health.status, $health.database, $health.model, $health.data_mode) -ForegroundColor Green

    # --- Frontend ---------------------------------------------------------
    Write-Host "Starting frontend on port $VitePort ..." -ForegroundColor Cyan
    $frontend = Start-Process -PassThru -NoNewWindow -FilePath 'npm.cmd' `
        -ArgumentList @('run', 'dev', '--', '--port', "$VitePort", '--strictPort') `
        -WorkingDirectory $frontendDir

    # --- Summary ----------------------------------------------------------
    Write-Host ''
    Write-Host '---------------- Ready ----------------' -ForegroundColor Green
    Write-Host ("  Dashboard : http://localhost:{0}/dashboard" -f $VitePort) -ForegroundColor Green
    Write-Host ("  API docs  : http://127.0.0.1:{0}/docs" -f $BackendPort) -ForegroundColor Green
    Write-Host ("  Health    : {0}" -f $healthUrl) -ForegroundColor Green
    Write-Host ''
    Write-Host '  Demo login: admin@landslideguard.ai / admin123' -ForegroundColor DarkGray
    Write-Host '  Press Ctrl+C to stop both processes.' -ForegroundColor DarkGray
    Write-Host ''

    # Park until interrupted so the child processes keep running.
    while (-not $backend.HasExited -and -not $frontend.HasExited) {
        Start-Sleep -Seconds 2
    }
}
finally {
    Write-Host ''
    Write-Host 'Shutting down ...' -ForegroundColor Cyan
    foreach ($proc in @($frontend, $backend)) {
        if ($null -ne $proc -and -not $proc.HasExited) {
            # Kill the whole process tree (npm -> node, uvicorn -> reloader).
            try { taskkill /PID $proc.Id /T /F 2>&1 | Out-Null } catch { }
        }
    }
}