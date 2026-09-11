from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_user_roles_client_admin_superuser'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='city',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Ville'),
        ),
    ]
