from django.core.management.base import BaseCommand

from parcels.models import Order
from parcels.order_status import sync_order_status


class Command(BaseCommand):
    help = "Recalcule le statut de chaque commande à partir de ses colis."

    def handle(self, *args, **options):
        updated = 0
        for order in Order.objects.all().iterator(chunk_size=100):
            before = order.status
            after = sync_order_status(order)
            if before != after:
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(f'Statuts recalculés : {updated} commande(s) mise(s) à jour.')
        )
