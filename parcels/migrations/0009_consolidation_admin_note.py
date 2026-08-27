from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0008_order_quote_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='consolidation',
            name='admin_note',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Note admin (groupage)',
            ),
        ),
    ]
