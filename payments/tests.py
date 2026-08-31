from decimal import Decimal
from unittest.mock import patch

from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from parcels.models import Order
from users.models import CustomUser

from .models import Payment, PaymentMethod


class PaymentInitiationTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="payer@example.com",
            password="test-password",
        )
        self.method = PaymentMethod.objects.create(
            name="Carte",
            code="card",
            is_active=True,
        )
        self.client.force_authenticate(self.user)
        self.signal_notification = patch(
            "parcels.signals.send_fcm_notification",
        )
        self.signal_admin_notification = patch(
            "parcels.signals.notify_admins",
        )
        self.signal_notification.start()
        self.signal_admin_notification.start()
        self.addCleanup(self.signal_notification.stop)
        self.addCleanup(self.signal_admin_notification.stop)

    @patch(
        "payments.views.PaymentService.initiate_payment",
        return_value="https://checkout.example.test",
    )
    def test_quote_ready_order_can_only_have_one_pending_payment(self, _mock):
        PaymentMethod.objects.create(name="Orange Money", code="orange_money", is_active=True)
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("25.00"),
        )
        payload = {
            "order_id": order.pk,
            "method": "orange_money",
            "phone_number": "0700000000",
        }

        first = self.client.post(reverse("payment-initiate"), payload)
        second = self.client.post(reverse("payment-initiate"), payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(Payment.objects.get(order=order).status, "pending")

    def test_card_payment_completes_in_app_without_redirect(self):
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("25.00"),
        )

        response = self.client.post(
            reverse("payment-initiate"),
            {"order_id": order.pk, "method": "card"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload.get("redirect_url"))
        self.assertEqual(payload["transaction"]["status"], "completed")
        self.assertEqual(Payment.objects.get(order=order).status, "completed")

    def test_card_payment_completes_existing_pending_payment(self):
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("25.00"),
        )
        Payment.objects.create(
            user=self.user,
            order=order,
            amount=Decimal("25.00"),
            currency="USD",
            reference="PAY-STUCK-PENDING",
            method=self.method,
            status="pending",
        )

        response = self.client.post(
            reverse("payment-initiate"),
            {"order_id": order.pk, "method": "card"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(Payment.objects.get(order=order).status, "completed")

    def test_client_cannot_list_all_payments(self):
        response = self.client.get(reverse("payment-manage"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_all_payments(self):
        admin = CustomUser.objects.create_user(
            email="admin-pay@example.com",
            password="test-password",
            role="admin",
        )
        Payment.objects.create(
            user=self.user,
            amount=Decimal("25.00"),
            currency="USD",
            reference="PAY-ADMIN-LIST",
            method=self.method,
            status="completed",
        )
        self.client.force_authenticate(admin)

        response = self.client.get(reverse("payment-manage"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["user_email"], self.user.email)

    def test_order_without_quote_cannot_be_paid(self):
        order = Order.objects.create(user=self.user)

        response = self.client.post(
            reverse("payment-initiate"),
            {"order_id": order.pk, "method": "card"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(order=order).exists())


class PaymentCompletionSignalTests(TransactionTestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="confirmed@example.com",
            password="test-password",
        )
        self.method = PaymentMethod.objects.create(
            name="Carte",
            code="card",
            is_active=True,
        )
        self.signal_notification = patch(
            "parcels.signals.send_fcm_notification",
        )
        self.signal_admin_notification = patch(
            "parcels.signals.notify_admins",
        )
        self.fulfillment_notification = patch(
            "parcels.fulfillment.send_fcm_notification",
        )
        self.fulfillment_admin_notification = patch(
            "parcels.fulfillment.notify_admins",
        )
        self.signal_notification.start()
        self.signal_admin_notification.start()
        self.fulfillment_notification.start()
        self.fulfillment_admin_notification.start()
        self.addCleanup(self.signal_notification.stop)
        self.addCleanup(self.signal_admin_notification.stop)
        self.addCleanup(self.fulfillment_notification.stop)
        self.addCleanup(self.fulfillment_admin_notification.stop)

    def test_completed_payment_generates_expected_parcels_once(self):
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("60.00"),
            expected_parcel_count=2,
        )
        payment = Payment.objects.create(
            user=self.user,
            order=order,
            amount=Decimal("60.00"),
            currency="USD",
            reference="PAY-TEST-COMPLETE",
            method=self.method,
            status="pending",
        )

        payment.status = "completed"
        payment.save(update_fields=["status", "updated_at"])

        self.assertEqual(order.parcels.count(), 2)
        payment.save(update_fields=["status", "updated_at"])
        self.assertEqual(order.parcels.count(), 2)
        order.refresh_from_db()
        self.assertEqual(order.status, "processing")

    def test_card_initiate_provisions_parcels(self):
        client = APIClient()
        client.force_authenticate(self.user)
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("40.00"),
            expected_parcel_count=2,
        )

        response = client.post(
            reverse("payment-initiate"),
            {"order_id": order.pk, "method": "card"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.parcels.count(), 2)
        order.refresh_from_db()
        self.assertEqual(order.status, "processing")

    @override_settings(DEBUG=True, PAYMENT_WEBHOOK_SECRET="")
    def test_replayed_webhook_does_not_duplicate_parcels(self):
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("80.00"),
            expected_parcel_count=2,
        )
        payment = Payment.objects.create(
            user=self.user,
            order=order,
            amount=Decimal("80.00"),
            currency="USD",
            reference="PAY-TEST-WEBHOOK",
            method=self.method,
            status="pending",
        )
        client = self.client_class()
        payload = {"reference": payment.reference, "status": "completed"}

        first = client.post(reverse("payment-webhook"), payload)
        second = client.post(reverse("payment-webhook"), payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(order.parcels.count(), 2)

    @override_settings(DEBUG=False, PAYMENT_WEBHOOK_SECRET="webhook-secret")
    def test_unsigned_production_webhook_is_rejected(self):
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("80.00"),
            expected_parcel_count=2,
        )
        payment = Payment.objects.create(
            user=self.user,
            order=order,
            amount=Decimal("80.00"),
            currency="USD",
            reference="PAY-TEST-UNSIGNED",
            method=self.method,
            status="pending",
        )

        response = self.client.post(
            reverse("payment-webhook"),
            {"reference": payment.reference, "status": "completed"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(order.parcels.exists())
