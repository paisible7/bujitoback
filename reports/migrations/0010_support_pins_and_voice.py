from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0009_support_quick_replies_and_auto_messages'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportmessage',
            name='is_pinned',
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name='Épinglé',
            ),
        ),
        migrations.AddField(
            model_name='supportmessage',
            name='pinned_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Épinglé le',
            ),
        ),
        migrations.CreateModel(
            name='SupportThreadMeta',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'is_pinned',
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        verbose_name='Conversation épinglée',
                    ),
                ),
                (
                    'pinned_at',
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name='Épinglée le',
                    ),
                ),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'client',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='support_thread_meta',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Client',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Méta conversation support',
                'verbose_name_plural': 'Métas conversations support',
            },
        ),
    ]
