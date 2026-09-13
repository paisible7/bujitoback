from django.db import migrations, models


NEW_PHONE = "18364649039"
NEW_STREET = (
    "浙江省台州市椒江区 浙江省台州市椒江区 "
    "市府大道1139号台州学院椒江校区台州学院椒江校区国际会议厅bujito"
)


def forwards(apps, schema_editor):
    BusinessSettings = apps.get_model("pricing", "BusinessSettings")
    # Met à jour la ligne singleton (pk=1) et toute autre éventuelle.
    BusinessSettings.objects.all().update(
        china_warehouse_phone=NEW_PHONE,
        china_warehouse_street=NEW_STREET,
    )


def backwards(apps, schema_editor):
    BusinessSettings = apps.get_model("pricing", "BusinessSettings")
    BusinessSettings.objects.all().update(
        china_warehouse_phone="18575740344",
        china_warehouse_street="佛山市南海区狮山镇塘头村一队新一巷3号bujito",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0003_china_warehouse_verbose_fcfa"),
    ]

    operations = [
        migrations.AlterField(
            model_name="businesssettings",
            name="china_warehouse_phone",
            field=models.CharField(
                default=NEW_PHONE,
                max_length=50,
                verbose_name="Entrepôt Chine — téléphone",
            ),
        ),
        migrations.AlterField(
            model_name="businesssettings",
            name="china_warehouse_street",
            field=models.CharField(
                default=NEW_STREET,
                max_length=500,
                verbose_name="Entrepôt Chine — adresse",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
