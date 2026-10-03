from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_customuser_admin_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='profile_photo',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='users/avatars/%Y/%m/',
                verbose_name='Photo de profil',
            ),
        ),
    ]
