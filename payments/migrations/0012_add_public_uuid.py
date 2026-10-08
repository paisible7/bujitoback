from django.db import migrations

from core.migration_helpers import add_public_uuid_field


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0011_payment_qr_image'),
    ]

    operations = []
    for model_name in ('savedpaymentmethod', 'paymentmethod', 'payment'):
        operations.extend(add_public_uuid_field('payments', model_name))
