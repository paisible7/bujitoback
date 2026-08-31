from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from users.models import CustomUser

from .fulfillment import provision_order_parcels
from .models import Order
from .quote_utils import parse_product_items
from .serializers import OrderQuoteSerializer


class OrderQuoteSerializerTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="photo@example.com",
            password="test-password",
        )
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

    def test_photo_only_order_can_receive_quote(self):
        order = Order.objects.create(user=self.user)
        serializer = OrderQuoteSerializer(
            order,
            data={
                "product_items": [
                    {
                        "description": "Produit présenté sur la photo",
                        "quantity": 2,
                        "price": "12.50",
                    }
                ],
                "withdrawal_fee": "5.00",
                "expected_parcel_count": 3,
            },
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        quoted_order = serializer.save()

        self.assertTrue(quoted_order.quote_ready)
        self.assertEqual(quoted_order.status, "pending")
        self.assertEqual(quoted_order.expected_parcel_count, 3)
        self.assertEqual(quoted_order.total_amount, Decimal("30.00"))
        items = parse_product_items(quoted_order.product_links)
        self.assertEqual(items[0]["description"], "Produit présenté sur la photo")
        self.assertEqual(items[0]["url"], "")


class ParcelProvisioningTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="client@example.com",
            password="test-password",
            full_name="Client Test",
            phone_number="+243810001234",
        )
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

    def test_provisioning_is_idempotent(self):
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("45.00"),
            expected_parcel_count=3,
        )

        first = provision_order_parcels(order.pk, notify=False)
        second = provision_order_parcels(order.pk, notify=False)

        self.assertEqual(first.created_count, 3)
        self.assertEqual(second.created_count, 0)
        self.assertEqual(order.parcels.count(), 3)
        self.assertEqual(
            set(order.parcels.values_list("order_sequence", flat=True)),
            {1, 2, 3},
        )
        self.assertEqual(
            set(order.parcels.values_list("status", flat=True)),
            {"awaiting_arrival"},
        )
        self.assertEqual(
            order.parcels.values("tracking_number").distinct().count(),
            3,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, "processing")

    def test_generated_parcels_become_groupable_after_arrival(self):
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("45.00"),
            expected_parcel_count=2,
        )
        provision_order_parcels(order.pk, notify=False)
        tracking_numbers = list(
            order.parcels.values_list("tracking_number", flat=True)
        )
        client = APIClient()
        client.force_authenticate(self.user)

        before_arrival = client.post(
            reverse("parcel-group"),
            {"tracking_numbers": tracking_numbers},
            format="json",
        )
        self.assertEqual(before_arrival.status_code, 400)

        order.parcels.update(status="pending")
        after_arrival = client.post(
            reverse("parcel-group"),
            {"tracking_numbers": tracking_numbers},
            format="json",
        )
        self.assertEqual(after_arrival.status_code, 201)

    def test_import_updates_generated_parcel_without_duplicate(self):
        admin = CustomUser.objects.create_user(
            email="admin@example.com",
            password="test-password",
            role="admin",
            is_staff=True,
        )
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("45.00"),
            expected_parcel_count=2,
        )
        provision_order_parcels(order.pk, notify=False)
        generated = order.parcels.get(order_sequence=1)
        internal_tracking = generated.tracking_number
        client = APIClient()
        client.force_authenticate(admin)

        response = client.post(
            reverse("parcel-bulk-import"),
            {
                "parcels": [
                    {
                        "tracking_number": "SUPPLIER-TRACK-001",
                        "status": "pending",
                        "order": order.pk,
                        "order_sequence": 1,
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.parcels.count(), 2)
        generated.refresh_from_db()
        self.assertEqual(generated.tracking_number, internal_tracking)
        self.assertEqual(
            generated.supplier_tracking_number,
            "SUPPLIER-TRACK-001",
        )
        self.assertEqual(generated.status, "pending")
