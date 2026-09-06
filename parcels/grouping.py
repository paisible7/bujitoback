"""Helpers groupage : statut partagé entre colis d'un même groupage accepté."""
from __future__ import annotations

from .models import Consolidation, Parcel


def completed_group_for_parcel(parcel: Parcel) -> Consolidation | None:
    return (
        parcel.consolidations.filter(status='completed')
        .order_by('-request_date')
        .first()
    )


def sync_completed_group_parcel_status(parcel: Parcel) -> None:
    """Aligne le statut de tous les colis du groupage accepté sur celui de [parcel]."""
    group = completed_group_for_parcel(parcel)
    if group is None:
        return

    new_status = parcel.status
    siblings = group.parcels.exclude(pk=parcel.pk).exclude(status=new_status)
    for sibling in siblings:
        sibling.status = new_status
        sibling.save(update_fields=['status', 'last_updated'])
