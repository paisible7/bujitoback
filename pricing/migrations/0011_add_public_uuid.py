from django.db import migrations

from core.migration_helpers import add_public_uuid_field


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0010_businesssettings_computer_flat_fee'),
    ]

    operations = add_public_uuid_field('pricing', 'businesssettings')
