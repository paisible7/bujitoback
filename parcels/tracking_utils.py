"""Génération de numéros de suivi Bujito."""
from __future__ import annotations

import uuid

from .models import Parcel


def _phone_digits(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def client_tracking_prefix(client_phone: str | None) -> str | None:
    """Préfixe client : BUJ + 4 derniers chiffres du téléphone."""
    digits = _phone_digits(client_phone)
    if len(digits) < 4:
        return None
    return f"BUJ{digits[-4:]}"


def generate_tracking_number(
    *,
    order_id: int | None = None,
    sequence: int | None = None,
    client_phone: str | None = None,
) -> str:
    """
    Génère un tracking unique.
    - Avec téléphone client (saisie admin) : BUJ{4 derniers chiffres}
      puis BUJ{4}-02, BUJ{4}-03… si collision.
    - Avec commande : BUJ-{orderId}-{seq}-{uuid8}
    - Sinon : BUJ-{uuid12}
    """
    prefix = client_tracking_prefix(client_phone)
    if prefix:
        if not Parcel.objects.filter(tracking_number=prefix).exists():
            return prefix
        for i in range(2, 1000):
            candidate = f"{prefix}-{i:02d}"
            if not Parcel.objects.filter(tracking_number=candidate).exists():
                return candidate
        raise RuntimeError("Impossible de générer un numéro de suivi unique.")

    for _ in range(20):
        short = uuid.uuid4().hex[:12].upper()
        if order_id is not None and sequence is not None:
            candidate = f"BUJ-{int(order_id):06d}-{int(sequence):02d}-{short[:8]}"
        else:
            candidate = f"BUJ-{short}"
        if not Parcel.objects.filter(tracking_number=candidate).exists():
            return candidate
    raise RuntimeError("Impossible de générer un numéro de suivi unique.")
