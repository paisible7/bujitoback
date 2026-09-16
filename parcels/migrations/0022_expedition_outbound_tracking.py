# Generated manually — confirm other-forwarder dispatch with tracking

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0021_expedition_transport_forwarder_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='expeditionrequest',
            name='outbound_tracking_number',
            field=models.CharField(
                blank=True,
                default='',
                max_length=100,
                verbose_name='N° suivi envoi vers transitaire',
            ),
        ),
        migrations.AddField(
            model_name='expeditionrequest',
            name='shipped_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Envoyé le',
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
                    ('shipped', 'Envoyé vers transitaire'),
                    ('cancelled', 'Annulé'),
                ],
                default='awaiting_payment',
                max_length=20,
                verbose_name='Statut',
            ),
        ),
    ]
