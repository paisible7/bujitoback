# Generated manually — Payment.expedition FK

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0020_expedition_mco_cbm_qr'),
        ('payments', '0009_payment_currency_fcfa'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='expedition',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payments',
                to='parcels.expeditionrequest',
                verbose_name='Expédition',
            ),
        ),
    ]
