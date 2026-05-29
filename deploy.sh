#!/usr/bin/env bash
# deploy.sh — Deploy Foundry to VPS
# Usage: bash deploy.sh
# Requirements: ssh key already added, root@vps accessible

set -euo pipefail

VPS_HOST="vps"
VPS_USER="root"
VPS_SSH="${VPS_USER}@${VPS_HOST}"
REMOTE_DIR="/root/projects/foundry"
SERVICE_NAME="foundry"
PORT=8000

echo "==> Deploying Foundry to ${VPS_SSH}:${REMOTE_DIR}"

# ---------------------------------------------------------------------------
# 1. Sync code (exclude dev/runtime artifacts)
# ---------------------------------------------------------------------------
echo "==> Syncing code..."
rsync -az --delete \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='*.egg-info' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='dist' \
  --exclude='build' \
  --exclude='scripts/import_vault_projects.py' \
  ./ "${VPS_SSH}:${REMOTE_DIR}/"

echo "==> Code synced."

# ---------------------------------------------------------------------------
# 2. Remote setup: Python, venv, dependencies, systemd service
# ---------------------------------------------------------------------------
ssh "${VPS_SSH}" bash <<REMOTE
set -euo pipefail

cd "${REMOTE_DIR}"

# Ensure Python 3.11+
if ! python3 --version 2>&1 | grep -qE '3\.(11|12|13)'; then
  echo "Installing Python 3.11..."
  apt-get update -qq && apt-get install -y -qq python3.11 python3.11-venv python3.11-pip
fi

# Create venv if missing
if [ ! -d ".venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
fi

# Install/upgrade dependencies
echo "Installing dependencies..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[dev]"

# Create .env if missing (user fills in values)
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill in your values at ${REMOTE_DIR}/.env"
fi

# Create ~/.foundry dir for DB
mkdir -p /root/.foundry

# Write systemd service
cat > /etc/systemd/system/${SERVICE_NAME}.service <<SERVICE
[Unit]
Description=Foundry Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${REMOTE_DIR}
EnvironmentFile=${REMOTE_DIR}/.env
ExecStart=${REMOTE_DIR}/.venv/bin/python -m uvicorn foundry.dashboard.app:app --host 0.0.0.0 --port ${PORT}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}

echo "Service status:"
systemctl is-active ${SERVICE_NAME} && echo "${SERVICE_NAME} is running on port ${PORT}" || echo "WARNING: service failed to start"
REMOTE

echo ""
echo "==> Deploy complete."
echo "    Dashboard: http://${VPS_HOST}:${PORT}"
echo ""
echo "    Next steps on VPS:"
echo "      1. Edit ${REMOTE_DIR}/.env — set FOUNDRY_DEVICE_ID, GITHUB_TOKEN, API keys"
echo "      2. systemctl restart ${SERVICE_NAME}"
echo "      3. Run import: cd ${REMOTE_DIR} && .venv/bin/python scripts/import_vault_projects.py"
echo ""
echo "    Useful commands:"
echo "      ssh ${VPS_SSH} journalctl -u ${SERVICE_NAME} -f   # live logs"
echo "      ssh ${VPS_SSH} systemctl restart ${SERVICE_NAME}  # restart"
