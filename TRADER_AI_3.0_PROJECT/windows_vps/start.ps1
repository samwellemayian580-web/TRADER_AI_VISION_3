$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not $env:MT5_BRIDGE_TOKEN) {
    throw "Set MT5_BRIDGE_TOKEN in this PowerShell session first."
}

if (-not (Test-Path $Python)) {
    throw "VPS environment missing. Run setup.ps1 first."
}

Set-Location $ProjectRoot

Write-Host "Starting TRADER AI MT5 bridge in READ-ONLY mode..."
& $Python -m broker.mt5_vps_server
