from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0017_consolidation_weight_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='parcel',
            name='china_arrival_date',
            field=models.DateField(blank=True, null=True, verbose_name="Date d'arrivée Chine"),
        ),
        migrations.AddField(
            model_name='parcel',
            name='weight_kg',
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=10,
                null=True,
                verbose_name='Poids (kg)',
            ),
        ),
        migrations.CreateModel(
            name='ShipmentBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='Code MCO')),
                ('status', models.CharField(
                    choices=[('open', 'Ouvert'), ('shipped', 'Expédié'), ('closed', 'Fermé')],
                    default='open',
                    max_length=20,
                    verbose_name='Statut',
                )),
                ('total_weight_kg', models.DecimalField(
                    decimal_places=3,
                    default=0,
                    max_digits=10,
                    verbose_name='Poids total (kg)',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('shipped_at', models.DateTimeField(blank=True, null=True, verbose_name='Expédié le')),
                ('notes', models.TextField(blank=True, default='', verbose_name='Notes')),
                ('parcels', models.ManyToManyField(
                    blank=True,
                    related_name='shipment_batches',
                    to='parcels.parcel',
                    verbose_name='Colis',
                )),
            ],
            options={
                'verbose_name': 'Lot MCO',
                'verbose_name_plural': 'Lots MCO',
                'ordering': ['-created_at'],
            },
        ),
    ]
