from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0004_expense_clients_m2m'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='entry_type',
            field=models.CharField(
                choices=[('expense', 'Dépense'), ('loss', 'Perte')],
                db_index=True,
                default='expense',
                max_length=20,
                verbose_name='Type',
            ),
        ),
    ]
