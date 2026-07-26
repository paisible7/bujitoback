#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash deploy/deploy_docker.sh
#
# Assumes:
# - You are running this from the repo root on the VPS
# - docker + docker compose plugin installed

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[deploy] repo: $ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[deploy] docker not found"
  exit 1
fi

echo "[deploy] pulling latest code (if repo has origin configured)..."
git pull --rebase || true

echo "[deploy] building + starting containers..."
docker compose up -d --build

echo "[deploy] done"

