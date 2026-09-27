from __future__ import annotations

import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from notifications.utils import notify_admins, send_fcm_notification

from .models import Consolidation, Order, Parcel
from .order_status import sync_order_status_by_id

logger = logging.getLogger(__name__)


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

    if getattr(instance, "_client_edited", False):
        client_name = (user.full_name or instance.client_name or user.email).strip()
        notify_admins(
            "Commande modifiée",
            (
                f"{client_name} ({user.email}) a modifié la commande "
                f"#{instance.pk}. Un nouveau devis est requis."
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
            "Commande mise à jour",
            (
                f"Votre commande #{instance.pk} a été mise à jour. "
                "Un nouveau devis vous sera envoyé."
            ),
            type="order",
            reference_id=instance.pk,
            data={"type": "order", "reference_id": instance.pk, "action": "edited"},
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
    # La notif "nouvelle demande" est envoyée dans ParcelGroupView après
    # parcels.set() — sinon post_save voit 0 colis (M2M pas encore lié).
    if created:
        return

    from django.db import transaction

    consolidation_id = instance.pk
    user_id = instance.user_id
    client_edited = bool(getattr(instance, "_client_edited", False))
    old_status = getattr(instance, "_old_status", None)
    new_status = instance.status

    def _notify():
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            group = Consolidation.objects.prefetch_related(
                'parcels', 'parcel_decisions'
            ).get(pk=consolidation_id)
            user = User.objects.get(pk=user_id)
        except Exception:
            logger.exception(
                "consolidation notify: group/user introuvable id=%s",
                consolidation_id,
            )
            return

        if client_edited:
            parcel_count = group.parcels.count()
            note = (group.client_note or "").strip()
            admin_body = (
                f"{user.email} a modifié le groupage #{group.pk} "
                f"({parcel_count} colis). Un nouveau devis poids/frais est requis."
            )
            if note:
                admin_body = f"{admin_body} Description: {note}"
            notify_admins(
                "Groupage modifié",
                admin_body,
                type="consolidation",
                reference_id=group.pk,
                data={
                    "type": "consolidation",
                    "reference_id": group.pk,
                    "action": "quote",
                },
            )
            send_fcm_notification(
                user,
                "Groupage mis a jour",
                (
                    f"Votre groupage #{group.pk} a ete mis a jour. "
                    "Un nouveau devis poids/frais vous sera propose."
                ),
                type="consolidation",
                reference_id=group.pk,
                data={
                    "type": "consolidation",
                    "reference_id": group.pk,
                    "action": "edited",
                },
            )
            return

        if old_status == new_status:
            return

        if new_status == "completed":
            note = (group.admin_note or "").strip()
            decisions = {
                d.parcel_id: d.decision
                for d in group.parcel_decisions.all()
            }
            accepted = []
            for p in group.parcels.all():
                if decisions.get(p.id, "accepted") == "rejected":
                    continue
                accepted.append(p.tracking_number or str(p.pk))
            tracking_list = ", ".join(accepted) if accepted else "—"
            body = (
                f"Votre groupage #{group.pk} a ete accepte. "
                f"Colis groups: {tracking_list}."
            )
            if note:
                body = f"{body} Note: {note}"
            note_image = None
            if group.admin_note_image:
                note_image = group.admin_note_image
            else:
                first = group.note_images.order_by('id').first()
                if first is not None:
                    note_image = first.image
            try:
                send_fcm_notification(
                    user,
                    "Groupage accepte",
                    body,
                    type="consolidation",
                    reference_id=group.pk,
                    image=note_image if note_image else None,
                    data={
                        "type": "consolidation",
                        "reference_id": group.pk,
                        "status": "completed",
                        "admin_note": note,
                    },
                )
            except Exception:
                logger.exception(
                    "Échec notif acceptation groupage #%s", group.pk
                )
        elif new_status == "cancelled":
            note = (group.admin_note or "").strip()
            body = f"Votre demande de groupage #{group.pk} a ete refusee."
            if note:
                body = f"{body} Note: {note}"
            send_fcm_notification(
                user,
                "Groupage refuse",
                body,
                type="consolidation",
                reference_id=group.pk,
                data={
                    "type": "consolidation",
                    "reference_id": group.pk,
                    "status": "cancelled",
                    "admin_note": note,
                },
            )
        elif new_status == "processing":
            send_fcm_notification(
                user,
                "Groupage en cours",
                f"Votre groupage #{group.pk} est en cours de preparation.",
                type="consolidation",
                reference_id=group.pk,
                data={
                    "type": "consolidation",
                    "reference_id": group.pk,
                    "status": "processing",
                },
            )

    transaction.on_commit(_notify)
