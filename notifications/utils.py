import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)

from .text_sanitizer import strip_emojis

def initialize_firebase():
    """Initialise Firebase Admin SDK si ce n'est pas déjà fait."""
    if not firebase_admin._apps:
        # Chemin vers le fichier JSON que vous allez télécharger depuis Firebase Console
        cred_path = os.path.join(settings.BASE_DIR, 'firebase-service-account.json')
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            logger.error(f"Fichier Firebase introuvable à : {cred_path}")

from django.utils import translation
from django.utils.translation import gettext as _

def send_fcm_notification(user, title, body, data=None, *, type="info", reference_id=None):
    """Envoie une notification à tous les appareils enregistrés d'un utilisateur."""
    # Activer la langue de l'utilisateur pour la traduction
    user_language = getattr(user, 'language', 'fr')
    with translation.override(user_language):
        initialize_firebase()
        from .models import FCMDevice, Notification

        # On s'assure que les textes sont traduits
        translated_title = strip_emojis(_(title))
        translated_body = strip_emojis(_(body))

        # 1. Sauvegarder dans l'historique
        notif = Notification.objects.create(
            user=user,
            title=translated_title,
            message=translated_body,
            type=type or 'info',
            reference_id=reference_id
        )

        # 2. Récupérer les tokens
        devices = FCMDevice.objects.filter(user=user)
        tokens = [d.token for d in devices]

        if not tokens:
            return {"success": False, "message": "Aucun appareil enregistré."}

        # 3. Préparer le message FCM
        payload = dict(data or {})
        if type is not None:
            payload.setdefault("type", str(type))
        if reference_id is not None:
            payload.setdefault("reference_id", str(reference_id))
        payload.setdefault("notification_id", str(notif.pk))
        payload.setdefault("created_at", notif.created_at.isoformat().replace("+00:00", "Z"))
        payload = {str(k): "" if v is None else str(v) for k, v in payload.items()}

        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=translated_title,
                body=translated_body,
            ),
            data=payload,
            tokens=tokens,
        )

        # 4. Envoyer via Firebase
        response = messaging.send_each_for_multicast(message)
        return {
            "success": True,
            "success_count": response.success_count,
            "failure_count": response.failure_count
        }
