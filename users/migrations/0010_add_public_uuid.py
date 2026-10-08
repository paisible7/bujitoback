from django.db import migrations

from core.migration_helpers import add_public_uuid_field


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_customuser_profile_photo'),
    ]

    operations = add_public_uuid_field('users', 'customuser')
