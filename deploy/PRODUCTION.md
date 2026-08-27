# Checklist déploiement production

Domaine API : `https://apibudig.capslockdev.com`

## A. Backend (VPS)

### 1. Code
```bash
cd /var/www/bujitodigital-backend   # adapter le chemin
git pull
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
```

> `CORS_ALLOW_ALL_ORIGINS=True` ok pour l’app mobile + tests. Restreindre plus tard si besoin.

### 3. Dépendances + migrate + static
```bash
bash deploy/deploy_venv.sh /var/www/bujitodigital-backend
# ou à la main :
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
sudo systemctl restart bujitodigital-backend
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

## B. App Flutter

1. `lib/services/api_endpoints.dart` → URL **prod** (déjà basculé)
2. Build release :
```powershell
.\scripts\build_apk_release.ps1
```
APK : `build\app\outputs\flutter-apk\app-release.apk`

## C. Vérifications post-deploy
- [ ] Login admin / client OK
- [ ] Images colis / commandes visibles
- [ ] Import + upload image OK
- [ ] Commandes admin visibles
- [ ] Notifications OK

## Notes
- Ne **pas** écraser `db.sqlite3` / `media/` du VPS avec la copie locale.
- Ne **pas** committer le `.env` local (DEBUG=True) vers le serveur.
- Paiements carte = encore **simulation** (pas de vrai prestataire).
