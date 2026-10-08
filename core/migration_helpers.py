"""Helpers pour ajouter un UUID public unique sur tables existantes."""
from __future__ import annotations

import uuid

from django.db import migrations, models


def make_gen_uuids(app_label: str, model_name: str):
    def gen_uuids(apps, schema_editor):
        Model = apps.get_model(app_label, model_name)
        for row in Model.objects.all().iterator():
            if getattr(row, 'uuid', None) is None:
                row.uuid = uuid.uuid4()
                row.save(update_fields=['uuid'])

    return gen_uuids


def add_public_uuid_field(app_label: str, model_name: str) -> list:
    """
    1) uuid nullable
    2) peupler chaque ligne
    3) non-null + unique + index
    """
    return [
        migrations.AddField(
            model_name=model_name,
            name='uuid',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(
            make_gen_uuids(app_label, model_name),
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name=model_name,
            name='uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                editable=False,
                db_index=True,
                verbose_name='UUID public',
            ),
        ),
    ]
