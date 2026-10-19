"""Tarifs d'expédition par ville de destination (Kinshasa / Lubumbashi)."""
from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

PRICING_CITY_KINSHASA = 'kinshasa'
PRICING_CITY_LUBUMBASHI = 'lubumbashi'
PRICING_CITIES = (PRICING_CITY_KINSHASA, PRICING_CITY_LUBUMBASHI)

CITY_RATE_KEYS = (
    'ordinary_rate_per_kg',
    'ordinary_days',
    'express_rate_per_kg',
    'express_days',
    'sensitive_rate_per_kg',
    'sensitive_days',
    'phone_flat_fee',
    'phone_days',
    'computer_flat_fee',
    'cbm_rate_usd',
)

_INT_KEYS = {
    'ordinary_days',
    'express_days',
    'sensitive_days',
    'phone_days',
}


def normalize_pricing_city(raw) -> str:
    text = unicodedata.normalize('NFD', str(raw or '').strip().lower())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    compact = ''.join(ch for ch in text if ch.isalnum())
    if 'lubum' in compact or 'lushi' in compact:
        return PRICING_CITY_LUBUMBASHI
    return PRICING_CITY_KINSHASA


def _as_decimal(value, fallback: Decimal) -> Decimal:
    if value in (None, ''):
        return fallback
    try:
        return Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, TypeError, ValueError):
        return fallback


def _as_int(value, fallback: int) -> int:
    if value in (None, ''):
        return fallback
    try:
        return int(Decimal(str(value).replace(',', '.')))
    except (InvalidOperation, TypeError, ValueError):
        return fallback


def _base_rates(settings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in CITY_RATE_KEYS:
        out[key] = getattr(settings, key)
    return out


def _json_rates(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    return raw


def resolve_city_rates(settings, city=None) -> dict[str, Any]:
    """Tarifs d'expédition pour une ville (Lubumbashi = overlay, sinon Kinshasa)."""
    base = _base_rates(settings)
    city_key = normalize_pricing_city(city)
    if city_key == PRICING_CITY_KINSHASA:
        return base
    overlay = _json_rates(getattr(settings, 'city_shipping_rates', None)).get(
        PRICING_CITY_LUBUMBASHI
    )
    if not isinstance(overlay, dict) or not overlay:
        return base
    merged = dict(base)
    for key in CITY_RATE_KEYS:
        if key not in overlay:
            continue
        fallback = base[key]
        if key in _INT_KEYS:
            merged[key] = _as_int(overlay[key], int(fallback or 0))
        else:
            merged[key] = _as_decimal(overlay[key], Decimal(str(fallback or 0)))
    return merged


def _jsonify_rates(rates: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in CITY_RATE_KEYS:
        val = rates.get(key)
        if key in _INT_KEYS:
            out[key] = int(val or 0)
        else:
            out[key] = float(Decimal(str(val or 0)))
    return out


def serialize_shipping_by_city(settings) -> dict[str, dict[str, Any]]:
    return {
        PRICING_CITY_KINSHASA: _jsonify_rates(resolve_city_rates(settings, PRICING_CITY_KINSHASA)),
        PRICING_CITY_LUBUMBASHI: _jsonify_rates(
            resolve_city_rates(settings, PRICING_CITY_LUBUMBASHI)
        ),
    }


def apply_shipping_by_city(settings, payload) -> None:
    """Écrit Kinshasa dans les colonnes globales, Lubumbashi dans le JSON."""
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return
    if not isinstance(payload, dict):
        return
    kin = payload.get(PRICING_CITY_KINSHASA)
    if isinstance(kin, dict):
        for key in CITY_RATE_KEYS:
            if key not in kin:
                continue
            current = getattr(settings, key)
            if key in _INT_KEYS:
                setattr(settings, key, _as_int(kin[key], int(current or 0)))
            else:
                setattr(settings, key, _as_decimal(kin[key], Decimal(str(current or 0))))

    lub = payload.get(PRICING_CITY_LUBUMBASHI)
    current_lub = resolve_city_rates(settings, PRICING_CITY_LUBUMBASHI)
    if isinstance(lub, dict):
        for key in CITY_RATE_KEYS:
            if key not in lub:
                continue
            fallback = current_lub[key]
            if key in _INT_KEYS:
                current_lub[key] = _as_int(lub[key], int(fallback or 0))
            else:
                current_lub[key] = _as_decimal(lub[key], Decimal(str(fallback or 0)))
    settings.city_shipping_rates = {
        PRICING_CITY_LUBUMBASHI: _jsonify_rates(current_lub),
    }
