from __future__ import annotations

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from notifications.utils import send_fcm_notification

from .models import Parcel, Order


@receiver(pre_save, sender=Parcel)
def _parcel_pre_save(sender, instance: Parcel, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    try:
        old = Parcel.objects.only("status").get(pk=instance.pk)
        instance._old_status = old.status
    except Parcel.DoesNotExist:
        instance._old_status = None


@receiver(post_save, sender=Parcel)
def _parcel_post_save(sender, instance: Parcel, created: bool, **kwargs):
    order = instance.order
    user = getattr(order, "user", None)
    if user is None:
        return

    old_status = getattr(instance, "_old_status", None)
    if not created and old_status == instance.status:
        return

    tracking = instance.tracking_number or str(instance.pk)
    title = "Mise a jour colis"
    body = f"Votre colis {tracking} est maintenant: {instance.get_status_display()}"
    send_fcm_notification(
        user,
        title,
        body,
        type="parcel",
        reference_id=instance.pk,
        data={"type": "parcel", "reference_id": instance.pk},
    )


@receiver(pre_save, sender=Order)
def _order_pre_save(sender, instance: Order, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    try:
        old = Order.objects.only("status").get(pk=instance.pk)
        instance._old_status = old.status
    except Order.DoesNotExist:
        instance._old_status = None


@receiver(post_save, sender=Order)
def _order_post_save(sender, instance: Order, created: bool, **kwargs):
    user = instance.user
    old_status = getattr(instance, "_old_status", None)
    if not created and old_status == instance.status:
        return

    title = "Mise a jour commande"
    body = f"Votre commande #{instance.pk} est maintenant: {instance.get_status_display()}"
    send_fcm_notification(
        user,
        title,
        body,
        type="order",
        reference_id=instance.pk,
        data={"type": "order", "reference_id": instance.pk},
    )

