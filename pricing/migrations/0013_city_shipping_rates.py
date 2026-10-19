from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0012_payment_processing_fee_percent'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesssettings',
            name='city_shipping_rates',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Ex: {"lubumbashi": {"ordinary_rate_per_kg": 19}}',
                verbose_name='Tarifs par ville',
            ),
        ),
    ]
