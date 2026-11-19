from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from notifications.utils import notify_admins, send_fcm_notification

from .models import Order, Parcel
from .order_status import sync_order_status


@dataclass(frozen=True)
class ProvisioningResult:
    parcels: tuple[Parcel, ...]
    created_count: int


def _notify_provisioning(
    *,
    order_id: int,
    user_id: int,
    user_email: str,
    created_count: int,
) -> None:
    from users.models import CustomUser

    user = CustomUser.objects.filter(pk=user_id).first()
    if user is None:
        return

    send_fcm_notification(
        user,
        "Paiement confirmé",
        (
            f"Votre paiement pour la commande #{order_id} est confirmé. "
            f"{created_count} colis sont en attente d'arrivée à l'entrepôt."
        ),
        type="order",
        reference_id=order_id,
        data={
            "type": "order",
            "reference_id": order_id,
            "action": "parcels_created",
        },
    )
    notify_admins(
        "Colis créés après paiement",
        (
            f"{created_count} colis placeholder ont été créés pour la commande "
            f"#{order_id} de {user_email} (sans n° de suivi — à attribuer à l'arrivée)."
        ),
        type="order",
        reference_id=order_id,
        data={
            "type": "order",
            "reference_id": order_id,
            "action": "parcels_created",
        },
    )


def provision_order_parcels(
    order_id: int,
    *,
    notify: bool = True,
) -> ProvisioningResult:
    """
    Crée les colis attendus d'une commande payée.

    Le verrou sur la commande et la contrainte (order, order_sequence)
    rendent la fonction sûre face aux webhooks répétés ou concurrents.
    """
    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .select_related("user")
            .get(pk=order_id)
        )
        expected_count = int(order.expected_parcel_count or 1)
        if expected_count < 1 or expected_count > 100:
            raise ValueError("Le nombre de colis prévus doit être compris entre 1 et 100.")

        existing_by_sequence = {
            parcel.order_sequence: parcel
            for parcel in order.parcels.filter(order_sequence__isnull=False)
        }
        parcels: list[Parcel] = []
        created_count = 0

        for sequence in range(1, expected_count + 1):
            parcel = existing_by_sequence.get(sequence)
            if parcel is None:
                # Pas de n° de suivi auto : attribué à l'arrivée / import / saisie admin.
                parcel = Parcel.objects.create(
                    order=order,
                    order_sequence=sequence,
                    tracking_number=None,
                    status="awaiting_arrival",
                    current_location="En attente d'arrivée à l'entrepôt",
                    client_name=order.client_name or order.user.full_name or order.user.email,
                    client_phone=order.client_phone or order.user.phone_number,
                    description=f"Colis prévu {sequence}/{expected_count} — commande #{order.pk}",
                )
                created_count += 1
            parcels.append(parcel)

        sync_order_status(order)

        if created_count and notify:
            notify_count = created_count
            transaction.on_commit(
                lambda: _notify_provisioning(
                    order_id=order.pk,
                    user_id=order.user_id,
                    user_email=order.user.email,
                    created_count=notify_count,
                ),
                robust=True,
            )

    return ProvisioningResult(
        parcels=tuple(parcels),
        created_count=created_count,
    )
