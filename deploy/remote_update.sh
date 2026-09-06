#!/usr/bin/env bash
set -euo pipefail

# Met à jour le backend sur le serveur (git sync + deps + migrate + collectstatic).
# Usage :
#   bash deploy/remote_update.sh
#   bash deploy/remote_update.sh --already-pulled
#   DEPLOY_PATH=/home/user/public_html bash deploy/remote_update.sh
#   SYSTEMD_SERVICE=bujito_backend bash deploy/remote_update.sh
#
# Par défaut : git fetch + reset --hard origin/<branch> (VPS = copie exacte de GitHub).
# Restart systemd : préfère un sudo limité pour paisible, sinon restart depuis root (CI).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${DEPLOY_PATH:-}" ]]; then
  ROOT_DIR="$(cd "$DEPLOY_PATH" && pwd)"
fi
cd "$ROOT_DIR"

already_pulled=0
if [[ "${1:-}" == "--already-pulled" ]]; then
  already_pulled=1
fi

# Service réel en prod (override possible).
SYSTEMD_SERVICE="${SYSTEMD_SERVICE:-bujito_backend}"

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
  log "git fetch + reset --hard origin/<branch>..."
  git fetch origin
  branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$branch" == "HEAD" ]]; then
    branch="main"
    git checkout -B main "origin/main"
  fi
  git reset --hard "origin/$branch"
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

try_systemctl_restart() {
  local unit="$1"
  # Accepte "bujito_backend" ou "bujito_backend.service"
  local name="${unit%.service}"

  if ! command -v systemctl >/dev/null 2>&1; then
    return 1
  fi
  if ! systemctl cat "${name}.service" >/dev/null 2>&1; then
    return 1
  fi

  log "restart systemd ${name}.service..."
  if sudo -n systemctl restart "${name}.service" 2>/dev/null; then
    return 0
  fi
  if systemctl restart "${name}.service" 2>/dev/null; then
    return 0
  fi
  log "systemd ${name}.service présent mais restart refusé (pas root / sudo nopasswd)."
  log "→ redémarre en root : systemctl restart ${name}.service"
  return 1
}

# 1) Service configuré (prod = bujito_backend)
if try_systemctl_restart "$SYSTEMD_SERVICE"; then
  restarted=1
fi

# 2) Ancien nom de service (rétrocompat)
if [[ "$restarted" -eq 0 ]]; then
  if try_systemctl_restart "bujitodigital-backend"; then
    restarted=1
  fi
fi

# 3) Reload gunicorn du projet si déjà lancé (fallback soft)
if [[ "$restarted" -eq 0 ]]; then
  if [[ -x "$ROOT_DIR/venv/bin/gunicorn" ]] && pgrep -f "$ROOT_DIR/venv/bin/gunicorn" >/dev/null 2>&1; then
    log "reload gunicorn du projet (HUP)..."
    pkill -HUP -f "$ROOT_DIR/venv/bin/gunicorn" || true
    restarted=1
  fi
fi

if [[ "$restarted" -eq 0 && -f gunicorn.pid ]]; then
  pid="$(tr -d '[:space:]' < gunicorn.pid || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    log "reload Gunicorn (HUP $pid)..."
    kill -HUP "$pid"
    restarted=1
  fi
fi

# cPanel / Passenger / Application Manager
touch tmp/restart.txt
if [[ -f passenger_wsgi.py ]]; then
  log "Passenger/cPanel restart signal (tmp/restart.txt)"
  restarted=1
fi

if [[ "$restarted" -eq 0 ]]; then
  log "aucun service redémarré automatiquement — restart root requis (ex: systemctl restart ${SYSTEMD_SERVICE})."
fi

log "done"
