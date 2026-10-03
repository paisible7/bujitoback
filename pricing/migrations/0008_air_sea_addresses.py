from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0007_usd_to_cny'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesssettings',
            name='china_air_address',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Adresse aérien Chine',
            ),
        ),
        migrations.AddField(
            model_name='businesssettings',
            name='china_sea_address',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Adresse maritime Chine',
            ),
        ),
    ]
