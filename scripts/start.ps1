$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Run .\scripts\setup.ps1 first.' }
if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host 'Port 8080 is already serving an application. Open http://localhost:8080, or stop that process before starting another instance.'
    exit 0
}
if (-not (Test-Path -LiteralPath 'dist\index.html')) {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
Write-Host 'NeuralSignalStudio: http://localhost:8080 — press Ctrl+C to stop.'
& .\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8080 --no-access-log
