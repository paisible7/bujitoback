from django.conf import settings
from django.db import migrations, models


def copy_client_to_clients(apps, schema_editor):
    Expense = apps.get_model('reports', 'Expense')
    for expense in Expense.objects.exclude(client_id=None).iterator():
        expense.clients.add(expense.client_id)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0003_expense_proof_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='clients',
            field=models.ManyToManyField(
                blank=True,
                related_name='accounting_expenses',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Clients concernés',
            ),
        ),
        migrations.RunPython(copy_client_to_clients, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='expense',
            name='client',
        ),
    ]
