from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from payments.models import Payment, PaymentMethod
from users.roles import ROLE_ADMIN, ROLE_SUPERUSER

User = get_user_model()


class AdminReportsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='admin-reports@bujito.com',
            password='Pass123!',
            role=ROLE_ADMIN,
            full_name='Admin Reports',
        )
        self.client_user = User.objects.create_user(
            email='client-reports@bujito.com',
            password='Pass123!',
            full_name='Client Reports',
            phone_number='+243800000001',
            city='Kinshasa',
        )
        self.method, _ = PaymentMethod.objects.get_or_create(
            code='card',
            defaults={'name': 'Carte', 'is_active': True},
        )
        Payment.objects.create(
            user=self.client_user,
            amount=Decimal('10.00'),
            currency='USD',
            reference='REP-STATS-1',
            method=self.method,
            status='completed',
        )
        Payment.objects.create(
            user=self.client_user,
            amount=Decimal('5.00'),
            currency='USD',
            reference='REP-STATS-2',
            method=self.method,
            status='pending',
        )
        self.signal_notification = patch('parcels.signals.send_fcm_notification')
        self.signal_admin_notification = patch('parcels.signals.notify_admins')
        self.signal_notification.start()
        self.signal_admin_notification.start()
        self.addCleanup(self.signal_notification.stop)
        self.addCleanup(self.signal_admin_notification.stop)

    def test_stats_requires_admin(self):
        self.client.force_authenticate(self.client_user)
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.status_code, 403)

    def test_stats_returns_kpis_and_series(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('clients_count', data)
        self.assertIn('payments_by_day', data)
        self.assertIn('orders_by_status', data)
        self.assertIn('parcels_by_status', data)
        self.assertIn('revenue_by_method', data)
        self.assertGreaterEqual(data['payments']['completed_count'], 1)
        self.assertGreaterEqual(data['payments']['pending_count'], 1)

    def test_accounting_and_csv_export(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/admin/accounting/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('totals', data)
        self.assertIn('results', data)
        self.assertGreaterEqual(data['count'], 2)

        csv_response = self.client.get('/api/admin/accounting/export.csv')
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn('text/csv', csv_response['Content-Type'])
        body = csv_response.content.decode('utf-8-sig')
        self.assertIn('reference', body)
        self.assertIn('REP-STATS-1', body)

    def test_client_service_search(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            '/api/admin/client-service/',
            {'search': 'client-reports'},
        )
        self.assertEqual(response.status_code, 200)
        results = response.json().get('results', [])
        self.assertTrue(any(r['email'] == 'client-reports@bujito.com' for r in results))
        card = next(r for r in results if r['email'] == 'client-reports@bujito.com')
        self.assertIn('china_warehouse_address', card)
        self.assertIn('recent_payments', card)

    def test_stats_invalid_dates_ignored(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            '/api/admin/stats/',
            {'from': 'not-a-date', 'to': 'also-bad'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('payments_by_day', response.json())

    def test_accounting_type_filters(self):
        self.client.force_authenticate(self.admin)
        for type_name in ('all', 'order', 'transfer', 'expedition'):
            response = self.client.get(
                '/api/admin/accounting/',
                {'type': type_name},
            )
            self.assertEqual(response.status_code, 200, type_name)
            self.assertEqual(response.json()['type'], type_name)

    def test_accounting_pagination_bounds(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            '/api/admin/accounting/',
            {'page': '0', 'page_size': '9999'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['page'], 1)
        self.assertLessEqual(data['page_size'], 100)

    def test_unauthenticated_reports_rejected(self):
        for url in (
            '/api/admin/stats/',
            '/api/admin/accounting/',
            '/api/admin/accounting/export.csv',
            '/api/admin/client-service/',
        ):
            response = self.client.get(url)
            self.assertIn(response.status_code, (401, 403), url)
