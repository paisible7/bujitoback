from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0010_expedition_mco_cbm_qr"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="qr_image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="payments/qr/%Y/%m/",
                verbose_name="QR Alipay / WeChat",
            ),
        ),
    ]
