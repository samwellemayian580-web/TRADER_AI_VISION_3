$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $PSScriptRoot ".venv"

Write-Host "Setting up TRADER AI VISION 3.0 Windows VPS..."

py -3.12 -m venv $Venv

if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    throw "Python 3.12 virtual environment could not be created."
}

& "$Venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Venv\Scripts\python.exe" -m pip install -r "$PSScriptRoot\requirements.txt"

Write-Host "Setup complete."
Write-Host "Make sure the MT5 desktop terminal is installed and logged into your HFM DEMO account."
