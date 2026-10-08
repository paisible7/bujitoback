import uuid

from django.db import models


class PublicUUIDModel(models.Model):
    """
    Identifiant public UUID pour toutes les entités métier.

    La PK interne (BigAutoField) reste pour les FK / perfs SQL.
    L'API et le client exposent `uuid` comme `id`.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        verbose_name='UUID public',
    )

    class Meta:
        abstract = True


class UUIDPrimaryModel(models.Model):
    """PK UUID — pour les tables d'images / pièces jointes."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    class Meta:
        abstract = True
