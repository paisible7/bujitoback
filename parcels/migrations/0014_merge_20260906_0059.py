# Generated manually — same name as VPS merge (2026-09-06).
from django.db import migrations


class Migration(migrations.Migration):
    """Unifie la branche VPS (alter/merge) et la branche app (admin_note_image)."""

    dependencies = [
        ('parcels', '0013_consolidation_admin_note_image'),
        ('parcels', '0013_merge_20260902_2127'),
    ]

    operations = []
