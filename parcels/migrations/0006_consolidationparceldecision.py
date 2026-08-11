# Generated manually

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0005_order_images'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConsolidationParcelDecision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('decision', models.CharField(
                    choices=[('pending', 'En attente'), ('accepted', 'Validé'), ('rejected', 'Refusé')],
                    default='pending',
                    max_length=20,
                    verbose_name='Décision',
                )),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Mis à jour')),
                ('consolidation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='parcel_decisions',
                    to='parcels.consolidation',
                    verbose_name='Groupage',
                )),
                ('parcel', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='consolidation_decisions',
                    to='parcels.parcel',
                    verbose_name='Colis',
                )),
            ],
            options={
                'verbose_name': 'Décision colis (groupage)',
                'verbose_name_plural': 'Décisions colis (groupage)',
                'unique_together': {('consolidation', 'parcel')},
            },
        ),
    ]
