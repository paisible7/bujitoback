# Generated manually for quote fields on Order

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0007_importbatch'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='withdrawal_fee',
            field=models.DecimalField(
                decimal_places=2,
                default=0.0,
                max_digits=10,
                verbose_name='Frais de retrait',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='quote_ready',
            field=models.BooleanField(default=False, verbose_name='Devis établi'),
        ),
    ]
