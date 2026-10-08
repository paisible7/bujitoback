"""Pipeline commun d'upload / validation d'images."""
from __future__ import annotations

import io
import logging
import uuid
from typing import Iterable

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
ALLOWED_CONTENT_TYPES = {
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
    'image/gif',
}
MAX_IMAGE_BYTES = 12 * 1024 * 1024  # 12 Mo
MAX_DIMENSION = 4096


def _extension(name: str) -> str:
    name = (name or '').strip().lower()
    if '.' not in name:
        return ''
    return '.' + name.rsplit('.', 1)[-1]


def collect_uploads(request, field_names: Iterable[str]) -> list[UploadedFile]:
    uploads: list[UploadedFile] = []
    files = getattr(request, 'FILES', None)
    if not files:
        return uploads
    for field in field_names:
        uploads.extend(files.getlist(field))
    return uploads


def normalize_image_upload(
    uploaded: UploadedFile,
    *,
    prefix: str = 'img',
) -> InMemoryUploadedFile:
    """
    Valide et normalise un upload image:
    - taille max
    - décodage Pillow
    - conversion JPEG/PNG/WEBP
    - nom de fichier UUID (évite collisions / caractères bizarres)
    """
    if uploaded is None:
        raise ValidationError('Fichier image manquant.')

    size = getattr(uploaded, 'size', None)
    if size is not None and size > MAX_IMAGE_BYTES:
        raise ValidationError('Image trop volumineuse (max 12 Mo).')

    raw_name = getattr(uploaded, 'name', '') or f'{prefix}.jpg'
    ext = _extension(raw_name)
    content_type = (getattr(uploaded, 'content_type', '') or '').lower()

    try:
        uploaded.seek(0)
    except Exception:
        pass

    try:
        image = Image.open(uploaded)
        image.load()
    except UnidentifiedImageError as exc:
        raise ValidationError(
            'Fichier image invalide. Utilisez JPG, PNG, WEBP ou GIF.'
        ) from exc
    except Exception as exc:
        raise ValidationError(f'Impossible de lire l’image: {exc}') from exc

    if max(image.size) > MAX_DIMENSION:
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

    fmt = (image.format or '').upper()
    if image.mode not in ('RGB', 'RGBA', 'L', 'P'):
        image = image.convert('RGB')

    # Prefer JPEG for photos; keep PNG/WEBP/GIF when already suited.
    if fmt in {'PNG', 'WEBP', 'GIF'} and (ext in {'.png', '.webp', '.gif'} or content_type in ALLOWED_CONTENT_TYPES):
        out_fmt = 'PNG' if fmt == 'PNG' else ('WEBP' if fmt == 'WEBP' else 'GIF')
        out_ext = '.' + out_fmt.lower()
        out_mime = f'image/{out_fmt.lower()}'
        if image.mode == 'P' and out_fmt != 'GIF':
            image = image.convert('RGBA')
    else:
        if image.mode in ('RGBA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            rgba = image.convert('RGBA')
            background.paste(rgba, mask=rgba.split()[-1])
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        out_fmt = 'JPEG'
        out_ext = '.jpg'
        out_mime = 'image/jpeg'

    buffer = io.BytesIO()
    save_kwargs = {'format': out_fmt}
    if out_fmt == 'JPEG':
        save_kwargs.update(quality=85, optimize=True)
    image.save(buffer, **save_kwargs)
    buffer.seek(0)

    safe_name = f'{prefix}_{uuid.uuid4().hex}{out_ext}'
    return InMemoryUploadedFile(
        file=buffer,
        field_name=getattr(uploaded, 'field_name', None),
        name=safe_name,
        content_type=out_mime,
        size=buffer.getbuffer().nbytes,
        charset=None,
    )


def normalize_image_uploads(
    uploads: Iterable[UploadedFile],
    *,
    prefix: str = 'img',
) -> list[InMemoryUploadedFile]:
    normalized = []
    for uploaded in uploads:
        try:
            normalized.append(normalize_image_upload(uploaded, prefix=prefix))
        except ValidationError:
            raise
        except Exception as exc:
            logger.exception('normalize_image_uploads failed: %s', exc)
            raise ValidationError(f'Erreur traitement image: {exc}') from exc
    return normalized
