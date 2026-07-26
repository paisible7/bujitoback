from django.apps import AppConfig


class ParcelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "parcels"

    def ready(self):
        # Register signal handlers.
        from . import signals  # noqa: F401

