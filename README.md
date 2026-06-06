# Guide du Backend Django - Bujito Digital

Ce document contient toutes les informations nécessaires pour faire tourner, tester et déployer le backend Django.

## 1. Identifiants de Test (Développement)

Ces comptes ont été pré-créés dans la base de données locale SQLite :

### Compte Administrateur (Admin)
- **Email** : `admin@test.com`
- **Mot de passe** : `admin123`
- **Rôle** : `admin`

### Compte Utilisateur Standard (User)
- **Email** : `user@test.com`
- **Mot de passe** : `user123`
- **Rôle** : `user`

---

## 2. Commandes Backend Utiles

Toutes ces commandes doivent être exécutées dans le dossier `bujitodigital-backend`.

### A. Activer l'environnement virtuel (venv)
- **Sur Windows (PowerShell)** :
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **Sur Windows (CMD)** :
  ```cmd
  .\venv\Scripts\activate.bat
  ```
- **Sur Linux / macOS** :
  ```bash
  source venv/bin/activate
  ```

### B. Lancer le serveur de développement
Une fois le `venv` activé :
```bash
python manage.py runserver 0.0.0.0:8000
```

### C. Gérer la base de données (Migrations)
Si vous modifiez des modèles dans `users/models.py` :
1. Générer les fichiers de migration :
   ```bash
   python manage.py makemigrations
   ```
2. Appliquer les migrations à la base de données :
   ```bash
   python manage.py migrate
   ```

### D. Créer un nouveau Superutilisateur (Admin) via la console
Si vous souhaitez créer un autre compte admin interactivement :
```bash
python manage.py createsuperuser
```
*(Entrez l'email et le mot de passe demandés).*

---

## 3. Endpoints API Implémentés

Tous les endpoints commencent par le préfixe `/api/auth/`.

### A. Inscription (Register)
- **URL** : `http://127.0.0.1:8000/api/auth/register/`
- **Méthode** : `POST`
- **Corps JSON attendu** :
  ```json
  {
    "email": "nouveau_user@test.com",
    "password": "motdepassefort",
    "role": "user" // Optionnel, par défaut "user"
  }
  ```
- **Réponse (Succès - 201 Created)** :
  ```json
  {
    "refresh": "TOKEN_JWT_DE_RAFRAICHISSEMENT",
    "access": "TOKEN_JWT_D_ACCES",
    "email": "nouveau_user@test.com",
    "role": "user"
  }
  ```

### B. Connexion (Login)
- **URL** : `http://127.0.0.1:8000/api/auth/login/`
- **Méthode** : `POST`
- **Corps JSON attendu** :
  ```json
  {
    "email": "user@test.com",
    "password": "user123"
  }
  ```
- **Réponse (Succès - 200 OK)** :
  ```json
  {
    "refresh": "TOKEN_JWT_DE_RAFRAICHISSEMENT",
    "access": "TOKEN_JWT_D_ACCES"
  }
  ```

### C. Profil Utilisateur (Protégé)
- **URL** : `http://127.0.0.1:8000/api/auth/profile/`
- **Méthode** : `GET`
- **Header requis** : `Authorization: Bearer <TOKEN_JWT_D_ACCES>`
- **Réponse (Succès - 200 OK)** :
  ```json
  {
    "id": 1,
    "email": "user@test.com",
    "role": "user"
  }
  ```

---

## 4. Déploiement sur Serveur VPS (Hestia CP sur LWS)

Pour déployer ce backend Django sur votre serveur VPS équipé de Hestia Control Panel :

### Étape 1 : Créer le site et la base de données dans Hestia CP
1. Connectez-vous à Hestia CP.
2. Créez un domaine web (ex: `api.bujitodigital.com`) avec SSL Let's Encrypt activé.
3. Créez une base de données MySQL (ou PostgreSQL si vous préférez) depuis le panel Hestia.

### Étape 2 : Envoyer le code sur le VPS et configurer l'environnement
1. Connectez-vous en SSH à votre VPS.
2. Clonez votre dépôt git ou uploadez le dossier `bujitodigital-backend` dans `/home/admin/web/api.bujitodigital.com/` (ou le dossier utilisateur correspondant).
3. Installez Python, pip et venv sur le serveur :
   ```bash
   sudo apt update
   sudo apt install python3-pip python3-venv python3-dev libmysqlclient-dev
   ```
4. Créez et activez le `venv` sur le VPS :
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
5. Installez les paquets requis :
   ```bash
   pip install django djangorestframework djangorestframework-simplejwt django-cors-headers mysqlclient gunicorn
   ```

### Étape 3 : Configurer Django pour la Production
Modifiez le fichier `backend/settings.py` du VPS :
1. Mettez `DEBUG = False`.
2. Ajoutez votre nom de domaine dans `ALLOWED_HOSTS` :
   ```python
   ALLOWED_HOSTS = ['api.bujitodigital.com']
   ```
3. Configurez la connexion à la base de données MySQL créée dans Hestia CP :
   ```python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.mysql',
           'NAME': 'nom_bdd_hestia',
           'USER': 'user_bdd_hestia',
           'PASSWORD': 'mot_de_passe_bdd',
           'HOST': '127.0.0.1',
           'PORT': '3306',
       }
   }
   ```
4. Exécutez les migrations sur le serveur :
   ```bash
   python manage.py migrate
   ```

### Étape 4 : Configurer Gunicorn et Systemd (Service de fond)
1. Créez un fichier service pour Gunicorn :
   ```bash
   sudo nano /etc/systemd/system/gunicorn.service
   ```
2. Ajoutez la configuration suivante (adaptez les chemins utilisateur) :
   ```ini
   [Unit]
   Description=gunicorn daemon for Bujito Digital API
   After=network.target

   [Service]
   User=admin
   Group=www-data
   WorkingDirectory=/home/admin/web/api.bujitodigital.com/private/bujitodigital-backend
   ExecStart=/home/admin/web/api.bujitodigital.com/private/bujitodigital-backend/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 backend.wsgi:application

   [Install]
   WantedBy=multi-user.target
   ```
3. Démarrez et activez le service Gunicorn :
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start gunicorn
   sudo systemctl enable gunicorn
   ```

### Étape 5 : Configurer Nginx en Reverse Proxy dans Hestia CP
Dans Hestia CP, modifiez la configuration Nginx pour votre domaine `api.bujitodigital.com` pour rediriger les requêtes vers Gunicorn (port 8000) :
1. Allez dans **Web** -> Modifier le domaine `api.bujitodigital.com` -> **Advanced Options**.
2. Dans la configuration Nginx (ou en éditant directement le fichier de configuration Nginx du domaine sur le serveur dans `/home/admin/conf/web/api.bujitodigital.com/nginx.conf`), ajoutez un bloc `location /` :
   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```
3. Redémarrez Nginx :
   ```bash
   sudo systemctl restart nginx
   ```
Votre backend est maintenant accessible en ligne sécurisé par SSL sous `https://api.bujitodigital.com` !
