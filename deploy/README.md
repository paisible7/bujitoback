# Deployment (VPS)

This repo supports two simple deployment styles:

1) Docker Compose (recommended if Docker is available on the VPS)
2) Systemd + venv + Gunicorn (no Docker)

Pick one and stick to it.

## 1) Docker Compose (recommended)

Prereqs on VPS:
- Docker + Docker Compose plugin (`docker compose version`)
- A reverse proxy (Nginx/Apache) forwarding to `127.0.0.1:8000` or exposing port 8000 directly

Steps:
1. Clone (or update) the repo on the VPS.
2. Create `.env` from `.env.example` and set at least:
   - `DEBUG=False`
   - `ALLOWED_HOSTS=your.domain.com,127.0.0.1,localhost`
   - `CORS_ALLOW_ALL_ORIGINS=False` (or True for quick testing)
3. Run:
   - `bash deploy/deploy_docker.sh`

Notes:
- Current `docker-compose.yml` runs `migrate` + `collectstatic` on each start.
- With SQLite, ensure `db.sqlite3` is persisted (this repo currently keeps it in the project folder).

## 2) Systemd + venv + Gunicorn (no Docker)

Prereqs on VPS:
- Python 3.12+ (match your server)
- `pip`, `venv`
- systemd
- Nginx or Apache

Suggested layout (example):
- `/var/www/bujitodigital-backend` (repo)
- system user: `www-data`

Steps:
1. Clone repo to the server path.
2. Create `.env` (same as above).
3. Install and configure the service:
   - Copy `deploy/bujitodigital-backend.service` to:
     - `/etc/systemd/system/bujitodigital-backend.service`
   - Edit paths inside the service file to match your VPS.
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable --now bujitodigital-backend`
4. Run deploy/update:
   - `bash deploy/deploy_venv.sh /var/www/bujitodigital-backend`
5. Reverse proxy:
   - Nginx example: `deploy/nginx-bujitodigital-backend.conf`
   - Apache example: `deploy/apache-bujitodigital-backend.conf`

## Troubleshooting
- If you see "no such column ..." on SQLite: run migrations on the VPS:
  - `python manage.py migrate`
- If static files are missing:
  - `python manage.py collectstatic --noinput`

