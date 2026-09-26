from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0024_expedition_express_category'),
    ]

    operations = [
        migrations.AlterField(
            model_name='parcel',
            name='warehouse_number',
            field=models.CharField(
                blank=True,
                help_text="Emplacement physique dans l'entrepôt (ex. étagère 1).",
                max_length=100,
                null=True,
                verbose_name='Emplacement entrepôt',
            ),
        ),
    ]
