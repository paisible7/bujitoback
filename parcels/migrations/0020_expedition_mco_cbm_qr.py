# Generated manually for expedition / MCO CBM

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('parcels', '0019_parcelimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='parcel',
            name='volume_cbm',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=12,
                null=True,
                verbose_name='Volume (CBM)',
            ),
        ),
        migrations.AddField(
            model_name='shipmentbatch',
            name='total_volume_cbm',
            field=models.DecimalField(
                decimal_places=4,
                default=0,
                max_digits=12,
                verbose_name='Volume total (CBM)',
            ),
        ),
        migrations.AddField(
            model_name='shipmentbatch',
            name='admin_description',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Description admin (expédition)',
            ),
        ),
        migrations.AddField(
            model_name='shipmentbatch',
            name='admin_photo',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='shipments/%Y/%m/',
                verbose_name='Photo admin (expédition)',
            ),
        ),
        migrations.CreateModel(
            name='ExpeditionRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mode', models.CharField(
                    choices=[
                        ('bujito_digital', 'Expédier par Bujito Digital'),
                        ('other_forwarder', 'Expédier par un autre transitaire'),
                    ],
                    max_length=30,
                    verbose_name='Mode',
                )),
                ('shipping_category', models.CharField(
                    blank=True,
                    choices=[
                        ('ordinary', 'Colis ordinaire'),
                        ('sensitive', 'Colis sensibles'),
                        ('phone', 'Téléphone'),
                    ],
                    max_length=20,
                    null=True,
                    verbose_name="Catégorie d'expédition",
                )),
                ('weight_kg', models.DecimalField(
                    decimal_places=3, default=0, max_digits=10, verbose_name='Poids (kg)',
                )),
                ('volume_cbm', models.DecimalField(
                    decimal_places=4, default=0, max_digits=12, verbose_name='Volume (CBM)',
                )),
                ('grouping_fee', models.DecimalField(
                    decimal_places=2, default=0, max_digits=10,
                    verbose_name='Frais de groupage (USD)',
                )),
                ('shipping_fee', models.DecimalField(
                    decimal_places=2, default=0, max_digits=10,
                    verbose_name="Frais d'expédition (USD)",
                )),
                ('forwarder_delivery_fee', models.DecimalField(
                    decimal_places=2, default=0, max_digits=10,
                    verbose_name='Frais livraison autre transitaire (USD)',
                )),
                ('cbm_fee', models.DecimalField(
                    decimal_places=2, default=0, max_digits=10,
                    verbose_name='Frais CBM total (USD)',
                )),
                ('cbm_fee_advance', models.DecimalField(
                    decimal_places=2, default=0, max_digits=10,
                    verbose_name='Acompte CBM 50% (USD)',
                )),
                ('total_due_now', models.DecimalField(
                    decimal_places=2, default=0, max_digits=10,
                    verbose_name='Montant dû maintenant (USD)',
                )),
                ('was_grouped', models.BooleanField(default=False, verbose_name='Colis groupé')),
                ('status', models.CharField(
                    choices=[
                        ('quoted', 'Devis'),
                        ('awaiting_payment', 'En attente de paiement'),
                        ('paid', 'Payé'),
                        ('cancelled', 'Annulé'),
                    ],
                    default='awaiting_payment',
                    max_length=20,
                    verbose_name='Statut',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('paid_at', models.DateTimeField(blank=True, null=True, verbose_name='Payé le')),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='expeditions_created',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Créé par',
                )),
                ('parcels', models.ManyToManyField(
                    related_name='expeditions',
                    to='parcels.parcel',
                    verbose_name='Colis',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='expeditions',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Client',
                )),
            ],
            options={
                'verbose_name': "Demande d'expédition",
                'verbose_name_plural': "Demandes d'expédition",
                'ordering': ['-created_at'],
            },
        ),
    ]
