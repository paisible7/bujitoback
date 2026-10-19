"""Calculs de poids facturable, frais d'expédition et de groupage."""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, InvalidOperation
from typing import Any

from .cities import normalize_pricing_city, resolve_city_rates
from .models import BusinessSettings

HALF = Decimal("0.5")
ZERO = Decimal("0.00")


def _to_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None


def billable_weight_kg(weight) -> Decimal:
    """
    Arrondi par excès au demi-kilo :
    0.2 → 0.5 ; 0.6 → 1.0 ; 1.0 → 1.0.
    """
    w = _to_decimal(weight)
    if w is None or w <= 0:
        return ZERO
    steps = (w / HALF).to_integral_value(rounding=ROUND_CEILING)
    return (steps * HALF).quantize(HALF)


def shipping_cost(
    *,
    category: str,
    weight_kg=None,
    quantity: int = 1,
    settings: BusinessSettings | None = None,
    city=None,
) -> dict[str, Any]:
    """
    category: ordinary | express | sensitive | phone | computer
    city: Kinshasa (défaut) ou Lubumbashi
    """
    cfg = settings or BusinessSettings.load()
    rates = resolve_city_rates(cfg, city)
    cat = (category or "ordinary").strip().lower()
    billable = billable_weight_kg(weight_kg)
    pieces = max(1, int(quantity or 1))

    if cat == "phone":
        amount = rates["phone_flat_fee"]
        days = rates["phone_days"]
        available = True
        detail = "forfait téléphone"
    elif cat == "computer":
        amount = (rates["computer_flat_fee"] * pieces).quantize(Decimal("0.01"))
        days = None
        available = True
        detail = f"{pieces} × forfait ordinateur à {rates['computer_flat_fee']} $/pièce"
    elif cat == "express":
        available = bool(cfg.express_available)
        days = rates["express_days"]
        amount = (billable * rates["express_rate_per_kg"]).quantize(Decimal("0.01")) if available else ZERO
        detail = f"{billable} kg × {rates['express_rate_per_kg']} $/kg"
    elif cat == "sensitive":
        available = True
        days = rates["sensitive_days"]
        amount = (billable * rates["sensitive_rate_per_kg"]).quantize(Decimal("0.01"))
        detail = f"{billable} kg × {rates['sensitive_rate_per_kg']} $/kg"
    else:
        cat = "ordinary"
        available = True
        days = rates["ordinary_days"]
        amount = (billable * rates["ordinary_rate_per_kg"]).quantize(Decimal("0.01"))
        detail = f"{billable} kg × {rates['ordinary_rate_per_kg']} $/kg"

    return {
        "category": cat,
        "available": available,
        "weight_kg": float(_to_decimal(weight_kg) or 0),
        "billable_kg": float(billable),
        "days": days,
        "amount_usd": float(amount),
        "detail": detail,
        "city": normalize_pricing_city(city),
        "message": None if available else "Express bientôt disponible",
    }


def grouping_cost(
    *,
    weight_kg,
    settings: BusinessSettings | None = None,
) -> dict[str, Any]:
    cfg = settings or BusinessSettings.load()
    billable = billable_weight_kg(weight_kg)

    if billable <= 0:
        amount = ZERO
        detail = "poids invalide"
    elif billable <= cfg.grouping_flat_max_kg:
        amount = cfg.grouping_flat_fee
        detail = f"forfait ≤ {cfg.grouping_flat_max_kg} kg"
    else:
        amount = (billable * cfg.grouping_rate_per_kg).quantize(Decimal("0.01"))
        detail = f"{billable} kg × {cfg.grouping_rate_per_kg} $/kg"

    return {
        "weight_kg": float(_to_decimal(weight_kg) or 0),
        "billable_kg": float(billable),
        "amount_usd": float(amount),
        "detail": detail,
    }
