from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0010_support_pins_and_voice'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportmessage',
            name='reply_to',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='replies',
                to='reports.supportmessage',
                verbose_name='Réponse à',
            ),
        ),
    ]
