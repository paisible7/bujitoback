# Checklist déploiement production

Domaine API : `https://apibudig.capslockdev.com`

## Idée

GitHub Actions = **déclencheur SSH** uniquement.  
Tout le travail (git, migrate, collectstatic, restart) se fait **sur le VPS**, comme en manuel.

```text
git push origin main
        ↓
GitHub Actions (SSH)
        ↓
VPS : fetch + reset --hard origin/main
        ↓
migrate + collectstatic + restart bujito_backend
```

Les tests Django restent dans le workflow **CI** (`ci.yml`) sur les PR — pas dans le deploy.

---

## A. Activer le deploy auto (une fois)

### 1. Clé SSH dédiée (recommandé : user `paisible`, pas root)

Sur Windows :

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\bujito_deploy -N ""
Get-Content $env:USERPROFILE\.ssh\bujito_deploy.pub
```

Sur le VPS, ajouter la **publique** dans `/home/paisible/.ssh/authorized_keys`  
(ou `/root/.ssh/authorized_keys` si tu gardes `SSH_USER=root`).

Autoriser uniquement le restart du service (en root une fois) :

```bash
echo 'paisible ALL=(root) NOPASSWD: /bin/systemctl restart bujito_backend, /bin/systemctl is-active bujito_backend, /bin/systemctl status bujito_backend' > /etc/sudoers.d/bujito-deploy
chmod 440 /etc/sudoers.d/bujito-deploy
```

### 2. Secrets GitHub (repo `paisible7/bujitoback`)

| Secret | Valeur recommandée |
|--------|--------------------|
| `SSH_HOST` | `vps120167.serveur-vps.net` |
| `SSH_USER` | `paisible` (idéal) ou `root` |
| `SSH_KEY` | clé **privée** `bujito_deploy` |
| `DEPLOY_PATH` | `/home/paisible/web/apibudig.capslockdev.com/public_html` |

Variable :

| Variable | Valeur |
|----------|--------|
| `DEPLOY_ENABLED` | `true` |

Sans `DEPLOY_ENABLED=true`, le job deploy ne part pas.

### 3. Vérifier

- Push sur `main` → onglet **Actions** → `Deploy production`
- Ou **Run workflow** à la main

`.env`, `db.sqlite3`, `media/` ne sont **pas** écrasés (gitignored + reset ne touche pas les untracked).

---

## A2. Secours depuis Windows

```powershell
cd C:\Users\paisible\Work\Android\CAPSLOCK\bujitodigital-backend
.\deploy\deploy_from_local.ps1
```

---

## B. Manuel sur le VPS

```bash
cd ~/web/apibudig.capslockdev.com/public_html
bash deploy/remote_update.sh
# si sudoers pas configuré :
sudo systemctl restart bujito_backend
```

`remote_update.sh` fait : `git fetch` + `reset --hard origin/<branch>` + pip + migrate + collectstatic + tentative restart.

### `.env` production
```env
DEBUG=False
SECRET_KEY=<clé-longue-aléatoire>
ALLOWED_HOSTS=apibudig.capslockdev.com,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://apibudig.capslockdev.com
CORS_ALLOW_ALL_ORIGINS=True
PUBLIC_BASE_URL=https://apibudig.capslockdev.com
SERVE_MEDIA=True
PAYMENT_WEBHOOK_SECRET=<secret>
```

---

## C. App Flutter

Pointer `api_endpoints.dart` vers la prod, puis build release.

## D. Post-deploy
- [ ] Login OK
- [ ] Media / images OK
- [ ] Groupage + notifications OK
- [ ] `systemctl status bujito_backend` → active

## Notes
- `reset --hard` = le code VPS **copie** `origin/main` (idéal si on ne modifie jamais le code à la main sur le serveur).
- Ne pas lancer `makemigrations` sur le VPS.
- Service systemd : **`bujito_backend`**.
