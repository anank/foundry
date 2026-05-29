# deploy.ps1 — Deploy Foundry to VPS from Windows
# Usage: .\deploy.ps1
# Requirements: ssh key added, `ssh vps` works (configure in ~/.ssh/config)

$ErrorActionPreference = "Stop"

$VPS_SSH   = "root@vps"
$REMOTE    = "/root/projects/foundry"
$SERVICE   = "foundry"
$PORT      = 8000

Write-Host "==> Deploying Foundry to ${VPS_SSH}:${REMOTE}" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Sync code via rsync (requires rsync in WSL or Git Bash)
#    Falls back to scp if rsync not available
# ---------------------------------------------------------------------------
Write-Host "==> Syncing code..." -ForegroundColor Cyan

$rsyncAvailable = $null
try { $rsyncAvailable = Get-Command rsync -ErrorAction Stop } catch {}

if ($rsyncAvailable) {
    rsync -az --delete `
        --exclude='.git' `
        --exclude='.env' `
        --exclude='__pycache__' `
        --exclude='*.pyc' `
        --exclude='.pytest_cache' `
        --exclude='*.egg-info' `
        --exclude='.venv' `
        --exclude='dist' `
        --exclude='build' `
        ./ "${VPS_SSH}:${REMOTE}/"
} else {
    Write-Host "  rsync not found, using scp..." -ForegroundColor Yellow
    # Create remote dir first
    ssh $VPS_SSH "mkdir -p ${REMOTE}"
    # Copy everything except .env and .venv
    $items = Get-ChildItem -Path . -Exclude '.git','.env','.venv','__pycache__','*.egg-info','dist','build'
    foreach ($item in $items) {
        scp -r $item.FullName "${VPS_SSH}:${REMOTE}/"
    }
}

Write-Host "==> Code synced." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. Remote setup via ssh heredoc
# ---------------------------------------------------------------------------
Write-Host "==> Running remote setup..." -ForegroundColor Cyan

$remoteScript = @"
set -euo pipefail
cd ${REMOTE}

# Python check
if ! python3 --version 2>&1 | grep -qE '3\.(11|12|13)'; then
  echo 'Installing Python 3.11...'
  apt-get update -qq && apt-get install -y -qq python3.11 python3.11-venv
fi

# Virtualenv
if [ ! -d '.venv' ]; then
  echo 'Creating virtualenv...'
  python3 -m venv .venv
fi

# Dependencies
echo 'Installing dependencies...'
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e '.[dev]'

# .env
if [ ! -f '.env' ]; then
  cp .env.example .env
  echo 'Created .env — fill in values at ${REMOTE}/.env'
fi

# DB dir
mkdir -p /root/.foundry

# Systemd service
cat > /etc/systemd/system/${SERVICE}.service <<SERVICE
[Unit]
Description=Foundry Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${REMOTE}
EnvironmentFile=${REMOTE}/.env
ExecStart=${REMOTE}/.venv/bin/python -m uvicorn foundry.dashboard.app:app --host 0.0.0.0 --port ${PORT}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable ${SERVICE}
systemctl restart ${SERVICE}
systemctl is-active ${SERVICE} && echo '${SERVICE} is running on port ${PORT}' || echo 'WARNING: service failed'
"@

ssh $VPS_SSH $remoteScript

Write-Host ""
Write-Host "==> Deploy complete." -ForegroundColor Green
Write-Host "    Dashboard : http://vps:${PORT}" -ForegroundColor White
Write-Host ""
Write-Host "    Next steps on VPS:" -ForegroundColor Yellow
Write-Host "      1. ssh ${VPS_SSH} nano ${REMOTE}/.env"
Write-Host "         Set: FOUNDRY_DEVICE_ID, GITHUB_TOKEN, ANTHROPIC_API_KEY"
Write-Host "      2. ssh ${VPS_SSH} systemctl restart ${SERVICE}"
Write-Host "      3. ssh ${VPS_SSH} 'cd ${REMOTE} && .venv/bin/python scripts/import_vault_projects.py'"
Write-Host ""
Write-Host "    Useful commands:" -ForegroundColor Yellow
Write-Host "      ssh ${VPS_SSH} journalctl -u ${SERVICE} -f    # live logs"
Write-Host "      ssh ${VPS_SSH} systemctl restart ${SERVICE}   # restart"
Write-Host "      ssh ${VPS_SSH} systemctl status ${SERVICE}    # status"
