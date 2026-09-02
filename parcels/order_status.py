"""Dérive le statut global d'une commande à partir de ses colis."""
from __future__ import annotations

from .models import Order

_SHIPPED_PARCEL_STATUSES = frozenset({
    'in_transit',
    'out_for_delivery',
    'delivered',
})


def derive_order_status(order: Order) -> str:
    """
    Statut commande automatique :
    - annulée : inchangée (décision admin)
    - sans colis : en attente (devis / paiement)
    - tous colis livrés : livrée
    - au moins un colis en route ou livré : expédiée
    - sinon : en traitement (entrepôt, attente d'arrivée, groupé…)
    """
    if order.status == 'cancelled':
        return 'cancelled'

    parcel_statuses = list(order.parcels.values_list('status', flat=True))
    if not parcel_statuses:
        return 'pending'

    if all(status == 'delivered' for status in parcel_statuses):
        return 'delivered'

    if any(status in _SHIPPED_PARCEL_STATUSES for status in parcel_statuses):
        return 'shipped'

    return 'processing'


def sync_order_status(order: Order, *, save: bool = True) -> str:
    """Recalcule et enregistre le statut commande si nécessaire."""
    new_status = derive_order_status(order)
    if order.status == new_status:
        return new_status
    if order.status == 'cancelled':
        return order.status
    order.status = new_status
    if save:
        order.save(update_fields=['status'])
    return new_status


def sync_order_status_by_id(order_id: int) -> str | None:
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return None
    return sync_order_status(order)
