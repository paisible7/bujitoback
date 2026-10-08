from io import BytesIO
from tempfile import TemporaryDirectory
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from pricing.models import BusinessSettings
from users.models import CustomUser

from .expedition_utils import build_expedition_quote, parcel_shipping_category
from .fulfillment import provision_order_parcels
from .models import Order, Parcel
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
                "commission_fee": "2.50",
                "expected_parcel_count": 3,
            },
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        quoted_order = serializer.save()

        self.assertTrue(quoted_order.quote_ready)
        self.assertEqual(quoted_order.status, "pending")
        self.assertEqual(quoted_order.expected_parcel_count, 3)
        self.assertEqual(quoted_order.total_amount, Decimal("32.50"))
        self.assertEqual(quoted_order.commission_fee, Decimal("2.50"))
        items = parse_product_items(quoted_order.product_links)
        self.assertEqual(items[0]["description"], "Produit présenté sur la photo")
        self.assertEqual(items[0]["url"], "")


class OrderPhotoUploadTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="order-photo@example.com",
            password="test-password",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _image(self, name):
        image = BytesIO()
        Image.new("RGB", (8, 8), color=(255, 200, 0)).save(image, format="JPEG")
        return SimpleUploadedFile(name, image.getvalue(), content_type="image/jpeg")

    def test_order_creation_accepts_single_and_multiple_photo_field_names(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("order-list-create"),
                    {
                        "client_name": "Photo Client",
                        "images": [self._image("product-1.jpg"), self._image("product-2.jpg")],
                    },
                    format="multipart",
                )

                self.assertEqual(response.status_code, 201, response.data)
                order = Order.objects.get(pk=response.data["id"])
                self.assertEqual(order.images.count(), 2)
                self.assertTrue(all(image.image.storage.exists(image.image.name) for image in order.images.all()))

    def test_order_creation_with_packages_and_photos(self):
        """Mimique l'envoi Flutter: packages JSON + images multipart."""
        import json

        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                packages = json.dumps(
                    [
                        {
                            "description": "Produit sur photo",
                            "comment": "Produit sur photo",
                            "links": [],
                        }
                    ]
                )
                response = self.client.post(
                    reverse("order-list-create"),
                    {
                        "client_name": "Photo Client",
                        "city": "Kinshasa",
                        "country": "CD",
                        "packages": packages,
                        "expected_parcel_count": "1",
                        "quantity": "1",
                        "image_package_indexes": "0",
                        "images": self._image("package-photo.jpg"),
                    },
                    format="multipart",
                )

                self.assertEqual(response.status_code, 201, response.data)
                order = Order.objects.get(pk=response.data["id"])
                self.assertEqual(order.images.count(), 1)
                self.assertEqual(order.images.first().package_index, 0)
                self.assertEqual(order.expected_parcel_count, 1)
                self.assertTrue(
                    order.images.first().image.storage.exists(
                        order.images.first().image.name
                    )
                )


class ComputerExpeditionPricingTests(TestCase):
    def test_computer_parcels_are_charged_per_piece_without_weight(self):
        parcels = [
            Parcel.objects.create(
                tracking_number=f'COMPUTER-{index}',
                description='Ordinateur portable',
            )
            for index in (1, 2)
        ]

        self.assertEqual(parcel_shipping_category(parcels[0]), 'computer')
        quote = build_expedition_quote(
            parcels=parcels,
            mode='bujito_digital',
            transport_mode='air',
            settings=BusinessSettings.load(),
        )

        self.assertEqual(quote['shipping_category'], 'computer')
        self.assertEqual(quote['shipping_fee'], 200.0)
        self.assertEqual(quote['total_due_now'], 200.0)


class OrderStatusSyncTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="sync@example.com",
            password="test-password",
        )
        self.signal_notification = patch("parcels.signals.send_fcm_notification")
        self.signal_admin_notification = patch("parcels.signals.notify_admins")
        self.signal_notification.start()
        self.signal_admin_notification.start()
        self.addCleanup(self.signal_notification.stop)
        self.addCleanup(self.signal_admin_notification.stop)

    def test_order_status_follows_parcel_progression(self):
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("20.00"),
            expected_parcel_count=1,
        )
        provision_order_parcels(order.pk, notify=False)
        order.refresh_from_db()
        self.assertEqual(order.status, "processing")

        parcel = order.parcels.get()
        parcel.status = "pending"
        parcel.save(update_fields=["status", "last_updated"])
        order.refresh_from_db()
        self.assertEqual(order.status, "processing")

        parcel.status = "in_transit"
        parcel.save(update_fields=["status", "last_updated"])
        order.refresh_from_db()
        self.assertEqual(order.status, "shipped")

        parcel.status = "delivered"
        parcel.save(update_fields=["status", "last_updated"])
        order.refresh_from_db()
        self.assertEqual(order.status, "delivered")

    def test_manual_order_status_is_rejected_when_parcels_exist(self):
        admin = CustomUser.objects.create_user(
            email="admin-sync@example.com",
            password="test-password",
            role="admin",
            is_staff=True,
        )
        order = Order.objects.create(
            user=self.user,
            quote_ready=True,
            total_amount=Decimal("20.00"),
            expected_parcel_count=1,
        )
        provision_order_parcels(order.pk, notify=False)
        client = APIClient()
        client.force_authenticate(admin)

        response = client.patch(
            reverse("order-detail", kwargs={"pk": order.pk}),
            {"status": "shipped"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "processing")


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


class OrderPaginationTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="orders-page@example.com",
            password="test-password",
        )
        self.signal_notification = patch("parcels.signals.send_fcm_notification")
        self.signal_admin_notification = patch("parcels.signals.notify_admins")
        self.signal_notification.start()
        self.signal_admin_notification.start()
        self.addCleanup(self.signal_notification.stop)
        self.addCleanup(self.signal_admin_notification.stop)
        for i in range(25):
            Order.objects.create(
                user=self.user,
                status="pending" if i % 2 == 0 else "shipped",
            )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_orders_without_page_return_full_list(self):
        response = self.client.get(reverse("order-list-create"))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 25)

    def test_orders_with_page_are_paginated(self):
        response = self.client.get(
            reverse("order-list-create"),
            {"page": 1, "page_size": 10},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 25)
        self.assertEqual(len(response.data["results"]), 10)

    def test_orders_status_filter_with_pagination(self):
        response = self.client.get(
            reverse("order-list-create"),
            {"page": 1, "page_size": 50, "status": "pending"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 13)
        self.assertTrue(
            all(item["status"] == "pending" for item in response.data["results"])
        )
