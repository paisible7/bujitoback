# Generated manually for admin_permissions foundation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_customuser_stars'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='admin_permissions',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    'Clés de modules admin (orders, parcels, …). '
                    'Liste vide = tous les droits (comportement actuel).'
                ),
                verbose_name='Permissions admin',
            ),
        ),
    ]
