from django.db import migrations, models


def forwards_roles(apps, schema_editor):
    CustomUser = apps.get_model('users', 'CustomUser')
    # Ancien rôle "user" → client
    CustomUser.objects.filter(role='user').update(role='client')
    # Comptes Django superuser → rôle superuser
    CustomUser.objects.filter(is_superuser=True).update(
        role='superuser',
        is_staff=True,
    )
    # Admins app : pas d'accès Django admin
    CustomUser.objects.filter(role='admin').update(
        is_staff=False,
        is_superuser=False,
    )
    # Clients : flags staff/superuser à False
    CustomUser.objects.filter(role='client').update(
        is_staff=False,
        is_superuser=False,
    )


def backwards_roles(apps, schema_editor):
    CustomUser = apps.get_model('users', 'CustomUser')
    CustomUser.objects.filter(role='client').update(role='user')
    CustomUser.objects.filter(role='superuser').update(role='admin')


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_customuser_language'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('client', 'Client'),
                    ('admin', 'Admin'),
                    ('superuser', 'Superuser'),
                ],
                default='client',
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards_roles, backwards_roles),
    ]
