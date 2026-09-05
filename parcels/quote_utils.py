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
                item = {
                    'url': url,
                    'description': description,
                    'price': _to_decimal(entry.get('price')),
                    'quantity': _to_qty(entry.get('quantity', 1)),
                }
                pkg = entry.get('package_index')
                if pkg is not None and pkg != '':
                    try:
                        item['package_index'] = max(0, int(pkg))
                    except (TypeError, ValueError):
                        pass
                items.append(item)
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
        pkg = item.get('package_index')
        if pkg is not None and pkg != '':
            try:
                entry['package_index'] = max(0, int(pkg))
            except (TypeError, ValueError):
                pass
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


def compute_quote_total(
    items: list[dict[str, Any]],
    withdrawal_fee=0,
    commission_fee=0,
) -> Decimal:
    total = Decimal('0.00')
    for item in items:
        price = _to_decimal(item.get('price'))
        if price is not None:
            qty = _to_qty(item.get('quantity', 1))
            total += price * qty
    withdrawal = _to_decimal(withdrawal_fee) or Decimal('0.00')
    commission = _to_decimal(commission_fee) or Decimal('0.00')
    return total + withdrawal + commission


def flatten_packages(packages) -> tuple[list[dict[str, Any]], int, str | None]:
    """
    Transforme une liste de colis client en product_items + expected_count + commentaire agrégé.
    Chaque colis: {description?, comment?, links: [{url, quantity}] | product_items}
    """
    if not isinstance(packages, list) or not packages:
        return [], 0, None

    items: list[dict[str, Any]] = []
    comments: list[str] = []
    package_count = 0

    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            continue
        package_count += 1
        pkg_index = package_count - 1
        description = str(
            package.get('description') or package.get('comment') or ''
        ).strip()
        comment = str(package.get('comment') or '').strip()
        if comment and comment != description:
            comments.append(f"Colis {package_count}: {comment}")
        elif description:
            comments.append(f"Colis {package_count}: {description}")

        links = package.get('links') or package.get('product_items') or package.get('items') or []
        link_items = normalize_incoming_links(links)
        if not link_items and description:
            link_items = [{'url': '', 'description': description, 'quantity': _to_qty(package.get('quantity', 1))}]
        elif not link_items and package.get('quantity'):
            link_items = [{'url': '', 'description': description or f'Colis {package_count}', 'quantity': _to_qty(package.get('quantity', 1))}]

        for link in link_items:
            entry = dict(link)
            entry['package_index'] = pkg_index
            if description and not entry.get('description'):
                entry['description'] = description
            items.append(entry)

        # Colis photo-only sans lien ni description explicite
        if not link_items:
            items.append({
                'url': '',
                'description': description or f'Colis {package_count}',
                'quantity': _to_qty(package.get('quantity', 1)),
                'package_index': pkg_index,
            })

    aggregated_comment = '\n'.join(comments) if comments else None
    return items, max(package_count, 1 if items else 0), aggregated_comment


def total_items_quantity(items: list[dict[str, Any]]) -> int:
    return sum(_to_qty(item.get('quantity', 1)) for item in items) or 1
