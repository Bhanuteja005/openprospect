# First-time setup on Windows. Run from the repo folder:
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#
#   1. checks Docker and uv
#   2. installs the Python workspace (uv sync)
#   3. creates .env (random passwords) and config\ from the examples
#   4. starts the services (first time downloads ~6 GB)
#   5. connects them (Listmonk API user + sending limits, Huginn scenario) and runs a health check
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Say($msg) { Write-Host $msg -ForegroundColor Cyan }
function Die($msg) { Write-Host $msg -ForegroundColor Red; exit 1 }

Say "1/5 Checking Docker and uv..."
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die "Docker Desktop is not installed: https://docs.docker.com/desktop/" }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Die "Docker Desktop is not running. Start it, wait for 'Engine running', then run this again." }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Die "uv is not installed: powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`""
}

Say "2/5 Installing OpenProspect (uv sync)..."
uv sync
if ($LASTEXITCODE -ne 0) { Die "uv sync failed" }

Say "3/5 Creating .env and config\ (existing files are kept)..."
uv run openprospect init

Say "4/5 Starting services (first time can take 10+ minutes)..."
uv run openprospect up

$port = "3740"
if (Test-Path .env) {
  $line = Select-String -Path .env -Pattern '^TWENTY_PORT=(.+)$' | Select-Object -First 1
  if ($line) { $port = $line.Matches[0].Groups[1].Value }
}
Say "   waiting for the CRM (http://localhost:$port) to finish its first start..."
for ($i = 0; $i -lt 60; $i++) {
  try { Invoke-WebRequest -UseBasicParsing "http://localhost:$port/healthz" -TimeoutSec 3 | Out-Null; break } catch { Start-Sleep 5 }
}

Say "5/5 Connecting the pieces (Listmonk API user, sending limits, Huginn scenario)..."
uv run openprospect setup
uv run openprospect doctor

Write-Host "`nDone. Next: edit config\settings.yaml, add your inbox + Twenty API key to .env" -ForegroundColor Green
Write-Host "and see docs\getting-started.md. Then:  uv run openprospect run" -ForegroundColor Green
