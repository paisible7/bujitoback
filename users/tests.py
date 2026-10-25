from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from parcels.models import Order, Parcel
from pricing.models import BusinessSettings

User = get_user_model()


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='client@bujito.com',
            password='OldPass123!',
            full_name='Client Test',
        )

    def test_verify_accepts_known_email(self):
        response = self.client.post(
            '/api/auth/password-reset/verify/',
            {'email': 'client@bujito.com'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_verify_rejects_unknown_email(self):
        response = self.client.post(
            '/api/auth/password-reset/verify/',
            {'email': 'unknown@bujito.com'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_reset_updates_password(self):
        response = self.client.post(
            '/api/auth/password-reset/',
            {
                'email': 'client@bujito.com',
                'password': 'NewPass456!',
                'confirm_password': 'NewPass456!',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456!'))
        self.assertFalse(self.user.check_password('OldPass123!'))

    def test_reset_rejects_password_mismatch(self):
        response = self.client.post(
            '/api/auth/password-reset/',
            {
                'email': 'client@bujito.com',
                'password': 'NewPass456!',
                'confirm_password': 'OtherPass456!',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)


class ProfileCountsAndAddressesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='counts@bujito.com',
            password='Pass123!',
            full_name='Client Counts',
            phone_number='+243811111111',
            city='Kinshasa',
        )
        settings = BusinessSettings.load()
        settings.china_air_address = 'Air Address Guangzhou'
        settings.china_sea_address = 'Sea Address Ningbo'
        settings.save()
        self.signal_notification = patch('parcels.signals.send_fcm_notification')
        self.signal_admin_notification = patch('parcels.signals.notify_admins')
        self.signal_notification.start()
        self.signal_admin_notification.start()
        self.addCleanup(self.signal_notification.stop)
        self.addCleanup(self.signal_admin_notification.stop)

        order = Order.objects.create(user=self.user, quote_ready=True)
        Parcel.objects.create(
            order=order,
            tracking_number='TRK-RCV-1',
            status='pending',
        )
        Parcel.objects.create(
            order=order,
            tracking_number='TRK-RCV-2',
            status='consolidated',
        )
        Parcel.objects.create(
            order=order,
            tracking_number='TRK-SENT-1',
            status='in_transit',
        )
        Parcel.objects.create(
            order=order,
            tracking_number='TRK-SENT-2',
            status='delivered',
        )
        Parcel.objects.create(
            order=order,
            tracking_number='TRK-WAIT-1',
            status='awaiting_arrival',
        )

    def test_profile_exposes_received_sent_counts_and_addresses(self):
        self.client.force_authenticate(self.user)
        response = self.client.get('/api/auth/profile/')
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data['parcels_count'], 5)
        self.assertEqual(data['parcels_received_count'], 2)
        self.assertEqual(data['parcels_sent_count'], 2)
        self.assertIn('Air Address Guangzhou', data['china_air_address'])
        self.assertIn('Sea Address Ningbo', data['china_sea_address'])
        self.assertIn('BU.Client Counts', data['china_warehouse_address'])

class ProfilePhotoAndAgentAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superuser = User.objects.create_user(
            email='super@bujito.com',
            password='Pass123!',
            role='superuser',
            full_name='Super Admin',
        )
        self.agent = User.objects.create_user(
            email='agent@bujito.com',
            password='Pass123!',
            role='admin',
            full_name='Agent Admin',
        )
        self.client_user = User.objects.create_user(
            email='photo@bujito.com',
            password='Pass123!',
            full_name='Photo Client',
        )

    def _make_image(self):
        buf = BytesIO()
        Image.new('RGB', (8, 8), color=(255, 200, 0)).save(buf, format='JPEG')
        return SimpleUploadedFile('avatar.jpg', buf.getvalue(), content_type='image/jpeg')

    def test_profile_photo_upload(self):
        self.client.force_authenticate(self.client_user)
        response = self.client.patch(
            '/api/auth/profile/',
            {
                'full_name': 'Photo Client Updated',
                'profile_photo': self._make_image(),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['full_name'], 'Photo Client Updated')
        self.assertTrue(response.data.get('profile_photo_url'))
        self.client_user.refresh_from_db()
        self.assertTrue(bool(self.client_user.profile_photo))

    def test_superuser_can_patch_agent_permissions(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.patch(
            f'/api/auth/users/{self.agent.id}/',
            {'admin_permissions': ['stats', 'accounting'], 'is_active': True},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.agent.refresh_from_db()
        self.assertEqual(
            sorted(self.agent.admin_permissions or []),
            ['accounting', 'stats'],
        )

    def test_superuser_can_patch_worker_percentages_and_status(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.patch(
            f'/api/auth/users/{self.agent.id}/',
            {
                'service_percentages': {'orders': 5, 'client_service': 6, 'bad': 9},
                'worker_status': 'pending',
                'permissions_restricted': True,
                'admin_permissions': ['client_service'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.service_percentages, {'orders': 5.0, 'client_service': 6.0})
        self.assertEqual(self.agent.worker_status, 'pending')
        self.assertFalse(self.agent.is_active)
        self.assertTrue(self.agent.permissions_restricted)
        self.assertEqual(response.data['service_percentages']['orders'], 5.0)
        self.assertIsNone(response.data.get('last_salary_payment'))

    def test_superuser_records_salary_and_worker_sees_it(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.post(
            f'/api/auth/users/{self.agent.id}/salary/',
            {
                'amount': '120.50',
                'currency': 'USD',
                'service': 'orders',
                'note': 'Octobre',
                'proof_image': self._make_image(),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(str(response.data['amount']), '120.50')
        self.assertTrue(response.data.get('proof_url'))

        self.client.force_authenticate(self.agent)
        profile = self.client.get('/api/auth/profile/')
        self.assertEqual(profile.status_code, 200)
        last = profile.data.get('last_salary_payment')
        self.assertIsNotNone(last)
        self.assertEqual(str(last['amount']), '120.50')
        self.assertTrue(last.get('proof_url'))
        mine = self.client.get('/api/auth/profile/salary/')
        self.assertEqual(mine.status_code, 200)
        self.assertIn('results', mine.data)
        self.assertEqual(len(mine.data['results']), 1)
        # Sans encaissement, le solde dû reste 0 (paiement manuel hors accruals).
        self.assertEqual(mine.data['month_total'], 0)
        from reports.models import Expense

        self.assertTrue(
            Expense.objects.filter(category='Salaire', amount='120.50').exists()
        )

    def test_salary_accrual_from_collections_and_multi_pay(self):
        """Commission auto = encaissé × % ; paiement multi remet le solde à 0."""
        from payments.models import Payment, PaymentMethod

        self.agent.service_percentages = {'orders': 2, 'grouping': 5}
        self.agent.save(update_fields=['service_percentages'])

        method = PaymentMethod.objects.create(name='Test', code='test_cash')
        client = User.objects.create_user(
            email='buyer@bujito.com',
            password='Pass123!',
            full_name='Buyer',
        )
        order = Order.objects.create(user=client, quote_ready=True, total_amount=1000)
        Payment.objects.create(
            user=client,
            order=order,
            amount='1000.00',
            currency='USD',
            reference='PAY-ORD-1',
            method=method,
            status='completed',
            provider_raw_response={'type': 'order', 'service_amount': 1000},
        )

        self.client.force_authenticate(self.agent)
        dash = self.client.get('/api/auth/profile/salary/')
        self.assertEqual(dash.status_code, 200)
        # 1000$ × 2% = 20$
        self.assertEqual(dash.data['month_total'], 20.0)
        orders_row = next(
            s for s in dash.data['by_service'] if s['service'] == 'orders'
        )
        self.assertEqual(orders_row['balance'], 20.0)
        self.assertEqual(orders_row['collected'], 1000.0)

        self.client.force_authenticate(self.superuser)
        pay = self.client.post(
            f'/api/auth/users/{self.agent.id}/salary/',
            {'services': ['orders', 'grouping'], 'note': 'Paiement multi'},
            format='json',
        )
        self.assertEqual(pay.status_code, 201)
        self.assertEqual(len(pay.data['results']), 1)  # grouping solde 0 → ignoré
        self.assertEqual(float(pay.data['results'][0]['amount']), 20.0)

        self.client.force_authenticate(self.agent)
        after = self.client.get('/api/auth/profile/salary/')
        self.assertEqual(after.data['month_total'], 0)
        orders_after = next(
            s for s in after.data['by_service'] if s['service'] == 'orders'
        )
        self.assertEqual(orders_after['balance'], 0)

    def test_expenses_and_losses_reduce_commission_base(self):
        """Dépenses + pertes diminuent l’encaissé net avant le %."""
        from payments.models import Payment, PaymentMethod
        from reports.models import Expense

        self.agent.service_percentages = {'orders': 10}
        self.agent.save(update_fields=['service_percentages'])

        method = PaymentMethod.objects.create(name='Cash2', code='test_cash_2')
        client = User.objects.create_user(
            email='buyer2@bujito.com',
            password='Pass123!',
            full_name='Buyer2',
        )
        order = Order.objects.create(user=client, quote_ready=True, total_amount=1000)
        Payment.objects.create(
            user=client,
            order=order,
            amount='1000.00',
            currency='USD',
            reference='PAY-ORD-2',
            method=method,
            status='completed',
            provider_raw_response={'type': 'order', 'service_amount': 1000},
        )
        Expense.objects.create(
            name='Fournisseur',
            category='Logistique',
            entry_type=Expense.ENTRY_EXPENSE,
            amount='80.00',
            currency='USD',
            recorded_by=self.superuser,
        )
        Expense.objects.create(
            name='Casse',
            category='Perte',
            entry_type=Expense.ENTRY_LOSS,
            amount='20.00',
            currency='USD',
            recorded_by=self.superuser,
        )
        # Miroir salaire : ne doit PAS réduire la base.
        Expense.objects.create(
            name='Agent',
            category='Salaire',
            entry_type=Expense.ENTRY_EXPENSE,
            amount='50.00',
            currency='USD',
            recorded_by=self.superuser,
        )

        self.client.force_authenticate(self.agent)
        dash = self.client.get('/api/auth/profile/salary/')
        self.assertEqual(dash.status_code, 200)
        # Net = 1000 − 80 − 20 = 900 ; 10 % = 90
        self.assertEqual(dash.data['collected_gross_total'], 1000.0)
        self.assertEqual(dash.data['deductions_total'], 100.0)
        self.assertEqual(dash.data['collected_total'], 900.0)
        self.assertEqual(dash.data['month_total'], 90.0)

    def test_admin_cannot_patch_agent_permissions(self):
        other = User.objects.create_user(
            email='other-admin@bujito.com',
            password='Pass123!',
            role='admin',
        )
        self.client.force_authenticate(other)
        response = self.client.patch(
            f'/api/auth/users/{self.agent.id}/',
            {'admin_permissions': ['stats']},
            format='json',
        )
        self.assertNotEqual(response.status_code, 200)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.admin_permissions, [])

    def test_accountant_can_pay_salary_but_not_edit_permissions(self):
        accountant = User.objects.create_user(
            email='accountant@bujito.com',
            password='Pass123!',
            role='admin',
            full_name='Comptable',
            permissions_restricted=True,
            admin_permissions=['accounting', 'payments', 'stats'],
        )
        self.client.force_authenticate(accountant)
        pay = self.client.post(
            f'/api/auth/users/{self.agent.id}/salary/',
            {
                'amount': '80.00',
                'currency': 'USD',
                'service': 'orders',
                'note': 'Paie comptable',
            },
            format='multipart',
        )
        self.assertEqual(pay.status_code, 201, pay.data)
        self.assertEqual(str(pay.data['amount']), '80.00')

        listed = self.client.get('/api/auth/users/', {'role': 'admin'})
        self.assertEqual(listed.status_code, 200)
        payload = listed.data
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        emails = [u['email'] for u in rows]
        self.assertIn(self.agent.email, emails)

        blocked = self.client.patch(
            f'/api/auth/users/{self.agent.id}/',
            {'admin_permissions': ['stats'], 'service_percentages': {'orders': 9}},
            format='json',
        )
        self.assertNotEqual(blocked.status_code, 200)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.admin_permissions, [])


class AdminRolePermissionHelperTests(TestCase):
    def test_presets_and_helpers(self):
        from users.admin_permissions import (
            ADMIN_ROLE_PRESETS,
            PERM_ACCOUNTING,
            PERM_EXPENSES_CHINA,
            PERM_SHIPMENTS,
            PERM_SHIPMENTS_RECEPTION,
            can_manage_china_expenses,
            can_pay_worker_salary,
            can_view_full_accounting,
            is_shipments_reception_only,
        )

        self.assertEqual(
            set(ADMIN_ROLE_PRESETS['parcel_manager']),
            {'grouping', 'shipments', 'parcels', 'import', 'expenses_china'},
        )
        self.assertEqual(
            set(ADMIN_ROLE_PRESETS['reception']),
            {PERM_SHIPMENTS_RECEPTION},
        )

        accountant = User.objects.create_user(
            email='acc-helper@bujito.com',
            password='Pass123!',
            role='admin',
            permissions_restricted=True,
            admin_permissions=list(ADMIN_ROLE_PRESETS['accountant']),
        )
        parcel_mgr = User.objects.create_user(
            email='parcel-helper@bujito.com',
            password='Pass123!',
            role='admin',
            permissions_restricted=True,
            admin_permissions=list(ADMIN_ROLE_PRESETS['parcel_manager']),
        )
        reception = User.objects.create_user(
            email='recep-helper@bujito.com',
            password='Pass123!',
            role='admin',
            permissions_restricted=True,
            admin_permissions=list(ADMIN_ROLE_PRESETS['reception']),
        )

        self.assertTrue(can_pay_worker_salary(accountant))
        self.assertTrue(can_view_full_accounting(accountant))
        self.assertTrue(can_manage_china_expenses(accountant))
        self.assertFalse(is_shipments_reception_only(accountant))

        self.assertFalse(can_pay_worker_salary(parcel_mgr))
        self.assertFalse(can_view_full_accounting(parcel_mgr))
        self.assertTrue(can_manage_china_expenses(parcel_mgr))
        self.assertFalse(is_shipments_reception_only(parcel_mgr))

        self.assertTrue(is_shipments_reception_only(reception))
        self.assertFalse(can_manage_china_expenses(reception))
        self.assertFalse(can_view_full_accounting(reception))
        # Avec shipments complet, pas « réception seule ».
        parcel_mgr.admin_permissions = [PERM_SHIPMENTS, PERM_SHIPMENTS_RECEPTION]
        parcel_mgr.save(update_fields=['admin_permissions'])
        self.assertFalse(is_shipments_reception_only(parcel_mgr))
        self.assertIn(PERM_ACCOUNTING, ADMIN_ROLE_PRESETS['accountant'])
        self.assertIn(PERM_EXPENSES_CHINA, ADMIN_ROLE_PRESETS['parcel_manager'])
