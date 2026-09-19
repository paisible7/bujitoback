from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parcels", "0023_expedition_loyalty_discount"),
    ]

    operations = [
        migrations.AlterField(
            model_name="expeditionrequest",
            name="shipping_category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ordinary", "Colis ordinaire"),
                    ("express", "Express (colis ordinaire)"),
                    ("sensitive", "Colis sensibles"),
                    ("phone", "Téléphone"),
                ],
                max_length=20,
                null=True,
                verbose_name="Catégorie d'expédition (avion)",
            ),
        ),
    ]
