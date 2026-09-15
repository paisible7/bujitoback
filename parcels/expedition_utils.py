"""Calculs de devis d'expédition (Bujito Digital / autre transitaire)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pricing.models import BusinessSettings
from pricing.utils import grouping_cost, shipping_cost

from .weight_utils import parse_weight_kg

ZERO = Decimal("0.00")
CBM_ADVANCE_RATIO = Decimal("0.50")


def _to_decimal(value) -> Decimal:
    if value is None or value == "":
        return ZERO
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def parcel_weight_kg(parcel) -> Decimal:
    if parcel.weight_kg is not None:
        return _to_decimal(parcel.weight_kg)
    parsed = parse_weight_kg(parcel.weight_volume)
    if parsed is not None:
        return _to_decimal(parsed)
    cons = (
        parcel.consolidations.filter(status="completed", weight_kg__isnull=False)
        .order_by("-request_date")
        .first()
    )
    if cons and cons.weight_kg is not None:
        count = max(cons.parcels.count(), 1)
        return (_to_decimal(cons.weight_kg) / count).quantize(Decimal("0.001"))
    return ZERO


def parcel_volume_cbm(parcel) -> Decimal:
    return _to_decimal(getattr(parcel, "volume_cbm", None))


def parcel_is_grouped(parcel) -> bool:
    return parcel.consolidations.filter(status="completed").exists()


def parcel_grouping_fee(parcel) -> Decimal | None:
    """Frais de groupage déjà fixé sur la consolidation completed, sinon None."""
    cons = (
        parcel.consolidations.filter(status="completed")
        .order_by("-request_date")
        .first()
    )
    if cons is None:
        return None
    if cons.grouping_fee is not None:
        return _to_decimal(cons.grouping_fee)
    if cons.weight_kg is not None:
        calc = grouping_cost(weight_kg=cons.weight_kg)
        return _to_decimal(calc["amount_usd"])
    return ZERO


def cbm_cost(*, volume_cbm, settings: BusinessSettings | None = None) -> dict[str, Any]:
    cfg = settings or BusinessSettings.load()
    vol = _to_decimal(volume_cbm)
    if vol <= 0:
        return {
            "volume_cbm": 0.0,
            "amount_usd": 0.0,
            "advance_usd": 0.0,
            "detail": "aucun CBM",
        }
    total = (vol * cfg.cbm_rate_usd).quantize(Decimal("0.01"))
    advance = (total * CBM_ADVANCE_RATIO).quantize(Decimal("0.01"))
    return {
        "volume_cbm": float(vol),
        "amount_usd": float(total),
        "advance_usd": float(advance),
        "detail": f"{vol} CBM × {cfg.cbm_rate_usd} $/m³ (acompte 50%)",
    }


def build_expedition_quote(
    *,
    parcels: list,
    mode: str,
    shipping_category: str | None = None,
    forwarder_delivery_fee=None,
    volume_cbm_override=None,
    weight_kg_override=None,
    settings: BusinessSettings | None = None,
) -> dict[str, Any]:
    """
    Calcule le devis d'expédition.
    total_due_now = frais applicables + 50% du CBM.
    """
    cfg = settings or BusinessSettings.load()
    mode = (mode or "").strip().lower()
    if mode not in {"bujito_digital", "other_forwarder"}:
        raise ValueError("mode invalide")

    if not parcels:
        raise ValueError("au moins un colis requis")

    weight = (
        _to_decimal(weight_kg_override)
        if weight_kg_override is not None
        else sum((parcel_weight_kg(p) for p in parcels), ZERO)
    )
    volume = (
        _to_decimal(volume_cbm_override)
        if volume_cbm_override is not None
        else sum((parcel_volume_cbm(p) for p in parcels), ZERO)
    )

    was_grouped = any(parcel_is_grouped(p) for p in parcels)
    grouping_fee = ZERO
    if was_grouped:
        # Une seule consolidation typique : prendre le fee du 1er colis groupé
        for p in parcels:
            fee = parcel_grouping_fee(p)
            if fee is not None:
                grouping_fee = fee
                break
        if grouping_fee <= 0 and weight > 0:
            grouping_fee = _to_decimal(grouping_cost(weight_kg=weight, settings=cfg)["amount_usd"])

    shipping_fee = ZERO
    category = None
    if mode == "bujito_digital":
        category = (shipping_category or "ordinary").strip().lower()
        if category not in {"ordinary", "sensitive", "phone"}:
            category = "ordinary"
        ship = shipping_cost(category=category, weight_kg=weight, settings=cfg)
        if not ship.get("available", True):
            raise ValueError(ship.get("message") or "catégorie indisponible")
        shipping_fee = _to_decimal(ship["amount_usd"])

    forwarder_fee = ZERO
    if mode == "other_forwarder":
        forwarder_fee = _to_decimal(forwarder_delivery_fee)
        if forwarder_fee < 0:
            raise ValueError("forwarder_delivery_fee invalide")

    cbm = cbm_cost(volume_cbm=volume, settings=cfg)
    cbm_fee = _to_decimal(cbm["amount_usd"])
    cbm_advance = _to_decimal(cbm["advance_usd"])

    if mode == "bujito_digital":
        base = (grouping_fee if was_grouped else ZERO) + shipping_fee
    else:
        base = (grouping_fee if was_grouped else ZERO) + forwarder_fee

    total_due_now = (base + cbm_advance).quantize(Decimal("0.01"))

    return {
        "mode": mode,
        "shipping_category": category,
        "was_grouped": was_grouped,
        "weight_kg": float(weight),
        "volume_cbm": float(volume),
        "grouping_fee": float(grouping_fee if was_grouped else ZERO),
        "shipping_fee": float(shipping_fee),
        "forwarder_delivery_fee": float(forwarder_fee),
        "cbm_fee": float(cbm_fee),
        "cbm_fee_advance": float(cbm_advance),
        "cbm_fee_remaining": float((cbm_fee - cbm_advance).quantize(Decimal("0.01"))),
        "total_due_now": float(total_due_now),
        "parcel_ids": [p.pk for p in parcels],
        "tracking_numbers": [p.tracking_number for p in parcels if p.tracking_number],
    }
