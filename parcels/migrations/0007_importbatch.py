# Generated manually

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('parcels', '0006_consolidationparceldecision'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file_name', models.CharField(max_length=255, verbose_name='Nom du fichier')),
                ('file_type', models.CharField(blank=True, default='', max_length=20, verbose_name='Type')),
                ('file', models.FileField(blank=True, null=True, upload_to='imports/%Y/%m/%d/', verbose_name='Fichier')),
                ('created_count', models.PositiveIntegerField(default=0, verbose_name='Créés')),
                ('updated_count', models.PositiveIntegerField(default=0, verbose_name='Mis à jour')),
                ('failed_count', models.PositiveIntegerField(default=0, verbose_name='Échecs')),
                ('matched_count', models.PositiveIntegerField(default=0, verbose_name='Associés')),
                ('message', models.TextField(blank=True, default='', verbose_name='Message')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name="Date d'import")),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='import_batches',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Importé par',
                )),
            ],
            options={
                'verbose_name': 'Import',
                'verbose_name_plural': 'Imports',
                'ordering': ['-created_at'],
            },
        ),
    ]
