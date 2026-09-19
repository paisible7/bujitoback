"""Calculs d'expédition (Bujito Digital / autre transitaire)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pricing.models import BusinessSettings
from pricing.utils import grouping_cost, shipping_cost

from .weight_utils import parse_weight_kg

ZERO = Decimal("0.00")
CBM_ADVANCE_RATIO = Decimal("0.50")
AIR_LOYALTY_STARS = 5
AIR_LOYALTY_ADVANCE_RATIO = Decimal("0.50")  # 50 % payable à l'avance (clients 5★)


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
    transport_mode: str | None = None,
    shipping_category: str | None = None,
    forwarder_delivery_fee=None,
    forwarder_address: str | None = None,
    volume_cbm_override=None,
    weight_kg_override=None,
    settings: BusinessSettings | None = None,
    client_stars: int | None = None,
) -> dict[str, Any]:
    """
    Calcule le montant d'expédition à partir des tarifs et du colis.

    - Bujito + avion  → poids × tarif catégorie ($/kg)
      (clients 5★ : 50 % payable à l'avance)
    - Bujito + bateau → volume × tarif CBM (acompte 50 %)
    - Autre transitaire → uniquement frais de transfert (fixis par l'admin)
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
    # Si les colis viennent d'un même groupage terminé, utiliser son poids réel.
    if weight_kg_override is None and was_grouped:
        cons = (
            parcels[0]
            .consolidations.filter(status="completed", weight_kg__isnull=False)
            .order_by("-request_date")
            .first()
        )
        if cons is not None:
            cons_ids = set(cons.parcels.values_list("id", flat=True))
            req_ids = {p.pk for p in parcels}
            if req_ids and req_ids.issubset(cons_ids):
                weight = _to_decimal(cons.weight_kg)

    grouping_fee = ZERO
    if was_grouped:
        for p in parcels:
            fee = parcel_grouping_fee(p)
            if fee is not None:
                grouping_fee = fee
                break
        if grouping_fee <= 0 and weight > 0:
            grouping_fee = _to_decimal(
                grouping_cost(weight_kg=weight, settings=cfg)["amount_usd"]
            )

    shipping_fee = ZERO
    shipping_fee_full = ZERO
    air_advance = ZERO
    loyalty_discount_usd = ZERO  # reste à payer plus tard (avion 5★)
    loyalty_air_discount_applied = False
    cbm_fee = ZERO
    cbm_advance = ZERO
    category = None
    transport = (transport_mode or "").strip().lower() or None
    address = (forwarder_address or "").strip()
    stars = int(client_stars or 0)

    if mode == "bujito_digital":
        if transport not in {"air", "sea"}:
            raise ValueError("Choisissez le transport : avion ou bateau.")
        if transport == "air":
            category = (shipping_category or "ordinary").strip().lower()
            # Express = tarif accéléré réservé aux colis ordinaires uniquement.
            if category == "express":
                pass
            elif category not in {"ordinary", "sensitive", "phone"}:
                category = "ordinary"
            if weight <= 0 and category != "phone":
                raise ValueError(
                    "Poids du colis manquant : impossible de calculer le tarif avion."
                )
            ship = shipping_cost(category=category, weight_kg=weight, settings=cfg)
            if not ship.get("available", True):
                raise ValueError(ship.get("message") or "catégorie indisponible")
            shipping_fee_full = _to_decimal(ship["amount_usd"])
            shipping_fee = shipping_fee_full
            if stars >= AIR_LOYALTY_STARS and shipping_fee_full > 0:
                air_advance = (
                    shipping_fee_full * AIR_LOYALTY_ADVANCE_RATIO
                ).quantize(Decimal("0.01"))
                loyalty_discount_usd = (
                    shipping_fee_full - air_advance
                ).quantize(Decimal("0.01"))
                loyalty_air_discount_applied = True
        else:
            if volume <= 0:
                raise ValueError(
                    "Volume (CBM) du colis manquant : impossible de calculer le tarif bateau."
                )
            cbm = cbm_cost(volume_cbm=volume, settings=cfg)
            cbm_fee = _to_decimal(cbm["amount_usd"])
            cbm_advance = _to_decimal(cbm["advance_usd"])

        air_due_now = air_advance if loyalty_air_discount_applied else shipping_fee
        total_due_now = (
            grouping_fee + air_due_now + cbm_advance
        ).quantize(Decimal("0.01"))
        status = "awaiting_payment"
        forwarder_fee = ZERO

    else:
        # Autre transitaire : frais de groupage (si groupé) + frais de transfert (admin).
        if not address:
            raise ValueError("Indiquez l'adresse du transitaire.")
        forwarder_fee = _to_decimal(forwarder_delivery_fee)
        if forwarder_fee < 0:
            raise ValueError("forwarder_delivery_fee invalide")
        if forwarder_fee > 0:
            total_due_now = (grouping_fee + forwarder_fee).quantize(Decimal("0.01"))
            status = "awaiting_payment"
        else:
            # Demande client : en attente que l'admin fixe les frais de transfert.
            total_due_now = ZERO
            status = "quoted"

    return {
        "mode": mode,
        "transport_mode": transport,
        "shipping_category": category,
        "forwarder_address": address,
        "was_grouped": was_grouped,
        "weight_kg": float(weight),
        "volume_cbm": float(volume),
        "grouping_fee": float(grouping_fee if was_grouped else ZERO),
        "shipping_fee": float(shipping_fee),
        "shipping_fee_before_discount": float(
            shipping_fee_full if shipping_fee_full > 0 else shipping_fee
        ),
        "loyalty_air_advance": float(air_advance),
        "loyalty_discount_usd": float(loyalty_discount_usd),
        "loyalty_air_discount_applied": loyalty_air_discount_applied,
        "loyalty_air_discount_pct": float(AIR_LOYALTY_ADVANCE_RATIO * 100)
        if loyalty_air_discount_applied
        else 0.0,
        "client_stars": stars,
        "forwarder_delivery_fee": float(forwarder_fee if mode == "other_forwarder" else ZERO),
        "cbm_fee": float(cbm_fee),
        "cbm_fee_advance": float(cbm_advance),
        "cbm_fee_remaining": float((cbm_fee - cbm_advance).quantize(Decimal("0.01"))),
        "total_due_now": float(total_due_now),
        "status": status,
        "parcel_ids": [p.pk for p in parcels],
        "tracking_numbers": [p.tracking_number for p in parcels if p.tracking_number],
    }
