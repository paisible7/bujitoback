from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0010_automatic_parcel_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='commission_fee',
            field=models.DecimalField(
                decimal_places=2,
                default=0.0,
                max_digits=10,
                verbose_name='Frais de commission',
            ),
        ),
    ]
