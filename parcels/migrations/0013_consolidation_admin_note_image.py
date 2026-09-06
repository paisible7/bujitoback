from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0012_orderimage_package_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='consolidation',
            name='admin_note_image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='consolidations/',
                verbose_name='Photo note admin (groupage)',
            ),
        ),
    ]
