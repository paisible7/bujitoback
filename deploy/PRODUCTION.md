# Checklist déploiement production

Domaine API : `https://apibudig.capslockdev.com`

## A. CI/CD GitHub Actions (déploiement auto)

À chaque push sur `main`, GitHub lance les tests puis, si activé, se connecte
en SSH au serveur, fait `git pull`, `migrate`, `collectstatic` et redémarre.

### 1. Une fois sur le serveur (SSH)

Le clone dans `public_html` reste. Vérifie que `git pull` marche déjà :

```bash
cd ~/web/apibudig.capslockdev.com/public_html
git status
git pull
```

Hôte SSH : `vps120167.serveur-vps.net` (tu te connectes en `root`, puis `su - paisible`).

Crée une clé **uniquement pour le deploy** (sur ta machine Windows) :

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\bujito_deploy -N ""
Get-Content $env:USERPROFILE\.ssh\bujito_deploy.pub
```

Ajoute la **clé publique** sur le serveur, dans `/root/.ssh/authorized_keys` (puisque GitHub se connectera en `root`) :

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "COLLER_LA_LIGNE_PUB_ICI" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Test :

```powershell
ssh -i $env:USERPROFILE\.ssh\bujito_deploy root@vps120167.serveur-vps.net "su - paisible -c 'cd ~/web/apibudig.capslockdev.com/public_html && git rev-parse --short HEAD'"
```

### 2. Secrets GitHub (repo `paisible7/bujitoback`)

Settings → Secrets and variables → Actions → **Secrets** :

| Secret | Valeur |
|--------|--------|
| `SSH_HOST` | `vps120167.serveur-vps.net` |
| `SSH_USER` | `root` |
| `SSH_KEY` | contenu **privé** de `bujito_deploy` (tout le fichier, y compris BEGIN/END) |
| `DEPLOY_PATH` | `/home/paisible/web/apibudig.capslockdev.com/public_html` |

Settings → Secrets and variables → Actions → **Variables** :

| Variable | Valeur |
|----------|--------|
| `DEPLOY_ENABLED` | `true` |

Sans `DEPLOY_ENABLED=true`, seuls les tests tournent (le deploy n’est pas lancé).

Le `.env`, `db.sqlite3` et `media/` du serveur **ne sont pas** touchés (gitignored).

### 3. Vérifier

- Onglet **Actions** du repo : workflow `CI` + `Deploy production`
- Ou **Run workflow** à la main (`workflow_dispatch`)

---

## B. Backend (manuel, si besoin)

### 1. Code
```bash
cd ~/web/apibudig.capslockdev.com/public_html
git pull
bash deploy/remote_update.sh --already-pulled
```

### 2. `.env` production (créer / mettre à jour)
```env
DEBUG=False
SECRET_KEY=<clé-longue-aléatoire>
ALLOWED_HOSTS=apibudig.capslockdev.com,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://apibudig.capslockdev.com
CORS_ALLOW_ALL_ORIGINS=True
PUBLIC_BASE_URL=https://apibudig.capslockdev.com
SERVE_MEDIA=True
PAYMENT_WEBHOOK_SECRET=<secret-fourni-au-prestataire>
```

> `CORS_ALLOW_ALL_ORIGINS=True` ok pour l’app mobile + tests. Restreindre plus tard si besoin.

### 3. Dépendances + migrate + static
```bash
bash deploy/remote_update.sh
```

Pour prévisualiser les anciennes commandes payées qui pourraient recevoir des
numéros de suivi (aucune écriture sans `--apply`) :
```bash
python manage.py provision_paid_order_parcels
# Après vérification uniquement :
python manage.py provision_paid_order_parcels --apply
```

### 4. Media (images)
- Dossier `media/` doit exister et être **writable** par `www-data`
- Nginx/Apache : utiliser `deploy/nginx-bujitodigital-backend.conf` ou Apache (Alias `/media/`)
- Test navigateur : `https://apibudig.capslockdev.com/media/parcels/<fichier>.jpg` → **200**
- Si 404 : vérifier `SERVE_MEDIA=True` + restart Gunicorn

### 5. Droits (exemple)
```bash
sudo chown -R www-data:www-data /var/www/bujitodigital-backend/media
sudo chmod -R u+rwX /var/www/bujitodigital-backend/media
```

## C. App Flutter

1. `lib/services/api_endpoints.dart` → URL **prod** (déjà basculé)
2. Build release :
```powershell
.\scripts\build_apk_release.ps1
```
APK : `build\app\outputs\flutter-apk\app-release.apk`

## D. Vérifications post-deploy
- [ ] Login admin / client OK
- [ ] Images colis / commandes visibles
- [ ] Import + upload image OK
- [ ] Commandes admin visibles
- [ ] Notifications OK
- [ ] Devis photo uniquement + nombre de colis enregistrés
- [ ] Paiement confirmé → numéros `BUJ-*` créés une seule fois
- [ ] Colis « En attente d’arrivée » → « Marquer arrivé » → groupage possible

## Notes
- Ne **pas** écraser `db.sqlite3` / `media/` du VPS avec la copie locale.
- Ne **pas** committer le `.env` local (DEBUG=True) vers le serveur.
- Paiements carte = encore **simulation** (pas de vrai prestataire). La
  génération automatique démarre dès qu’un paiement passe réellement à
  `completed` via webhook ou validation admin.
