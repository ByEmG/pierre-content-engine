#!/usr/bin/env bash
# Run once on a fresh Ubuntu server (Oracle Cloud Always Free works), from inside the repo folder.
set -euo pipefail

sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip git tzdata

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

[ -f .env ] || { cp .env.example .env; echo "Fill in .env, then run this script again."; exit 0; }

.venv/bin/python -m pytest -q
.venv/bin/python -m engine check || true

sudo cp deploy/content-engine.service /etc/systemd/system/
sudo sed -i "s#/home/ubuntu/pierre-content-engine#$(pwd)#g; s#User=ubuntu#User=$(whoami)#" /etc/systemd/system/content-engine.service
sudo systemctl daemon-reload
sudo systemctl enable --now content-engine
echo "Running. Logs: journalctl -u content-engine -f"
