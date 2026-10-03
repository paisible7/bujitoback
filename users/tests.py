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
