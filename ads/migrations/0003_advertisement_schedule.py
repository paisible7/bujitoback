from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0002_advertisement_screens'),
    ]

    operations = [
        migrations.AddField(
            model_name='advertisement',
            name='starts_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Vide = immédiat',
                null=True,
                verbose_name="Début d'affichage",
            ),
        ),
        migrations.AddField(
            model_name='advertisement',
            name='ends_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Vide = pas de limite',
                null=True,
                verbose_name="Fin d'affichage",
            ),
        ),
    ]
