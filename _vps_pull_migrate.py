"""VPS: git fetch + pull, migrate, restart bujito_backend."""
import paramiko

HOST = "vps120167.serveur-vps.net"
USER = "root"
PASSWORD = "Z4Y7e3J94"
APP = "/home/paisible/web/apibudig.capslockdev.com/public_html"

REMOTE = f"""
set -euo pipefail
cd '{APP}'
GIT="git -c safe.directory={APP}"

if [[ -x '{APP}/venv/bin/python' ]]; then
  PY='{APP}/venv/bin/python'
else
  PY="$(command -v python3)"
fi

echo "=== BEFORE ==="
$GIT rev-parse --short HEAD
$GIT log -1 --pretty='%h %s'
$GIT status -sb | head -15

echo "=== FETCH + PULL ==="
$GIT fetch origin
branch="$($GIT rev-parse --abbrev-ref HEAD)"
if [[ "$branch" == "HEAD" ]]; then
  branch=main
fi
$GIT pull --ff-only origin "$branch"

echo "=== MIGRATE ==="
"$PY" manage.py migrate --noinput

echo "=== RESTART ==="
systemctl restart bujito_backend.service
sleep 2
systemctl is-active bujito_backend.service

echo "=== AFTER ==="
$GIT rev-parse --short HEAD
$GIT log -1 --pretty='%h %s'
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
_, stdout, stderr = client.exec_command(REMOTE, timeout=300)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
code = stdout.channel.recv_exit_status()
client.close()
print(out)
if err.strip():
    print("STDERR:", err)
raise SystemExit(code)
