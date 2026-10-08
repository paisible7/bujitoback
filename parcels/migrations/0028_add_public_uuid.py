from django.db import migrations

from core.migration_helpers import add_public_uuid_field


MODELS = [
    'consolidation',
    'consolidationnoteimage',
    'consolidationparceldecision',
    'expeditionrequest',
    'importbatch',
    'order',
    'orderimage',
    'parcel',
    'parcelimage',
    'shipmentbatch',
]


class Migration(migrations.Migration):

    dependencies = [
        ('parcels', '0027_alter_expeditionrequest_loyalty_discount_usd_and_more'),
    ]

    operations = []
    for model_name in MODELS:
        operations.extend(add_public_uuid_field('parcels', model_name))
