import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0009_consolidation_admin_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='expected_parcel_count',
            field=models.PositiveSmallIntegerField(
                default=1,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name='Nombre de colis prévus',
            ),
        ),
        migrations.AddField(
            model_name='parcel',
            name='order_sequence',
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                verbose_name='Numéro de colis dans la commande',
            ),
        ),
        migrations.AddField(
            model_name='parcel',
            name='supplier_tracking_number',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=100,
                null=True,
                verbose_name='Numéro de suivi fournisseur',
            ),
        ),
        migrations.AlterField(
            model_name='parcel',
            name='status',
            field=models.CharField(
                choices=[
                    ('awaiting_arrival', "En attente d'arrivée"),
                    ('pending', "Arrivé à l'entrepôt"),
                    ('consolidated', 'Groupé'),
                    ('in_transit', 'En transit'),
                    ('out_for_delivery', 'En cours de livraison'),
                    ('delivered', 'Livré'),
                    ('exception', 'Exception'),
                ],
                default='pending',
                max_length=20,
                verbose_name='Statut',
            ),
        ),
        migrations.AddConstraint(
            model_name='parcel',
            constraint=models.UniqueConstraint(
                fields=('order', 'order_sequence'),
                name='unique_parcel_sequence_per_order',
            ),
        ),
    ]
