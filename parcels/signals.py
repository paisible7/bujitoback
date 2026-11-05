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
        instance._old_description = None
        return
    try:
        old = Parcel.objects.only("status", "description").get(pk=instance.pk)
        instance._old_status = old.status
        instance._old_description = old.description
    except Parcel.DoesNotExist:
        instance._old_status = None
        instance._old_description = None


def _parcel_content_label(parcel: Parcel) -> str:
    raw = (parcel.description or "").strip()
    return raw if raw else "non précisé"


def _notify_client_parcel_content(
    parcel: Parcel,
    *,
    title: str,
    intro: str,
    action: str,
    user=None,
) -> None:
    """Notifie le client du contenu enregistré + invitation à faire corriger."""
    from .ownership import resolve_parcel_owner

    tracking = parcel.tracking_number or str(parcel.pk)
    owner = user or resolve_parcel_owner(parcel)
    if owner is None:
        return
    content = _parcel_content_label(parcel)
    extras = []
    if parcel.weight_kg is not None and parcel.weight_kg > 0:
        extras.append(f"poids {parcel.weight_kg} kg")
    if parcel.volume_cbm is not None and parcel.volume_cbm > 0:
        extras.append(f"volume {parcel.volume_cbm} m³")
    extras_txt = f" ({', '.join(extras)})" if extras else ""
    body = (
        f"{intro} Contenu enregistré : {content}{extras_txt}. "
        "Si ce n'est pas exact, ouvrez le suivi du colis et demandez "
        "une modification au support."
    )
    try:
        send_fcm_notification(
            owner,
            title,
            body,
            type="parcel",
            reference_id=parcel.pk,
            data={
                "type": "parcel",
                "reference_id": str(parcel.pk),
                "action": action,
                "tracking_number": tracking,
                "description": content,
            },
            translate=False,
        )
    except Exception:
        logger.exception(
            "Échec notification client contenu colis %s (%s)",
            parcel.pk,
            action,
        )


def _notify_warehouse_arrival(parcel: Parcel, *, user=None) -> None:
    """Notifie client (si connu) + admins de l'arrivée entrepôt."""
    from .ownership import resolve_parcel_owner

    tracking = parcel.tracking_number or str(parcel.pk)
    owner = user or resolve_parcel_owner(parcel)
    client_label = (
        (getattr(owner, "email", None) if owner is not None else None)
        or (getattr(owner, "full_name", None) if owner is not None else None)
        or (parcel.client_name or "").strip()
        or (parcel.client_phone or "").strip()
        or "—"
    )
    if owner is not None:
        _notify_client_parcel_content(
            parcel,
            title="Colis arrivé à l'entrepôt",
            intro=(
                f"Votre colis {tracking} a été réceptionné à l'entrepôt "
                "et peut maintenant être groupé."
            ),
            action="arrived",
            user=owner,
        )
    try:
        notify_admins(
            "Colis arrivé à l'entrepôt",
            f"Colis {tracking} ({client_label}) réceptionné à l'entrepôt.",
            type="parcel",
            reference_id=parcel.pk,
            data={
                "type": "parcel",
                "reference_id": str(parcel.pk),
                "action": "arrived",
                "tracking_number": tracking,
            },
        )
    except Exception:
        logger.exception(
            "Échec notification admin arrivée entrepôt colis %s",
            parcel.pk,
        )


