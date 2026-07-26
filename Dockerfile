# Utiliser une image Python officielle légère
FROM python:3.12-slim

# Définir des variables d'environnement
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Définir le répertoire de travail
WORKDIR /app

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copier le projet
COPY . /app/

# Créer un dossier pour les fichiers statiques
RUN mkdir -p /app/staticfiles

# Exposer le port
EXPOSE 8000

# Commande par défaut pour démarrer le serveur (sera écrasée par docker-compose si besoin)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "backend.wsgi:application"]
