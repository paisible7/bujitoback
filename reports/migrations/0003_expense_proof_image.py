from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0002_add_public_uuid'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='proof_image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='expenses/proofs/%Y/%m/',
                verbose_name='Preuve (reçu / capture)',
            ),
        ),
    ]
