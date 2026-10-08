from django.db import migrations

from core.migration_helpers import add_public_uuid_field


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0001_initial'),
    ]

    operations = add_public_uuid_field('reports', 'expense')
