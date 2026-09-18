from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0006_cbm_rate_500"),
    ]

    operations = [
        migrations.AddField(
            model_name="businesssettings",
            name="usd_to_cny",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("6.3000"),
                max_digits=12,
                verbose_name="1 USD → CNY (yuan)",
            ),
        ),
    ]
