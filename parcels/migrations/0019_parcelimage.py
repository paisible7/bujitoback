from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0018_parcel_china_weight_shipmentbatch'),
    ]

    operations = [
        migrations.CreateModel(
            name='ParcelImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='parcels/', verbose_name='Image')),
                ('sort_order', models.PositiveSmallIntegerField(default=1, verbose_name='Ordre')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True, verbose_name="Date d'upload")),
                ('parcel', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='extra_images',
                    to='parcels.parcel',
                    verbose_name='Colis',
                )),
            ],
            options={
                'verbose_name': 'Image de colis',
                'verbose_name_plural': 'Images de colis',
                'ordering': ['sort_order', 'id'],
            },
        ),
    ]
