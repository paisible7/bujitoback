"""Orchestration paiements — SasPay (checkout hébergé) + simulation DEV."""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.utils import timezone

from .saspay_client import SasPayClient, SasPayError, saspay_enabled

logger = logging.getLogger(__name__)

# Plancher général SasPay — tous moyens (MM, Wave, carte, crypto).
SASPAY_MIN_AMOUNT_USD = Decimal("0.50")


def _ensure_saspay_amount_ok(payment) -> None:
    """Évite d'ouvrir une page SasPay déjà vouée à l'échec (min global)."""
    currency = (payment.currency or "USD").strip().upper()
    try:
        amount = Decimal(str(payment.amount))
    except (InvalidOperation, TypeError, ValueError):
        return
    if currency == "USD" and amount < SASPAY_MIN_AMOUNT_USD:
        raise SasPayError(
            f"Montant minimum SasPay : {SASPAY_MIN_AMOUNT_USD} USD "
            f"pour tous les moyens de paiement "
            f"(montant actuel : {amount} USD).",
            code="validation_error",
            http_status=400,
        )


def _merge_provider_meta(payment, patch: dict[str, Any]) -> dict:
    raw = payment.provider_raw_response
    base: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {"previous": raw}
    base.update(patch)
    return base


def _customer_from_payment(payment) -> tuple[str, str, str | None]:
    user = payment.user
    email = (getattr(user, "email", None) or "").strip()
    first = (getattr(user, "first_name", None) or "").strip()
    last = (getattr(user, "last_name", None) or "").strip()
    name = f"{first} {last}".strip() or email.split("@")[0] or "Client Bujito"
    phone = (payment.phone_number or getattr(user, "phone", None) or "").strip() or None
    return email or "noreply@bujitodigital.com", name, phone


def _return_url(payment) -> str | None:
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    if not base:
        return None
    return f"{base}/api/payments/return/?ref={payment.reference}"


def _map_saspay_status(status_value: str | None) -> str | None:
    status = (status_value or "").strip().upper()
    if status in {"SUCCESS", "PAID", "COMPLETED"}:
        return "completed"
    if status in {"FAILED", "ERROR"}:
        return "failed"
    if status in {"CANCELLED", "CANCELED", "EXPIRED"}:
        return "cancelled"
    if status in {"PENDING", "PROCESSING"}:
        return "pending"
    return None


