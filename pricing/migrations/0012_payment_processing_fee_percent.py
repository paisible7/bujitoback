from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0011_add_public_uuid'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesssettings',
            name='payment_processing_fee_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                help_text='Frais gateway débités au client (hors recharge Alipay/WeChat).',
                max_digits=5,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
                verbose_name='Frais de traitement API paiement (%)',
            ),
        ),
    ]
