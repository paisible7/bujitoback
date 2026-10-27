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
    Map devise Bujito → (country ISO2 SasPay, currency ISO).
    RDC = CD (Airtel/Orange/Vodacom). Les paiements USD restent en USD ;
    SasPay convertit si le réseau exige une autre devise.
    Pour carte internationale seule, XX est aussi accepté — on privilégie CD
    pour afficher les MM congolais sur le checkout hébergé.
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
    # USD (commandes / expéditions) → pays RDC
    return "CD", "USD"


def _humanize_error_payload(payload: Any) -> tuple[str, str | None]:
    """Extrait un message lisible + code depuis une réponse d'erreur SasPay."""
    if not isinstance(payload, dict):
        return "Erreur SasPay", None
    err = payload.get("error")
    if isinstance(err, dict) and err.get("message"):
        return str(err["message"]), (str(err["code"]) if err.get("code") else None)
    if isinstance(payload.get("message"), str) and payload["message"].strip():
        return payload["message"].strip(), None
    # Validation style {champ: ["…"]} ou error: {champ: ["…"]}
    source = err if isinstance(err, dict) else payload
    parts: list[str] = []
    for key, val in source.items():
        if key in {"success", "code", "data", "error", "detail"}:
            if key == "detail" and isinstance(val, str) and val.strip():
                return val.strip(), None
            continue
        if isinstance(val, list) and val:
            parts.append(f"{key}: {', '.join(str(v) for v in val)}")
        elif isinstance(val, str) and val.strip():
            parts.append(f"{key}: {val.strip()}")
    if parts:
        # Un seul champ → message seul (« Le montant minimum est de 0.50 USD. »)
        if len(parts) == 1 and ": " in parts[0]:
            return parts[0].split(": ", 1)[1], "validation_error"
        return " ; ".join(parts), "validation_error"
    return "Erreur SasPay", None


def _unwrap(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {}
    if payload.get("success") is False:
        message, code = _humanize_error_payload(payload)
        raise SasPayError(
            message,
            http_status=payload.get("code"),
            code=code,
            payload=payload,
        )
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    # Certaines routes renvoient l'objet directement (sans enveloppe).
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
            message, code = _humanize_error_payload(payload)
            logger.warning(
                "SasPay HTTP %s on %s %s: %s",
                response.status_code,
                method,
                path,
                message,
            )
            raise SasPayError(
                message,
                http_status=response.status_code,
                code=code,
                payload=payload,
            )

        # Succès (200/201…) — enveloppe {success,data} ou objet brut.
        try:
            return _unwrap(payload)
        except SasPayError:
            raise
        except Exception as exc:
            logger.warning("SasPay unwrap failed on %s %s: %s", method, path, type(exc).__name__)
            raise SasPayError(
                "Réponse SasPay illisible",
                http_status=response.status_code,
                code="bad_response",
                payload=payload if isinstance(payload, dict) else None,
            ) from exc

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
