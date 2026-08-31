"""Helpers pour liens produits / devis (JSON dans Order.product_links)."""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any


def _to_decimal(value) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_qty(value) -> int:
    try:
        qty = int(value)
    except (TypeError, ValueError):
        return 1
    return qty if qty > 0 else 1


def parse_product_items(raw: str | None) -> list[dict[str, Any]]:
    """
    Normalise product_links en liste de {url, description, price, quantity}.
    Accepte : JSON liste de strings, JSON liste d'objets, texte multiligne.
    Une ligne issue d'une photo peut avoir une description sans URL.
    """
    if not raw:
        return []

    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None

    items: list[dict[str, Any]] = []
    if isinstance(parsed, list):
        for entry in parsed:
            if isinstance(entry, str):
                url = entry.strip()
                if url:
                    items.append({'url': url, 'price': None, 'quantity': 1})
            elif isinstance(entry, dict):
                url = str(entry.get('url') or entry.get('link') or '').strip()
                description = str(entry.get('description') or entry.get('label') or '').strip()
                if not url and not description:
                    continue
                items.append({
                    'url': url,
                    'description': description,
                    'price': _to_decimal(entry.get('price')),
                    'quantity': _to_qty(entry.get('quantity', 1)),
                })
        return items

    for line in str(raw).splitlines():
        url = line.strip()
        if url:
            items.append({'url': url, 'price': None, 'quantity': 1})
    return items


def dump_product_items(items: list[dict[str, Any]]) -> str:
    serializable = []
    for item in items:
        url = str(item.get('url') or '').strip()
        description = str(item.get('description') or item.get('label') or '').strip()
        if not url and not description:
            continue
        qty = _to_qty(item.get('quantity', 1))
        price = item.get('price')
        entry = {'quantity': qty}
        if url:
            entry['url'] = url
        if description:
            entry['description'] = description
        if price is None or price == '':
            entry['price'] = None
        else:
            dec = _to_decimal(price)
            entry['price'] = float(dec) if dec is not None else None
        serializable.append(entry)
    return json.dumps(serializable, ensure_ascii=False)


def normalize_incoming_links(links) -> list[dict[str, Any]]:
    """Normalise la payload create/update (list, string JSON, etc.)."""
    if links is None:
        return []
    if isinstance(links, str):
        return parse_product_items(links)
    if isinstance(links, list):
        return parse_product_items(json.dumps(links, ensure_ascii=False))
    return []


def compute_quote_total(items: list[dict[str, Any]], withdrawal_fee) -> Decimal:
    total = Decimal('0.00')
    for item in items:
        price = _to_decimal(item.get('price'))
        if price is not None:
            qty = _to_qty(item.get('quantity', 1))
            total += price * qty
    fee = _to_decimal(withdrawal_fee) or Decimal('0.00')
    return total + fee


def total_items_quantity(items: list[dict[str, Any]]) -> int:
    return sum(_to_qty(item.get('quantity', 1)) for item in items) or 1
