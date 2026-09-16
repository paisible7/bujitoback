# Generated manually — air loyalty discount for 5★ clients

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0022_expedition_outbound_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='expeditionrequest',
            name='loyalty_discount_usd',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='50 % sur le tarif avion pour clients 5★.',
                max_digits=10,
                verbose_name='Réduction fidélité aérienne (USD)',
            ),
        ),
    ]
