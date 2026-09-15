# Generated manually for CBM rate + China payment QR images

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0004_update_china_warehouse_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesssettings',
            name='cbm_rate_usd',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('350.00'),
                max_digits=10,
                verbose_name='CBM — $/m³',
            ),
        ),
        migrations.AddField(
            model_name='businesssettings',
            name='alipay_qr_image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='pricing/qr/%Y/%m/',
                verbose_name='QR Alipay',
            ),
        ),
        migrations.AddField(
            model_name='businesssettings',
            name='wechat_qr_image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='pricing/qr/%Y/%m/',
                verbose_name='QR WeChat Pay',
            ),
        ),
    ]
