#!/bin/bash
set -euo pipefail
cd /root/projects/foundry

echo "==> Python version"
python3 --version

echo "==> Creating venv"
[ -d .venv ] || python3 -m venv .venv

echo "==> Installing dependencies"
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[dev]"

echo "==> Creating .env"
[ -f .env ] || cp .env.example .env

echo "==> Creating dirs"
mkdir -p /root/.foundry/logs

echo "==> Writing systemd service"
cat > /etc/systemd/system/foundry.service << 'SERVICE'
[Unit]
Description=Foundry Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/projects/foundry
EnvironmentFile=/root/projects/foundry/.env
ExecStart=/root/projects/foundry/.venv/bin/python -m uvicorn foundry.dashboard.app:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

echo "==> Starting service"
systemctl daemon-reload
systemctl enable foundry
systemctl restart foundry
sleep 3
systemctl is-active foundry && echo "foundry RUNNING on :8000" || (echo "FAILED:"; journalctl -u foundry -n 30 --no-pager)
