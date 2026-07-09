# Starts AI-SoulMatch bound to the local network so other devices on the
# same Wi-Fi/LAN can reach it (not just this machine). Run from the project
# root, or double-click via a shortcut with this as the target.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "No .env found — copy .env.example to .env and configure it first." -ForegroundColor Yellow
    exit 1
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\streamlit.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment not found at .venv — run: py -3.12 -m venv .venv; .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

$lanIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.InterfaceAlias -notmatch 'Loopback|WSL|vEthernet' -and $_.IPAddress -notlike '169.254*'
} | Select-Object -First 1).IPAddress

Write-Host "Starting AI-SoulMatch..." -ForegroundColor Green
Write-Host "  Local:   http://localhost:8501"
if ($lanIP) { Write-Host "  Network: http://${lanIP}:8501  (other devices on this Wi-Fi/LAN)" }
Write-Host ""

& $venvPython run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true --browser.gatherUsageStats false
