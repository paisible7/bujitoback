#!/usr/bin/env bash
set -euo pipefail

# Compat: ancien point d'entrée. Préférer deploy/remote_update.sh
#   bash deploy/deploy_venv.sh /absolute/path/to/bujitodigital-backend

REPO_DIR="${1:-}"
if [[ -z "${REPO_DIR}" ]]; then
  echo "usage: $0 /absolute/path/to/bujitodigital-backend"
  exit 2
fi

export DEPLOY_PATH="$REPO_DIR"
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/remote_update.sh"
