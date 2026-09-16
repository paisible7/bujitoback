from decimal import Decimal

from django.db import migrations, models


def set_cbm_rate_500(apps, schema_editor):
    BusinessSettings = apps.get_model('pricing', 'BusinessSettings')
    BusinessSettings.objects.filter(pk=1).update(cbm_rate_usd=Decimal('500.00'))


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0005_expedition_mco_cbm_qr'),
    ]

    operations = [
        migrations.AlterField(
            model_name='businesssettings',
            name='cbm_rate_usd',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('500.00'),
                max_digits=10,
                verbose_name='Par bateau (CBM) — $/m³',
            ),
        ),
        migrations.RunPython(set_cbm_rate_500, noop_reverse),
    ]