@receiver(post_save, sender=Parcel)
def _parcel_post_save(sender, instance: Parcel, created: bool, **kwargs):
    from .ownership import resolve_parcel_owner

    if instance.order_id:
        sync_order_status_by_id(instance.order_id)

    old_status = getattr(instance, "_old_status", None)
    old_description = getattr(instance, "_old_description", None)
    new_description = (instance.description or "").strip()
    old_description_norm = (old_description or "").strip()
    description_changed = (
        not created and old_description_norm != new_description and bool(new_description)
    )
    status_changed = created or old_status != instance.status

    if not created and not status_changed and not description_changed:
        return

    tracking = instance.tracking_number or str(instance.pk)
    if created and instance.status == "awaiting_arrival":
        # Le service de provisionnement envoie une notification récapitulative
        # avec tous les numéros de la commande.
        return

    # Arrivée dépôt : transition attendue, ou création déjà « arrivé ».
    is_arrival = (
        old_status == "awaiting_arrival" and instance.status == "pending"
    ) or (created and instance.status == "pending")
    if is_arrival:
        _notify_warehouse_arrival(instance)
        return

    if description_changed:
        _notify_client_parcel_content(
            instance,
            title="Contenu du colis mis à jour",
            intro=f"Le contenu de votre colis {tracking} a été modifié.",
            action="content_updated",
        )

    if not status_changed:
        return

    user = resolve_parcel_owner(instance)
    if user is None:
        return

    title = "Mise a jour colis"
    body = f"Votre colis {tracking} est maintenant: {instance.get_status_display()}"
    send_fcm_notification(
        user,
        title,
        body,
        type="parcel",
        reference_id=instance.pk,
        data={
            "type": "parcel",
            "reference_id": str(instance.pk),
            "tracking_number": tracking,
        },
        translate=False,
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


def _consolidation_ref_id(group: Consolidation):
    """Préfère l’UUID public (aligné avec l’API Flutter)."""
    return str(getattr(group, "uuid", None) or group.pk)


@receiver(pre_save, sender=Consolidation)
def _consolidation_pre_save(sender, instance: Consolidation, **kwargs):
    if not instance.pk:
        instance._old_status = None
        instance._old_weight_kg = None
        instance._old_billable_weight_kg = None
        instance._old_grouping_fee = None
        instance._old_admin_note = None
        return
    try:
        old = Consolidation.objects.only(
            "status",
            "weight_kg",
            "billable_weight_kg",
            "grouping_fee",
            "admin_note",
        ).get(pk=instance.pk)
        instance._old_status = old.status
        instance._old_weight_kg = old.weight_kg
        instance._old_billable_weight_kg = old.billable_weight_kg
        instance._old_grouping_fee = old.grouping_fee
        instance._old_admin_note = old.admin_note
    except Consolidation.DoesNotExist:
        instance._old_status = None
        instance._old_weight_kg = None
        instance._old_billable_weight_kg = None
        instance._old_grouping_fee = None
        instance._old_admin_note = None


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
    old_weight_kg = getattr(instance, "_old_weight_kg", None)
    old_billable_weight_kg = getattr(instance, "_old_billable_weight_kg", None)
    old_grouping_fee = getattr(instance, "_old_grouping_fee", None)
    old_admin_note = getattr(instance, "_old_admin_note", None)

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

        ref_id = _consolidation_ref_id(group)

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
                reference_id=ref_id,
                data={
                    "type": "consolidation",
                    "reference_id": ref_id,
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
                reference_id=ref_id,
                data={
                    "type": "consolidation",
                    "reference_id": ref_id,
                    "action": "edited",
                },
            )
            return

        # Devis admin (poids / frais) sans changement de statut — comme les commandes.
        # Si le statut change aussi (accept/refus), on envoie seulement la notif de statut.
        quote_updated = (
            group.weight_kg != old_weight_kg
            or group.billable_weight_kg != old_billable_weight_kg
            or group.grouping_fee != old_grouping_fee
        )
        has_quote = group.weight_kg is not None or group.grouping_fee is not None
        if quote_updated and has_quote and old_status == new_status:
            fee = group.grouping_fee
            weight = group.billable_weight_kg or group.weight_kg
            parts = [f"Le devis de votre groupage #{group.pk} est pret."]
            if weight is not None:
                parts.append(f"Poids : {weight} kg.")
            if fee is not None:
                parts.append(f"Frais de groupage : {fee} USD.")
            note = (group.admin_note or "").strip()
            if note and note != (old_admin_note or "").strip():
                parts.append(f"Note : {note}")
            try:
                send_fcm_notification(
                    user,
                    "Devis groupage disponible",
                    " ".join(parts),
                    type="consolidation",
                    reference_id=ref_id,
                    data={
                        "type": "consolidation",
                        "reference_id": ref_id,
                        "action": "quote_ready",
                    },
                )
            except Exception:
                logger.exception(
                    "Échec notif devis groupage #%s", group.pk
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
                    reference_id=ref_id,
                    image=note_image if note_image else None,
                    data={
                        "type": "consolidation",
                        "reference_id": ref_id,
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
                reference_id=ref_id,
                data={
                    "type": "consolidation",
                    "reference_id": ref_id,
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
                reference_id=ref_id,
                data={
                    "type": "consolidation",
                    "reference_id": ref_id,
                    "status": "processing",
                },
            )

    transaction.on_commit(_notify)
