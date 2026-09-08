"""Helpers pour parser poids et dates depuis l'import Excel / API."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


def parse_weight_kg(value) -> Optional[Decimal]:
    """Extrait un poids numérique depuis un nombre ou une chaîne (ex. '12.5kg')."""
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    s = str(value).strip().replace(',', '.')
    match = re.search(r'(\d+(?:\.\d+)?)', s)
    if not match:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None


def parse_china_date(value) -> Optional[date]:
    """Parse une date d'arrivée Chine (Excel date, ISO, ou formats FR courants)."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # ISO datetime
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).date()
    except ValueError:
        return None
