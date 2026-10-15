import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0005_expense_entry_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('body', models.TextField(verbose_name='Message')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='support_threads',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Client',
                )),
                ('sender', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='support_messages_sent',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Expéditeur',
                )),
            ],
            options={
                'verbose_name': 'Message support',
                'verbose_name_plural': 'Messages support',
                'ordering': ['created_at'],
            },
        ),
    ]
