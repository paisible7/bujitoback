# Generated manually to align VPS migration history (no-op on fresh installs).
from django.db import migrations


class Migration(migrations.Migration):
    """Ancienne branche VPS (alter status). Schéma déjà couvert par 0010_automatic_*."""

    dependencies = [
        ('parcels', '0009_consolidation_admin_note'),
    ]

    operations = []
