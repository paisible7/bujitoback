from decimal import Decimal

from django.db import migrations, models
from django.core.validators import MaxValueValidator, MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0015_electronics_fragile_per_kg_labels'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesssettings',
            name='usd_to_eur',
            field=models.DecimalField(
                decimal_places=6,
                default=Decimal('0.920000'),
                max_digits=12,
                verbose_name='1 USD → EUR (€)',
            ),
        ),
        migrations.AddField(
            model_name='businesssettings',
            name='money_transfer_fee_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=5,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
                verbose_name="Frais de transfert d'argent (%)",
                help_text='Frais appliqués aux transferts d’argent (hors recharge Alipay/WeChat).',
            ),
        ),
    ]
