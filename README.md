# Bujito Digital — Backend

## Comptes de test (seeder)

Mot de passe pour **tous** : `Test1234!`

| Rôle | Email | Téléphone | Nom |
|------|-------|-----------|-----|
| Admin | `admin@bujito.com` | `+243810000001` | Admin Bujito |
| Client | `alice@bujito.com` | `+243810000002` | Alice Mbala |
| Client | `bob@bujito.com` | `+243810000003` | Bob Kalonji |

Créer / rafraîchir ces comptes et les données de démo :

```bash
python manage.py seed_data --flush
```

---

## Démarrage local

```powershell
# Windows (PowerShell) — le venv s'appelle "venv" (pas .venv)
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data --flush
python manage.py runserver 0.0.0.0:8000
```

Linux / macOS :

```bash
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data --flush
python manage.py runserver 0.0.0.0:8000
```

API locale : `http://127.0.0.1:8000/api/`

---

## Auth (rapide)

- Login : `POST /api/auth/login/` → `{ "email", "password" }`
- Register : `POST /api/auth/register/`
- Profil : `GET /api/auth/profile/` (header `Authorization: Bearer <access>`)

---

## Déploiement (rappel)

Voir aussi `deploy/` (scripts + nginx). En prod : `migrate`, servir `/media/` et `/static/` via Nginx, puis éventuellement `seed_data` si besoin de comptes de démo.
