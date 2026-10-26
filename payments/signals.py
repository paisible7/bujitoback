from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Payment

logger = logging.getLogger(__name__)


def _payment_service_amount(payment: Payment) -> Decimal:
    """Montant service (hors frais gateway) pour valider une commande."""
    meta = payment.provider_raw_response
    if isinstance(meta, dict):
        raw = meta.get("service_amount")
        if raw is not None:
            try:
                return Decimal(str(raw))
            except (InvalidOperation, TypeError, ValueError):
                pass
    return payment.amount


@receiver(pre_save, sender=Payment)
def _payment_pre_save(sender, instance: Payment, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    try:
        instance._old_status = Payment.objects.only("status").get(
            pk=instance.pk,
        ).status
    except Payment.DoesNotExist:
        instance._old_status = None


@receiver(post_save, sender=Payment)
def _payment_post_save(sender, instance: Payment, created: bool, **kwargs):
    if instance.status != "completed":
        return
    if getattr(instance, "_old_status", None) == "completed":
        return

    # Expédition payée → marquer paid (éligible MCO si Bujito Digital)
    if instance.expedition_id is not None:
        expedition_id = instance.expedition_id
        payment_pk = instance.pk
        payment_amount = instance.amount

        def mark_expedition() -> None:
            from django.utils import timezone
            from notifications.utils import notify_admins, send_fcm_notification
            from parcels.models import ExpeditionRequest

            exp = (
                ExpeditionRequest.objects.select_related("user")
                .filter(pk=expedition_id, status="awaiting_payment")
                .first()
            )
            if exp is None:
                logger.info(
                    "Payment %s completed but expedition %s was not awaiting payment.",
                    payment_pk,
                    expedition_id,
                )
                return
            exp.status = "paid"
            exp.paid_at = timezone.now()
            exp.save(update_fields=["status", "paid_at"])
            trackings = ", ".join(
                exp.parcels.values_list("tracking_number", flat=True)[:5]
            )
            carrier = (
                "autre transitaire"
                if exp.mode == "other_forwarder"
                else "Bujito Digital"
            )
            try:
                notify_admins(
                    "Expédition payée",
                    f"Paiement #{payment_pk} — expédition #{exp.pk} "
                    f"({carrier}) : ${payment_amount}. "
                    f"Client {getattr(exp.user, 'email', '')}. "
                    f"Colis : {trackings or '—'}.",
                    type="payment",
                    reference_id=payment_pk,
                    data={
                        "type": "expedition",
                        "expedition_id": str(exp.pk),
                        "payment_id": str(payment_pk),
                        "mode": exp.mode,
                        "status": "paid",
                    },
                )
                if exp.user_id:
                    send_fcm_notification(
                        exp.user,
                        "Paiement expédition confirmé",
                        f"Votre paiement de ${payment_amount} pour "
                        f"l'expédition #{exp.pk} ({carrier}) est confirmé.",
                        type="payment",
                        reference_id=payment_pk,
                        data={
                            "type": "expedition",
                            "expedition_id": str(exp.pk),
                            "payment_id": str(payment_pk),
                            "mode": exp.mode,
                            "status": "paid",
                        },
                        translate=False,
                    )
            except Exception:
                logger.exception(
                    "Échec notification après paiement expédition #%s",
                    expedition_id,
                )

        transaction.on_commit(mark_expedition, robust=True)
        return

    if instance.order_id is None:
        return

    order = instance.order
    service_amount = _payment_service_amount(instance)
    if (
        not order.quote_ready
        or order.total_amount <= 0
        or service_amount != order.total_amount
    ):
        logger.warning(
            "Payment %s completed but order %s is not fulfillable "
            "(quote_ready=%s, payment=%s, service=%s, total=%s).",
            instance.pk,
            order.pk,
            order.quote_ready,
            instance.amount,
            service_amount,
            order.total_amount,
        )
        return

    order_id = instance.order_id

    def provision() -> None:
        from parcels.fulfillment import provision_order_parcels

        provision_order_parcels(order_id)

    transaction.on_commit(provision, robust=True)
