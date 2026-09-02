from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

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
