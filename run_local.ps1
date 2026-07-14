# Starts AI-SoulMatch bound to the local network so other devices on the
# same Wi-Fi/LAN can reach it (not just this machine). Run from the project
# root, or double-click via a shortcut with this as the target.

$ErrorActionPreference = "Stop"

# $PSScriptRoot is empty in a few invocation contexts (e.g. some conda/venv
# -wrapped prompts calling the script by bare name instead of via .\ or a
# full path) — fall back to $PSCommandPath's directory so Join-Path below
# never silently builds a null/empty path (which Start-Process then reports
# as a confusing "FilePath is null or empty" with no mention of why).
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $PSCommandPath }
if (-not $scriptDir) {
    Write-Host "Could not determine this script's own directory — run it as '.\run_local.ps1' from the project root instead of by bare name." -ForegroundColor Red
    exit 1
}
Set-Location $scriptDir

if (-not (Test-Path ".env")) {
    Write-Host "No .env found — copy .env.example to .env and configure it first." -ForegroundColor Yellow
    exit 1
}

$venvPython = Join-Path $scriptDir ".venv\Scripts\streamlit.exe"
$venvPythonExe = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment not found at .venv — run: py -3.12 -m venv .venv; .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $venvPythonExe)) {
    Write-Host "python.exe not found at $venvPythonExe — the .venv looks incomplete. Recreate it: py -3.12 -m venv .venv; .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

$lanIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.InterfaceAlias -notmatch 'Loopback|WSL|vEthernet' -and $_.IPAddress -notlike '169.254*'
} | Select-Object -First 1).IPAddress

# V3-3: payment-gateway webhooks arrive on a separate stdlib HTTP sidecar —
# Streamlit itself can't receive arbitrary POST routes. See webhook_server.py.
# -NoNewWindow (not -WindowStyle Hidden): hiding a window requires an
# interactive window station, which isn't always available when this script
# itself is launched non-interactively/detached (e.g. as a background job) —
# under that condition -WindowStyle Hidden makes Start-Process fail with a
# misleading "FilePath is null or empty" error. -NoNewWindow has no such
# dependency and still keeps the sidecar out of the way (no console popup).
Write-Host "Starting webhook sidecar (payments)..." -ForegroundColor Green
$webhookProcess = Start-Process -FilePath $venvPythonExe -ArgumentList "webhook_server.py" -PassThru -NoNewWindow
Write-Host "  Webhooks: http://localhost:8502/webhooks/{razorpay,stripe}  (pid $($webhookProcess.Id))"

Write-Host "Starting AI-SoulMatch..." -ForegroundColor Green
Write-Host "  Local:   http://localhost:8501"
if ($lanIP) { Write-Host "  Network: http://${lanIP}:8501  (other devices on this Wi-Fi/LAN)" }
Write-Host ""

try {
    & $venvPython run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true --browser.gatherUsageStats false
} finally {
    Write-Host "Stopping webhook sidecar (pid $($webhookProcess.Id))..." -ForegroundColor Yellow
    Stop-Process -Id $webhookProcess.Id -Force -ErrorAction SilentlyContinue
}
