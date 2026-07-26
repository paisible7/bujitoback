#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash deploy/deploy_venv.sh /absolute/path/to/bujitodigital-backend
#
# This script:
# - pulls latest code
# - ensures venv
# - installs requirements
# - runs migrate + collectstatic
# - restarts systemd service (if present)

REPO_DIR="${1:-}"
if [[ -z "${REPO_DIR}" ]]; then
  echo "usage: $0 /absolute/path/to/bujitodigital-backend"
  exit 2
fi

cd "$REPO_DIR"

echo "[deploy] repo: $REPO_DIR"

echo "[deploy] pulling latest code (if repo has origin configured)..."
git pull --rebase || true

if [[ ! -d "venv" ]]; then
  echo "[deploy] creating venv..."
  python3 -m venv venv
fi

echo "[deploy] installing python deps..."
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt

echo "[deploy] migrate + collectstatic..."
./venv/bin/python manage.py migrate --noinput
./venv/bin/python manage.py collectstatic --noinput

if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-unit-files | grep -q "^bujitodigital-backend\\.service"; then
    echo "[deploy] restarting systemd service..."
    sudo systemctl restart bujitodigital-backend.service
  else
    echo "[deploy] systemd service not installed (bujitodigital-backend.service)"
  fi
fi

echo "[deploy] done"

