from django.db import migrations


def clear_advertisements(apps, schema_editor):
    """Supprime les affiches seed / en dur pour laisser l'interface vide."""
    Advertisement = apps.get_model('ads', 'Advertisement')
    # Efface aussi les fichiers media liés si possible.
    for ad in Advertisement.objects.all():
        image = getattr(ad, 'image', None)
        if image:
            try:
                image.delete(save=False)
            except Exception:
                pass
    Advertisement.objects.all().delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0003_advertisement_schedule'),
    ]

    operations = [
        migrations.RunPython(clear_advertisements, noop),
    ]
