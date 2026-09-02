#!/usr/bin/env bash
set -euo pipefail

# Met à jour le backend sur le serveur (git pull + deps + migrate + restart).
# Usage :
#   bash deploy/remote_update.sh
#   bash deploy/remote_update.sh --already-pulled
#   DEPLOY_PATH=/home/user/public_html bash deploy/remote_update.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${DEPLOY_PATH:-}" ]]; then
  ROOT_DIR="$(cd "$DEPLOY_PATH" && pwd)"
fi
cd "$ROOT_DIR"

already_pulled=0
if [[ "${1:-}" == "--already-pulled" ]]; then
  already_pulled=1
fi

log() { echo "[deploy] $*"; }

log "repo: $ROOT_DIR"

if [[ ! -f manage.py ]]; then
  echo "[deploy] manage.py introuvable dans $ROOT_DIR" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "[deploy] .env manquant — le fichier de prod ne doit pas être écrasé par git." >&2
  exit 1
fi

if [[ "$already_pulled" -eq 0 ]]; then
  log "git fetch + pull (fast-forward)..."
  git fetch origin
  branch="$(git rev-parse --abbrev-ref HEAD)"
  git pull --ff-only origin "$branch"
fi

log "commit: $(git rev-parse --short HEAD) ($(git log -1 --pretty=%s))"

if [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
  PY="$ROOT_DIR/venv/bin/python"
elif [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
  PY="$PYTHON_BIN"
else
  PY="$(command -v python3)"
fi

log "python: $PY ($("$PY" --version 2>&1))"

if [[ ! -d "$ROOT_DIR/venv" && -z "${PYTHON_BIN:-}" ]]; then
  log "création du venv..."
  python3 -m venv venv
  PY="$ROOT_DIR/venv/bin/python"
fi

log "installation des dépendances..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

mkdir -p media staticfiles tmp

log "migrate + collectstatic..."
"$PY" manage.py migrate --noinput
"$PY" manage.py collectstatic --noinput

restarted=0

if [[ -x "$ROOT_DIR/venv/bin/gunicorn" ]] && pgrep -f "$ROOT_DIR/venv/bin/gunicorn" >/dev/null 2>&1; then
  log "reload gunicorn du projet..."
  pkill -HUP -f "$ROOT_DIR/venv/bin/gunicorn" || true
  restarted=1
fi

if [[ -f gunicorn.pid ]]; then
  pid="$(tr -d '[:space:]' < gunicorn.pid || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    log "reload Gunicorn (HUP $pid)..."
    kill -HUP "$pid"
    restarted=1
  fi
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl cat bujitodigital-backend.service >/dev/null 2>&1; then
    log "restart systemd bujitodigital-backend..."
    if sudo -n systemctl restart bujitodigital-backend.service 2>/dev/null; then
      restarted=1
    elif systemctl restart bujitodigital-backend.service 2>/dev/null; then
      restarted=1
    else
      log "systemd présent mais restart refusé (sudo sans mot de passe ?)"
    fi
  fi
fi

# cPanel / Passenger / Application Manager
touch tmp/restart.txt
if [[ -f passenger_wsgi.py || -f tmp/restart.txt ]]; then
  log "Passenger/cPanel restart signal (tmp/restart.txt)"
  restarted=1
fi

if [[ "$restarted" -eq 0 ]]; then
  log "aucun service redémarré automatiquement — redémarre l'app Python dans cPanel si besoin."
fi

log "done"
