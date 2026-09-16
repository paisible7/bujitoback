"""Helpers d'appartenance colis / client (commande OU téléphone)."""
from __future__ import annotations


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def user_owns_parcel(user, parcel) -> bool:
    """
    Un colis appartient au client si :
    - lié à une commande de ce user, OU
    - le téléphone client du colis correspond au téléphone du compte.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if parcel.order_id and getattr(parcel, "order", None) is not None:
        if parcel.order.user_id == user.id:
            return True
    user_phone = _digits(getattr(user, "phone_number", None))
    parcel_phone = _digits(getattr(parcel, "client_phone", None))
    if user_phone and parcel_phone:
        if user_phone == parcel_phone:
            return True
        # Tolérance préfixe pays (ex. 243… vs local)
        if user_phone.endswith(parcel_phone) or parcel_phone.endswith(user_phone):
            if min(len(user_phone), len(parcel_phone)) >= 8:
                return True
    return False


def parcels_for_user_q(user):
    """Filtre ORM pour les colis visibles / actionnables par un client."""
    from django.db.models import Q

    from .models import Parcel  # noqa: F401 — typage doc

    q = Q(order__user=user)
    phone = _digits(getattr(user, "phone_number", None))
    if phone and len(phone) >= 8:
        # Match souple : le champ texte contient la séquence de chiffres
        # (les espaces/+ du stockage sont gérés côté Python à l'écriture ;
        # ici on matche les derniers chiffres significatifs).
        tail = phone[-9:] if len(phone) > 9 else phone
        q |= Q(client_phone__icontains=tail)
    return q
