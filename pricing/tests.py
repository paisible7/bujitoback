from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from users.models import CustomUser

from .models import BusinessSettings
from .utils import billable_weight_kg, grouping_cost, shipping_cost


class BillableWeightTests(TestCase):
    def test_rounds_up_to_half_kg(self):
        self.assertEqual(billable_weight_kg("0.2"), Decimal("0.5"))
        self.assertEqual(billable_weight_kg("0.6"), Decimal("1.0"))
        self.assertEqual(billable_weight_kg("1"), Decimal("1.0"))
        self.assertEqual(billable_weight_kg("1.01"), Decimal("1.5"))


class ShippingCostTests(TestCase):
    def setUp(self):
        self.cfg = BusinessSettings.load()

    def test_ordinary(self):
        result = shipping_cost(category="ordinary", weight_kg="0.2", settings=self.cfg)
        self.assertEqual(result["billable_kg"], 0.5)
        self.assertEqual(result["amount_usd"], 8.5)  # 0.5 * 17
        self.assertEqual(result["days"], 21)

    def test_sensitive(self):
        result = shipping_cost(category="sensitive", weight_kg="1", settings=self.cfg)
        self.assertEqual(result["amount_usd"], 25.0)

    def test_phone_flat(self):
        result = shipping_cost(category="phone", settings=self.cfg)
        self.assertEqual(result["amount_usd"], 36.0)

    def test_express_unavailable(self):
        result = shipping_cost(category="express", weight_kg="1", settings=self.cfg)
        self.assertFalse(result["available"])


class GroupingCostTests(TestCase):
    def setUp(self):
        self.cfg = BusinessSettings.load()

    def test_flat_tier(self):
        result = grouping_cost(weight_kg="3.2", settings=self.cfg)
        self.assertEqual(result["billable_kg"], 3.5)
        self.assertEqual(result["amount_usd"], 5.0)

    def test_per_kg_tier(self):
        result = grouping_cost(weight_kg="5", settings=self.cfg)
        self.assertEqual(result["amount_usd"], 12.5)  # 5 * 2.5


class PricingApiTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="client@example.com",
            password="test-password",
        )
        self.admin = CustomUser.objects.create_user(
            email="admin@example.com",
            password="test-password",
            role="admin",
        )
        BusinessSettings.load()

    def test_client_can_read_settings(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/pricing/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(response.data["ordinary_rate_per_kg"]), 17.0)

    def test_client_cannot_patch(self):
        self.client.force_authenticate(self.user)
        response = self.client.patch(
            "/api/pricing/settings/",
            {"usd_to_cdf": "2500"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_patch_rate(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            "/api/pricing/settings/",
            {"usd_to_cdf": "2500"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(response.data["usd_to_cdf"]), 2500.0)

    def test_estimate_shipping(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/pricing/estimate/",
            {"kind": "shipping", "category": "ordinary", "weight_kg": "0.2"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["billable_kg"], 0.5)
        self.assertEqual(response.data["amount_usd"], 8.5)
