param([switch]$Production, [switch]$Dev)

# La PWA compilada es la experiencia predeterminada. -Dev habilita Vite.
if (-not $Dev) { $Production = $true }

# FORMA — arranque local. NO necesita Docker.
# PostgreSQL es opcional: si Docker no está, usa SQLite automáticamente.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$backendPy = Join-Path $root "backend\.venv\Scripts\python.exe"
$uvicorn = Join-Path $root "backend\.venv\Scripts\uvicorn.exe"
$logDir = Join-Path $root "backend\data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path $uvicorn)) {
    Write-Host "Creando entorno Python..."
    Push-Location (Join-Path $root "backend")
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    Pop-Location
}

if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    Write-Host "Instalando frontend..."
    Push-Location (Join-Path $root "frontend")
    npm install
    Pop-Location
}

function Test-Port([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $c
}

if (Test-Port 8000) {
    Write-Host "API ya estaba en http://127.0.0.1:8000"
} else {
    Start-Process -FilePath $backendPy -WindowStyle Hidden -ArgumentList @(
        "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"
    ) -WorkingDirectory (Join-Path $root "backend") `
        -RedirectStandardOutput (Join-Path $logDir "server-output.log") `
        -RedirectStandardError (Join-Path $logDir "server-error.log")
    Write-Host "Arrancando API en http://127.0.0.1:8000"
}

if (Test-Port 5173) {
    Write-Host "UI ya estaba en http://localhost:5173"
} else {
    if ($Production) {
        Push-Location (Join-Path $root "frontend")
        try {
            npm run build
            if ($LASTEXITCODE -ne 0) { throw "No se pudo compilar la PWA" }
        } finally { Pop-Location }
    }
    $viteArguments = if ($Production) { @("preview", "--host", "127.0.0.1", "--port", "5173", "--strictPort") } else { @("--host", "127.0.0.1", "--port", "5173", "--strictPort") }
    $nodeExe = (Get-Command node -ErrorAction Stop).Source
    $viteEntry = Join-Path $root "frontend\node_modules\vite\bin\vite.js"
    Start-Process -FilePath $nodeExe -WindowStyle Hidden -ArgumentList (@(('"' + $viteEntry + '"')) + $viteArguments) -WorkingDirectory (Join-Path $root "frontend") `
        -RedirectStandardOutput (Join-Path $logDir "frontend-output.log") `
        -RedirectStandardError (Join-Path $logDir "frontend-error.log")
    Write-Host "Arrancando UI en http://localhost:5173"
}

function Test-LocalHttp([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

$startupDeadline = (Get-Date).AddSeconds(45)
do {
    $backendReady = Test-LocalHttp "http://127.0.0.1:8000/api/v1/health"
    $frontendReady = Test-LocalHttp "http://127.0.0.1:5173/"
    if ($backendReady -and $frontendReady) { break }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $startupDeadline)
if (-not $backendReady -or -not $frontendReady) {
    throw "No respondieron ambos servicios. Backend: $backendReady; frontend: $frontendReady. Revisa los registros en $logDir"
}

Write-Host ""
Write-Host "Proyecto encendido: http://127.0.0.1:5173/"
Write-Host "Docs:  http://127.0.0.1:8000/api/docs"
Write-Host "Docker es opcional. Este script funciona sin el."
Write-Host "Puedes cerrar esta terminal; ambos servicios quedan en segundo plano."
