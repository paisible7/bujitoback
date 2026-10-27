"""Client HTTP SasPay — appels serveur uniquement (clé jamais exposée)."""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.saspay.me/api/v1"
REQUEST_TIMEOUT = 30


class SasPayError(Exception):
    """Erreur métier ou HTTP SasPay."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        code: str | None = None,
        payload: Any = None,
    ):
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.payload = payload


def saspay_enabled() -> bool:
    return bool((getattr(settings, "SASPAY_API_KEY", "") or "").strip())


def _api_key() -> str:
    key = (getattr(settings, "SASPAY_API_KEY", "") or "").strip()
    if not key:
        raise SasPayError("SASPAY_API_KEY manquante", code="not_configured")
    return key


def _base_url() -> str:
    return (
        getattr(settings, "SASPAY_BASE_URL", "") or DEFAULT_BASE_URL
    ).rstrip("/")


def amount_to_decimal_string(amount) -> str:
    """Montants SasPay = chaînes décimales, jamais de flottants."""
    try:
        value = Decimal(str(amount).replace(",", ".")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SasPayError(f"Montant invalide: {amount}") from exc
    if value <= 0:
        raise SasPayError("Le montant doit être > 0")
    return f"{value:.2f}"


def resolve_country_and_currency(currency: str | None) -> tuple[str, str]:
    """
    Map devise Bujito → (country ISO / code SasPay, currency ISO).
    XC = RDC (USD) dans le catalogue SasPay ; CD = RDC en CDF.
    """
    code = (currency or "USD").strip().upper()
    if code in {"FC", "CDF"}:
        return "CD", "CDF"
    if code in {"FCFA", "XOF"}:
        return "BJ", "XOF"
    if code == "CNY":
        return "CN", "CNY"
    if code == "GBP":
        return "GB", "GBP"
    # Commandes / expéditions Bujito en USD → wallet RDC (USD)
    return "XC", "USD"


def _unwrap(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {}
    if payload.get("success") is False:
        err = payload.get("error") or {}
        if isinstance(err, dict) and "message" in err:
            raise SasPayError(
                str(err.get("message") or "Erreur SasPay"),
                http_status=payload.get("code"),
                code=str(err.get("code") or "") or None,
                payload=payload,
            )
        # Erreurs de validation {champ: [msg]}
        raise SasPayError(
            "Requête SasPay invalide",
            http_status=payload.get("code") or 400,
            code="validation_error",
            payload=payload,
        )
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


class SasPayClient:
    """Client REST SasPay (Bearer sk_test_… / sk_live_…)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = (api_key if api_key is not None else _api_key()).strip()
        self.base_url = (base_url or _base_url()).rstrip("/")

    def _headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(idempotency_key=idempotency_key),
                json=json_body,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning("SasPay network error on %s %s: %s", method, path, type(exc).__name__)
            raise SasPayError(
                "Impossible de joindre SasPay",
                code="network_error",
            ) from exc

        try:
            payload = response.json() if response.content else {}
        except ValueError:
            payload = {"raw": (response.text or "")[:500]}

        if response.status_code == 429:
            raise SasPayError(
                "Limite de débit SasPay (429) — réessayez plus tard",
                http_status=429,
                code="rate_limited",
                payload=payload,
            )
        if response.status_code in {401, 403}:
            raise SasPayError(
                "Authentification SasPay refusée",
                http_status=response.status_code,
                code="auth_error",
                payload=payload,
            )
        if response.status_code >= 400:
            message = "Erreur SasPay"
            code = None
            if isinstance(payload, dict):
                err = payload.get("error")
                if isinstance(err, dict):
                    message = str(err.get("message") or message)
                    code = err.get("code")
                elif payload.get("message"):
                    message = str(payload["message"])
            raise SasPayError(
                message,
                http_status=response.status_code,
                code=str(code) if code else None,
                payload=payload,
            )

        return _unwrap(payload)

    def create_checkout_session(
        self,
        *,
        amount,
        currency: str,
        customer_email: str,
        customer_name: str,
        description: str = "",
        country: str | None = None,
        customer_phone: str | None = None,
        return_url: str | None = None,
        metadata: dict | None = None,
        fee_charge_mode: str | None = None,
    ) -> dict:
        country_code, currency_code = resolve_country_and_currency(currency)
        if country:
            country_code = country.strip().upper()
        body: dict[str, Any] = {
            "amount": amount_to_decimal_string(amount),
            "currency": currency_code,
            "customer_email": (customer_email or "").strip() or "noreply@bujitodigital.com",
            "customer_name": (customer_name or "").strip() or "Client Bujito",
            "country": country_code,
        }
        if description:
            body["description"] = description[:255]
        if customer_phone:
            body["customer_phone"] = customer_phone.strip()
        if return_url:
            body["return_url"] = return_url
        if metadata:
            body["metadata"] = metadata
        mode = (fee_charge_mode or getattr(settings, "SASPAY_FEE_CHARGE_MODE", "") or "").strip()
        if mode in {"ADD_ON", "DEDUCTED"}:
            body["fee_charge_mode"] = mode

        return self._request("POST", "/checkout-sessions/", json_body=body)

    def checkout_status(self, session_id: str) -> dict:
        return self._request("GET", f"/checkout-sessions/{session_id}/status/")

    def verify_payment(self, payment_id: str) -> dict:
        return self._request("GET", f"/payments/{payment_id}/verify/")

    def softpay(
        self,
        *,
        amount,
        currency: str,
        country: str,
        network: str,
        customer: dict,
        description: str = "",
        metadata: dict | None = None,
        idempotency_key: str | None = None,
        fee_charge_mode: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "amount": amount_to_decimal_string(amount),
            "currency": currency.strip().upper(),
            "country": country.strip().upper(),
            "network": network.strip(),
            "customer": customer,
        }
        if description:
            body["description"] = description[:255]
        if metadata:
            body["metadata"] = metadata
        mode = (fee_charge_mode or getattr(settings, "SASPAY_FEE_CHARGE_MODE", "") or "").strip()
        if mode in {"ADD_ON", "DEDUCTED"}:
            body["fee_charge_mode"] = mode
        return self._request(
            "POST",
            "/payments/softpay/",
            json_body=body,
            idempotency_key=idempotency_key or str(uuid4()),
        )
