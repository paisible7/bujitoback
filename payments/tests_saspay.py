"""Tests sécurité webhook SasPay + mapping pays/devise."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from users.models import CustomUser

from .models import Payment, PaymentMethod
from .saspay_client import amount_to_decimal_string, resolve_country_and_currency
from .webhook_security import verify_saspay_webhook


class SasPayHelpersTests(TestCase):
    def test_amount_is_decimal_string(self):
        self.assertEqual(amount_to_decimal_string("14"), "14.00")
        self.assertEqual(amount_to_decimal_string(Decimal("22.5")), "22.50")

    def test_rdc_usd_maps_to_xc(self):
        self.assertEqual(resolve_country_and_currency("USD"), ("XC", "USD"))
        self.assertEqual(resolve_country_and_currency("CDF"), ("CD", "CDF"))


class SasPayWebhookSignatureTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="saspay@example.com",
            password="test-password",
        )
        self.method, _ = PaymentMethod.objects.get_or_create(
            code="card",
            defaults={"name": "Carte", "is_active": True},
        )
        self.payment = Payment.objects.create(
            user=self.user,
            amount=Decimal("50.00"),
            currency="USD",
            reference="PAY-SASPAY-1",
            method=self.method,
            status="pending",
            provider_raw_response={
                "type": "order",
                "service_amount": "50.00",
                "bujito_reference": "PAY-SASPAY-1",
            },
        )

    def _sign(self, body: bytes, secret: str, ts: str | None = None) -> tuple[str, str]:
        timestamp = ts or str(int(time.time()))
        signed = f"{timestamp}.".encode() + body
        sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return timestamp, sig

    @override_settings(
        DEBUG=False,
        SASPAY_WEBHOOK_SECRET="saspay-secret",
        PAYMENT_WEBHOOK_SECRET="",
    )
    def test_signed_transaction_success_completes_payment(self):
        payload = {
            "event": "transaction.success",
            "data": {
                "id": "tx-abc",
                "status": "SUCCESS",
                "amount": "50.00",
                "net_amount": "50.00",
                "currency": "USD",
                "metadata": {"bujito_reference": "PAY-SASPAY-1"},
            },
        }
        body = json.dumps(payload).encode()
        ts, sig = self._sign(body, "saspay-secret")
        response = self.client.post(
            reverse("payment-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=sig,
            HTTP_X_WEBHOOK_TIMESTAMP=ts,
            HTTP_X_WEBHOOK_EVENT="transaction.success",
        )
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "completed")
        self.assertEqual(self.payment.external_id, "tx-abc")

    @override_settings(
        DEBUG=False,
        SASPAY_WEBHOOK_SECRET="saspay-secret",
        PAYMENT_WEBHOOK_SECRET="",
    )
    def test_stale_timestamp_rejected(self):
        body = b'{"event":"webhook.test","data":{}}'
        ts, sig = self._sign(body, "saspay-secret", ts=str(int(time.time()) - 900))
        self.assertFalse(verify_saspay_webhook(body, sig, ts, "saspay-secret"))
        response = self.client.post(
            reverse("payment-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=sig,
            HTTP_X_WEBHOOK_TIMESTAMP=ts,
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(
        DEBUG=False,
        SASPAY_WEBHOOK_SECRET="saspay-secret",
        PAYMENT_WEBHOOK_SECRET="",
    )
    def test_webhook_test_event_acks(self):
        payload = {"event": "webhook.test", "data": {"ok": True}}
        body = json.dumps(payload).encode()
        ts, sig = self._sign(body, "saspay-secret")
        response = self.client.post(
            reverse("payment-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=sig,
            HTTP_X_WEBHOOK_TIMESTAMP=ts,
            HTTP_X_WEBHOOK_EVENT="webhook.test",
        )
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
