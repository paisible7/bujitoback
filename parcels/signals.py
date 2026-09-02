from __future__ import annotations

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from notifications.utils import notify_admins, send_fcm_notification

from .models import Consolidation, Order, Parcel
from .order_status import sync_order_status_by_id


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
    if instance.order_id:
        sync_order_status_by_id(instance.order_id)

    order = instance.order
    user = getattr(order, "user", None)
    if user is None:
        return

    old_status = getattr(instance, "_old_status", None)
    if not created and old_status == instance.status:
        return

    tracking = instance.tracking_number or str(instance.pk)
    if created and instance.status == "awaiting_arrival":
        # Le service de provisionnement envoie une notification récapitulative
        # avec tous les numéros de la commande.
        return
    if old_status == "awaiting_arrival" and instance.status == "pending":
        send_fcm_notification(
            user,
            "Colis arrivé à l'entrepôt",
            (
                f"Votre colis {tracking} a été réceptionné à l'entrepôt "
                "et peut maintenant être groupé."
            ),
            type="parcel",
            reference_id=instance.pk,
            data={
                "type": "parcel",
                "reference_id": instance.pk,
                "action": "arrived",
            },
        )
        return

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
        instance._old_quote_ready = False
        instance._old_total_amount = None
        instance._old_withdrawal_fee = None
        instance._old_commission_fee = None
        instance._old_product_links = None
        instance._old_expected_parcel_count = None
        return
    try:
        old = Order.objects.only(
            "status",
            "quote_ready",
            "total_amount",
            "withdrawal_fee",
            "commission_fee",
            "product_links",
            "expected_parcel_count",
        ).get(pk=instance.pk)
        instance._old_status = old.status
        instance._old_quote_ready = old.quote_ready
        instance._old_total_amount = old.total_amount
        instance._old_withdrawal_fee = old.withdrawal_fee
        instance._old_commission_fee = old.commission_fee
        instance._old_product_links = old.product_links
        instance._old_expected_parcel_count = old.expected_parcel_count
    except Order.DoesNotExist:
        instance._old_status = None
        instance._old_quote_ready = False
        instance._old_total_amount = None
        instance._old_withdrawal_fee = None
        instance._old_commission_fee = None
        instance._old_product_links = None
        instance._old_expected_parcel_count = None


@receiver(post_save, sender=Order)
def _order_post_save(sender, instance: Order, created: bool, **kwargs):
    user = instance.user

    if created:
        client_name = (user.full_name or instance.client_name or user.email).strip()
        notify_admins(
            "Nouvelle commande",
            (
                f"{client_name} ({user.email}) a envoyé la commande "
                f"#{instance.pk}. Un devis est à établir."
            ),
            type="order",
            reference_id=instance.pk,
            data={
                "type": "order",
                "reference_id": instance.pk,
                "action": "quote",
            },
        )
        send_fcm_notification(
            user,
            "Commande reçue",
            (
                f"Votre commande #{instance.pk} a bien été reçue. "
                "Vous serez notifié dès que le devis sera disponible."
            ),
            type="order",
            reference_id=instance.pk,
            data={"type": "order", "reference_id": instance.pk},
        )
        return

    old_status = getattr(instance, "_old_status", None)
    old_quote_ready = getattr(instance, "_old_quote_ready", False)
    old_total_amount = getattr(instance, "_old_total_amount", None)
    old_withdrawal_fee = getattr(instance, "_old_withdrawal_fee", None)
    old_commission_fee = getattr(instance, "_old_commission_fee", None)
    old_product_links = getattr(instance, "_old_product_links", None)
    old_expected_parcel_count = getattr(
        instance,
        "_old_expected_parcel_count",
        None,
    )
    quote_updated = instance.quote_ready and (
        not old_quote_ready
        or old_total_amount != instance.total_amount
        or old_withdrawal_fee != instance.withdrawal_fee
        or old_commission_fee != instance.commission_fee
        or old_product_links != instance.product_links
        or old_expected_parcel_count != instance.expected_parcel_count
    )

    if quote_updated:
        send_fcm_notification(
            user,
            "Devis disponible",
            (
                f"Le devis de votre commande #{instance.pk} est prêt. "
                f"Montant total : {instance.total_amount:.2f} USD."
            ),
            type="order",
            reference_id=instance.pk,
            data={
                "type": "order",
                "reference_id": instance.pk,
                "action": "quote_ready",
            },
        )
        return

    if old_status == instance.status:
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


@receiver(pre_save, sender=Consolidation)
def _consolidation_pre_save(sender, instance: Consolidation, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    try:
        old = Consolidation.objects.only("status").get(pk=instance.pk)
        instance._old_status = old.status
    except Consolidation.DoesNotExist:
        instance._old_status = None


@receiver(post_save, sender=Consolidation)
def _consolidation_post_save(sender, instance: Consolidation, created: bool, **kwargs):
    user = instance.user
    parcel_count = instance.parcels.count()

    if created:
        notify_admins(
            "Nouvelle demande de groupage",
            f"{user.email} demande le groupage de {parcel_count} colis (#{instance.pk}).",
            type="consolidation",
            reference_id=instance.pk,
            data={"type": "consolidation", "reference_id": instance.pk},
        )
        send_fcm_notification(
            user,
            "Demande de groupage envoyee",
            f"Votre demande de groupage #{instance.pk} ({parcel_count} colis) est en attente de validation.",
            type="consolidation",
            reference_id=instance.pk,
            data={"type": "consolidation", "reference_id": instance.pk},
        )
        return

    old_status = getattr(instance, "_old_status", None)
    if old_status == instance.status:
        return

    if instance.status == "completed":
        note = (instance.admin_note or "").strip()
        decisions = {
            d.parcel_id: d.decision
            for d in instance.parcel_decisions.all()
        }
        accepted = []
        for p in instance.parcels.all():
            if decisions.get(p.id, "accepted") == "rejected":
                continue
            accepted.append(p.tracking_number or str(p.pk))
        tracking_list = ", ".join(accepted) if accepted else "—"
        body = (
            f"Votre groupage #{instance.pk} a ete accepte. "
            f"Colis groups: {tracking_list}."
        )
        if note:
            body = f"{body} Note: {note}"
        send_fcm_notification(
            user,
            "Groupage accepte",
            body,
            type="consolidation",
            reference_id=instance.pk,
            data={
                "type": "consolidation",
                "reference_id": instance.pk,
                "status": "completed",
                "admin_note": note,
            },
        )
    elif instance.status == "cancelled":
        note = (instance.admin_note or "").strip()
        body = f"Votre demande de groupage #{instance.pk} a ete refusee."
        if note:
            body = f"{body} Note: {note}"
        send_fcm_notification(
            user,
            "Groupage refuse",
            body,
            type="consolidation",
            reference_id=instance.pk,
            data={
                "type": "consolidation",
                "reference_id": instance.pk,
                "status": "cancelled",
                "admin_note": note,
            },
        )
    elif instance.status == "processing":
        send_fcm_notification(
            user,
            "Groupage en cours",
            f"Votre groupage #{instance.pk} est en cours de preparation.",
            type="consolidation",
            reference_id=instance.pk,
            data={"type": "consolidation", "reference_id": instance.pk, "status": "processing"},
        )
