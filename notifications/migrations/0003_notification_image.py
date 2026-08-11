from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_alter_fcmdevice_options_alter_notification_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='notifications/',
                verbose_name='Image / annonce',
            ),
        ),
    ]
