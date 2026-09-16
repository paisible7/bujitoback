from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0020_expedition_mco_cbm_qr'),
    ]

    operations = [
        migrations.AddField(
            model_name='expeditionrequest',
            name='transport_mode',
            field=models.CharField(
                blank=True,
                choices=[('air', 'Par avion'), ('sea', 'Par bateau')],
                max_length=10,
                null=True,
                verbose_name='Transport (avion / bateau)',
            ),
        ),
        migrations.AddField(
            model_name='expeditionrequest',
            name='forwarder_address',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Adresse autre transitaire',
            ),
        ),
        migrations.AlterField(
            model_name='expeditionrequest',
            name='shipping_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ordinary', 'Colis ordinaire'),
                    ('sensitive', 'Colis sensibles'),
                    ('phone', 'Téléphone'),
                ],
                max_length=20,
                null=True,
                verbose_name="Catégorie d'expédition (avion)",
            ),
        ),
        migrations.AlterField(
            model_name='expeditionrequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('quoted', 'En attente frais transfert'),
                    ('awaiting_payment', 'En attente de paiement'),
                    ('paid', 'Payé'),
                    ('cancelled', 'Annulé'),
                ],
                default='awaiting_payment',
                max_length=20,
                verbose_name='Statut',
            ),
        ),
        migrations.AlterField(
            model_name='expeditionrequest',
            name='forwarder_delivery_fee',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=10,
                verbose_name='Frais transfert autre transitaire (USD)',
            ),
        ),
    ]