class PaymentService:
    """
    Intégration SasPay :
    - initiate → POST /checkout-sessions/ (page hébergée : MM + carte)
    - verify → GET checkout status / payment verify
    Livraison uniquement sur status SUCCESS (via webhook ou verify).
    """

    @staticmethod
    def is_live() -> bool:
        return saspay_enabled()

    @staticmethod
    def initiate_payment(payment) -> str | None:
        if not saspay_enabled():
            # Fallback DEV uniquement : URL factice (jamais en prod sans clé).
            if settings.DEBUG:
                mock_url = f"https://checkout.provider.com/pay/{payment.reference}"
                payment.payment_url = mock_url
                payment.provider_raw_response = _merge_provider_meta(
                    payment,
                    {"simulated": True, "redirect_url": mock_url},
                )
                payment.save(
                    update_fields=["payment_url", "provider_raw_response", "updated_at"]
                )
                return mock_url
            raise SasPayError(
                "Paiement indisponible : configurez SASPAY_API_KEY",
                code="not_configured",
            )

        _ensure_saspay_amount_ok(payment)

        email, name, phone = _customer_from_payment(payment)
        # Ne pas envoyer un téléphone trop court / ambigu (évite 422 SasPay).
        if phone and len("".join(ch for ch in phone if ch.isdigit())) < 8:
            phone = None
        description = f"Bujito {payment.reference}"
        if payment.order_id:
            description = f"Commande Bujito {payment.reference}"
        elif payment.expedition_id:
            description = f"Expédition Bujito {payment.reference}"

        metadata = {
            "bujito_reference": payment.reference,
            "payment_uuid": str(getattr(payment, "uuid", "") or payment.pk),
            "method": getattr(payment.method, "code", None) or "",
        }
        if payment.order_id:
            metadata["order_id"] = str(payment.order_id)
        if payment.expedition_id:
            metadata["expedition_id"] = str(payment.expedition_id)

        client = SasPayClient()
        try:
            data = client.create_checkout_session(
                amount=payment.amount,
                currency=payment.currency,
                customer_email=email,
                customer_name=name,
                description=description,
                customer_phone=phone,
                return_url=_return_url(payment),
                metadata=metadata,
            )
        except SasPayError as exc:
            logger.warning(
                "SasPay initiate failed for %s: %s | payload=%s",
                payment.reference,
                exc,
                getattr(exc, "payload", None),
            )
            raise
        except Exception as exc:
            logger.exception("SasPay initiate unexpected error for %s", payment.reference)
            raise SasPayError("Échec initialisation SasPay") from exc

        checkout_url = (data.get("checkout_url") or "").strip()
        session_id = str(data.get("id") or "").strip() or None
        if not checkout_url:
            raise SasPayError(
                "SasPay n'a pas renvoyé de checkout_url",
                code="missing_checkout_url",
                payload=data,
            )

        payment.payment_url = checkout_url
        payment.external_id = session_id
        payment.provider_raw_response = _merge_provider_meta(
            payment,
            {
                "provider": "saspay",
                "saspay_checkout_id": session_id,
                "saspay_checkout_slug": data.get("slug"),
                "saspay_checkout_status": data.get("status"),
                "checkout_url": checkout_url,
            },
        )
        payment.save(
            update_fields=[
                "payment_url",
                "external_id",
                "provider_raw_response",
                "updated_at",
            ]
        )
        return checkout_url

    @staticmethod
    def verify_payment_status(payment) -> str | None:
        """
        Interroge SasPay et met à jour le Payment si statut terminal.
        Retourne le nouveau statut interne ou None si inchangé / indisponible.
        """
        if payment.status in {"completed", "failed", "cancelled"}:
            return payment.status

        if not saspay_enabled():
            return None

        meta = payment.provider_raw_response if isinstance(payment.provider_raw_response, dict) else {}
        checkout_id = (
            meta.get("saspay_checkout_id")
            or (payment.external_id if not meta.get("saspay_payment_id") else None)
        )
        payment_id = meta.get("saspay_payment_id") or meta.get("saspay_transaction_id")

        client = SasPayClient()
        mapped = None
        provider_patch: dict[str, Any] = {"provider": "saspay", "verified_at": timezone.now().isoformat()}

        try:
            if payment_id:
                data = client.verify_payment(str(payment_id))
                mapped = _map_saspay_status(data.get("status"))
                provider_patch["saspay_verify"] = {
                    "id": data.get("id"),
                    "status": data.get("status"),
                    "net_amount": data.get("net_amount"),
                    "currency": data.get("currency"),
                }
                if data.get("id"):
                    payment.external_id = str(data["id"])
            elif checkout_id:
                data = client.checkout_status(str(checkout_id))
                mapped = _map_saspay_status(
                    data.get("transaction_status") or data.get("status")
                )
                provider_patch["saspay_checkout_status"] = data.get("status")
                tx_id = data.get("transaction_id") or data.get("transaction_reference")
                if tx_id:
                    provider_patch["saspay_payment_id"] = str(tx_id)
                    payment.external_id = str(tx_id)
                    # Double-check via verify if SUCCESS-ish
                    if mapped == "completed" or (data.get("transaction_status") or "").upper() == "SUCCESS":
                        try:
                            verified = client.verify_payment(str(tx_id))
                            mapped = _map_saspay_status(verified.get("status")) or mapped
                            provider_patch["saspay_verify"] = {
                                "id": verified.get("id"),
                                "status": verified.get("status"),
                                "net_amount": verified.get("net_amount"),
                                "currency": verified.get("currency"),
                            }
                        except SasPayError:
                            pass
            else:
                return None
        except SasPayError as exc:
            logger.warning(
                "SasPay verify failed for %s: %s",
                payment.reference,
                exc,
            )
            return None

        if not mapped or mapped == "pending":
            payment.provider_raw_response = _merge_provider_meta(payment, provider_patch)
            payment.save(update_fields=["provider_raw_response", "external_id", "updated_at"])
            return None

        if payment.status != mapped:
            payment.status = mapped
        payment.provider_raw_response = _merge_provider_meta(payment, provider_patch)
        payment.save(
            update_fields=["status", "provider_raw_response", "external_id", "updated_at"]
        )
        return mapped

    @staticmethod
    def apply_saspay_webhook_event(payment, event: str, data: dict) -> str | None:
        """Applique un event webhook SasPay déjà authentifié. Retourne nouveau statut ou None."""
        event_l = (event or "").strip().lower()
        status_raw = (data.get("status") or "").strip().upper()

        mapped = None
        if event_l == "transaction.success" or status_raw == "SUCCESS":
            mapped = "completed"
        elif event_l == "transaction.failed" or status_raw == "FAILED":
            mapped = "failed"
        elif event_l in {"transaction.cancelled", "transaction.canceled"} or status_raw in {
            "CANCELLED",
            "CANCELED",
        }:
            mapped = "cancelled"

        patch = {
            "provider": "saspay",
            "saspay_webhook_event": event_l,
            "saspay_webhook_data": {
                "id": data.get("id"),
                "reference": data.get("reference"),
                "status": data.get("status"),
                "amount": data.get("amount"),
                "charged": data.get("charged"),
                "net_amount": data.get("net_amount"),
                "fee": data.get("fee"),
                "fee_charge_mode": data.get("fee_charge_mode"),
                "currency": data.get("currency"),
                "country": data.get("country"),
                "network": data.get("network"),
            },
        }
        if data.get("id"):
            patch["saspay_payment_id"] = str(data["id"])
            payment.external_id = str(data["id"])

        payment.provider_raw_response = _merge_provider_meta(payment, patch)
        if mapped and payment.status != mapped:
            payment.status = mapped
            payment.save(
                update_fields=[
                    "status",
                    "provider_raw_response",
                    "external_id",
                    "updated_at",
                ]
            )
            return mapped

        payment.save(
            update_fields=["provider_raw_response", "external_id", "updated_at"]
        )
        return None
