from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Advertisement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, default='', max_length=200, verbose_name='Titre')),
                ('image', models.ImageField(upload_to='ads/%Y/%m/', verbose_name='Image')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Ordre')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créée le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Mise à jour')),
            ],
            options={
                'verbose_name': 'Affiche publicitaire',
                'verbose_name_plural': 'Affiches publicitaires',
                'ordering': ['sort_order', '-created_at'],
            },
        ),
    ]
