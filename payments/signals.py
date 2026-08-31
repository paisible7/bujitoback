from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Payment

logger = logging.getLogger(__name__)


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
    if instance.status != "completed" or instance.order_id is None:
        return
    if getattr(instance, "_old_status", None) == "completed":
        return

    order = instance.order
    if (
        not order.quote_ready
        or order.total_amount <= 0
        or instance.amount != order.total_amount
    ):
        logger.warning(
            "Payment %s completed but order %s is not fulfillable "
            "(quote_ready=%s, payment=%s, total=%s).",
            instance.pk,
            order.pk,
            order.quote_ready,
            instance.amount,
            order.total_amount,
        )
        return

    order_id = instance.order_id

    def provision() -> None:
        from parcels.fulfillment import provision_order_parcels

        provision_order_parcels(order_id)

    transaction.on_commit(provision, robust=True)
