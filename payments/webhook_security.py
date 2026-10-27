"""Vérification signature webhooks SasPay (+ compat legacy)."""
from __future__ import annotations

import hashlib
import hmac
import time

from django.conf import settings

WEBHOOK_TOLERANCE_SECONDS = 300


def webhook_secret() -> str:
    """Préfère SASPAY_WEBHOOK_SECRET, sinon PAYMENT_WEBHOOK_SECRET."""
    return (
        (getattr(settings, "SASPAY_WEBHOOK_SECRET", "") or "").strip()
        or (getattr(settings, "PAYMENT_WEBHOOK_SECRET", "") or "").strip()
    )


def verify_saspay_webhook(raw_body: bytes, signature: str, timestamp: str, secret: str) -> bool:
    """
    SasPay : HMAC-SHA256 hex de f"{timestamp}.{body}" ; rejeter si |now-ts| > 300s.
    """
    if not secret or not signature or not timestamp:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > WEBHOOK_TOLERANCE_SECONDS:
        return False
    signed = f"{timestamp}.".encode("utf-8") + (raw_body or b"")
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def verify_legacy_hmac(raw_body: bytes, signature: str, secret: str) -> bool:
    """Ancien schéma (corps seul) — conservé pour compat tests/dev."""
    if not secret or not signature:
        return False
    sig = signature.strip()
    if sig.startswith("sha256="):
        sig = sig[len("sha256=") :]
    mac = hmac.new(secret.encode("utf-8"), msg=raw_body or b"", digestmod=hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, sig)


def verify_incoming_webhook(request) -> bool:
    secret = webhook_secret()
    if not secret:
        # Sans secret : uniquement en DEBUG (jamais en production).
        return bool(settings.DEBUG)

    raw = request.body or b""
    saspay_sig = (request.headers.get("X-Webhook-Signature") or "").strip()
    saspay_ts = (request.headers.get("X-Webhook-Timestamp") or "").strip()
    if saspay_sig and saspay_ts:
        return verify_saspay_webhook(raw, saspay_sig, saspay_ts, secret)

    legacy = (
        request.headers.get("X-Payment-Signature")
        or request.headers.get("X-Signature")
        or request.headers.get("X-Hub-Signature-256")
        or ""
    ).strip()
    if legacy:
        return verify_legacy_hmac(raw, legacy, secret)
    return False
