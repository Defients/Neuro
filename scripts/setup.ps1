param([string]$Python = '')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (-not $Python) {
        $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $bundledPython) { $Python = $bundledPython }
        else {
            & py -3.12 -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or pass -Python with a Python 3.12+ executable path.' }
        }
    }
    if ($Python) { & $Python -m venv .venv }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
& npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
Write-Host 'Ready. Start with: .\scripts\start.ps1'
