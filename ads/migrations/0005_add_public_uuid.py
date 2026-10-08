from django.db import migrations

from core.migration_helpers import add_public_uuid_field


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0004_clear_seed_advertisements'),
    ]

    operations = add_public_uuid_field('ads', 'advertisement')
