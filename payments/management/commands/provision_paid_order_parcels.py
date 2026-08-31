from django.core.management.base import BaseCommand

from parcels.fulfillment import provision_order_parcels
from payments.models import Payment


class Command(BaseCommand):
    help = (
        "Prévisualise ou génère les colis manquants pour les anciennes "
        "commandes dont le paiement est confirmé."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Applique réellement la génération (sinon mode aperçu).",
        )
        parser.add_argument(
            "--include-existing",
            action="store_true",
            help=(
                "Traite aussi les commandes ayant d'anciens colis sans "
                "numéro de séquence."
            ),
        )
        parser.add_argument(
            "--notify",
            action="store_true",
            help="Notifie les clients et les admins pour les colis créés.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        include_existing = options["include_existing"]
        should_notify = options["notify"]

        payments = (
            Payment.objects.filter(
                status="completed",
                order__isnull=False,
                order__quote_ready=True,
            )
            .select_related("order")
            .order_by("order_id", "-updated_at")
        )

        seen_order_ids = set()
        eligible_order_ids = []
        skipped = 0
        for payment in payments:
            order = payment.order
            if order.pk in seen_order_ids:
                continue
            seen_order_ids.add(order.pk)
            if payment.amount != order.total_amount:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Commande #{order.pk} ignorée : montant du paiement différent."
                    )
                )
                continue
            has_legacy_parcels = order.parcels.filter(
                order_sequence__isnull=True,
            ).exists()
            if has_legacy_parcels and not include_existing:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Commande #{order.pk} ignorée : colis historiques présents "
                        "(utilisez --include-existing après vérification)."
                    )
                )
                continue
            eligible_order_ids.append(order.pk)

        mode = "APPLICATION" if apply_changes else "APERÇU"
        self.stdout.write(
            f"{mode} : {len(eligible_order_ids)} commande(s) éligible(s), "
            f"{skipped} ignorée(s)."
        )

        if not apply_changes:
            for order_id in eligible_order_ids:
                self.stdout.write(f"  - Commande #{order_id}")
            self.stdout.write("Relancez avec --apply pour créer les colis.")
            return

        total_created = 0
        for order_id in eligible_order_ids:
            result = provision_order_parcels(
                order_id,
                notify=should_notify,
            )
            total_created += result.created_count
            self.stdout.write(
                f"Commande #{order_id} : {result.created_count} colis créé(s)."
            )

        self.stdout.write(
            self.style.SUCCESS(f"Terminé : {total_created} colis créé(s).")
        )
