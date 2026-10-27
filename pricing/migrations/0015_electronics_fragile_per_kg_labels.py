# Generated manually — labels: forfait → $ / kg (calcul inchangé côté schéma)

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0014_electronics_battery_and_fragile_extra_fees'),
    ]

    operations = [
        migrations.AlterField(
            model_name='businesssettings',
            name='electronics_battery_flat_fee',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('22.00'),
                max_digits=10,
                verbose_name='Électronique avec batterie — $ / kg',
            ),
        ),
        migrations.AlterField(
            model_name='businesssettings',
            name='fragile_extra_flat_fee',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('20.00'),
                max_digits=10,
                verbose_name='Extras fragiles — $ / kg',
            ),
        ),
    ]
