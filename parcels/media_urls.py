"""Helpers pour URLs media absolues (photos colis / commandes)."""
from __future__ import annotations

import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)


def absolute_media_url(file_field, request=None, *, label: str = 'media') -> str | None:
    """Retourne une URL absolue https pour un ImageField/FileField, ou None."""
    if not file_field:
        logger.debug('%s: champ fichier vide', label)
        return None

    try:
        relative = file_field.url
    except ValueError as exc:
        logger.warning('%s: .url inaccessible: %s', label, exc)
        return None

    try:
        disk_path = file_field.path
        if not os.path.exists(disk_path):
            logger.warning('%s: fichier manquant sur disque path=%s url=%s', label, disk_path, relative)
        else:
            logger.debug('%s: OK path=%s url=%s', label, disk_path, relative)
    except Exception as exc:
        logger.warning('%s: impossible de résoudre .path: %s (url=%s)', label, exc, relative)

    # 1) Request (corrige Host / HTTPS via X-Forwarded-*)
    if request is not None:
        absolute = request.build_absolute_uri(relative)
        # Si le proxy renvoie http:// alors qu'on est en HTTPS public
        public = getattr(settings, 'PUBLIC_BASE_URL', '') or ''
        if public and absolute.startswith('http://') and public.startswith('https://'):
            absolute = 'https://' + absolute[len('http://'):]
        logger.info('%s: URL absolue=%s', label, absolute)
        return absolute

    # 2) PUBLIC_BASE_URL de settings / .env
    public = getattr(settings, 'PUBLIC_BASE_URL', '') or ''
    if public:
        absolute = f'{public.rstrip("/")}{relative}'
        logger.info('%s: URL via PUBLIC_BASE_URL=%s', label, absolute)
        return absolute

    logger.warning('%s: pas de request ni PUBLIC_BASE_URL — URL relative=%s', label, relative)
    return relative
