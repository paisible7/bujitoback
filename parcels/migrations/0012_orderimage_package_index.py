from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0011_order_commission_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderimage',
            name='package_index',
            field=models.PositiveSmallIntegerField(
                default=0,
                verbose_name='Index du colis dans la commande',
            ),
        ),
    ]
