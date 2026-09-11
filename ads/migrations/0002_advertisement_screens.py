from django.db import migrations, models


def set_default_screens(apps, schema_editor):
    Advertisement = apps.get_model('ads', 'Advertisement')
    for ad in Advertisement.objects.all():
        if not ad.screens:
            ad.screens = ['home']
            ad.save(update_fields=['screens'])


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='advertisement',
            name='screens',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Liste des clés d'écran : home, orders, grouping, tracking, profile",
                verbose_name='Écrans',
            ),
        ),
        migrations.RunPython(set_default_screens, migrations.RunPython.noop),
    ]
