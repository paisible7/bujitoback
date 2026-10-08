from django.db import migrations, models

from core.migration_helpers import add_public_uuid_field


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_notification_image'),
    ]

    operations = [
        *add_public_uuid_field('notifications', 'fcmdevice'),
        *add_public_uuid_field('notifications', 'notification'),
        migrations.AlterField(
            model_name='notification',
            name='reference_id',
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                verbose_name='ID de référence',
            ),
        ),
    ]
