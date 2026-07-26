import os
import firebase_admin
from firebase_admin import credentials
from django.apps import AppConfig
from django.conf import settings

class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'

    def ready(self):
        # On évite la double initialisation
        if not firebase_admin._apps:
            # On cherche d'abord dans les variables d'environnement (votre plan)
            # Sinon on cherche le fichier par défaut à la racine
            cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')

            if not cred_path:
                cred_path = os.path.join(settings.BASE_DIR, 'firebase-service-account.json')

            if os.path.exists(cred_path):
                try:
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                except Exception as e:
                    print(f"Erreur lors de l'initialisation Firebase : {e}")
            else:
                print(f"Avertissement : Fichier Firebase introuvable à {cred_path}")
