from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
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
        from parcels.models import ExpeditionRequest

        exp = ExpeditionRequest.objects.create(
            user=self.client_user,
            mode='bujito_digital',
            transport_mode='air_normal',
            was_grouped=True,
            grouping_fee=Decimal('15.00'),
            total_due_now=Decimal('15.00'),
        )
        Payment.objects.create(
            user=self.client_user,
            expedition=exp,
            amount=Decimal('15.00'),
            currency='USD',
            reference='REP-GRP-1',
            method=self.method,
            status='completed',
            provider_raw_response={
                'type': 'expedition',
                'expedition_id': exp.pk,
                'was_grouped': True,
            },
        )
        self.client.force_authenticate(self.admin)
        for type_name in ('all', 'order', 'transfer', 'expedition', 'grouping'):
            response = self.client.get(
                '/api/admin/accounting/',
                {'type': type_name},
            )
            self.assertEqual(response.status_code, 200, type_name)
            self.assertEqual(response.json()['type'], type_name)
        grouping_res = self.client.get(
            '/api/admin/accounting/',
            {'type': 'grouping'},
        )
        self.assertEqual(grouping_res.status_code, 200)
        refs = [r['reference'] for r in grouping_res.json().get('results', [])]
        self.assertIn('REP-GRP-1', refs)

    def test_accounting_search_and_financial_summary(self):
        self.client.force_authenticate(self.admin)
        image = BytesIO()
        Image.new('RGB', (8, 8), color=(255, 200, 0)).save(image, format='JPEG')
        proof = SimpleUploadedFile(
            'proof.jpg',
            image.getvalue(),
            content_type='image/jpeg',
        )
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                created_expense = self.client.post(
                    '/api/admin/accounting/expenses/',
                    {
                        'name': 'Transporteur',
                        'category': 'Logistique',
                        'amount': '15.00',
                        'currency': 'USD',
                        'expense_date': timezone.localdate().isoformat(),
                        'clients': str(self.client_user.pk),
                        'proof_image': proof,
                    },
                    format='multipart',
                )
                self.assertEqual(
                    created_expense.status_code, 201, created_expense.data
                )
                created_payload = created_expense.json()
                self.assertEqual(
                    created_payload.get('client_names'),
                    ['Client Reports'],
                )
                details = created_payload.get('clients_detail') or []
                self.assertEqual(len(details), 1)
                self.assertEqual(details[0]['id'], self.client_user.pk)
                self.assertEqual(details[0]['full_name'], 'Client Reports')

                response = self.client.get('/api/admin/accounting/')
                self.assertEqual(response.status_code, 200)
                summary = response.json()['financial_summary'][0]
                self.assertEqual(summary['currency'], 'USD')
                self.assertEqual(summary['revenue'], 10.0)
                self.assertEqual(summary['expenses'], 15.0)
                self.assertEqual(summary['losses'], 0.0)
                self.assertEqual(summary['net'], -5.0)
                self.assertEqual(summary['profit'], 0.0)
                self.assertEqual(summary['loss'], 0.0)

                loss_proof = SimpleUploadedFile(
                    'loss.jpg',
                    image.getvalue(),
                    content_type='image/jpeg',
                )
                created_loss = self.client.post(
                    '/api/admin/accounting/expenses/',
                    {
                        'name': 'Colis perdu',
                        'category': 'Perte',
                        'amount': '3.00',
                        'currency': 'USD',
                        'entry_type': 'loss',
                        'expense_date': timezone.localdate().isoformat(),
                        'clients': str(self.client_user.pk),
                        'proof_image': loss_proof,
                    },
                    format='multipart',
                )
                self.assertEqual(created_loss.status_code, 201, created_loss.data)
                summary2 = self.client.get('/api/admin/accounting/').json()[
                    'financial_summary'
                ][0]
                self.assertEqual(summary2['expenses'], 15.0)
                self.assertEqual(summary2['losses'], 3.0)
                self.assertEqual(summary2['net'], -8.0)
                self.assertEqual(summary2['loss'], 3.0)

                filtered = self.client.get(
                    '/api/admin/accounting/',
                    {
                        'date': timezone.localdate().isoformat(),
                        'name': 'Client Reports',
                        'client': 'Client Reports',
                        'amount': '10',
                    },
                )
                self.assertEqual(filtered.status_code, 200)
                self.assertEqual(filtered.json()['count'], 1)
                self.assertEqual(filtered.json()['results'][0]['amount'], '10.00')

                expense_rows = self.client.get(
                    '/api/admin/accounting/expenses/',
                    {'client': 'Client Reports'},
                )
                self.assertEqual(expense_rows.status_code, 200)
                expense_list = expense_rows.json()
                names = {row['name'] for row in expense_list}
                self.assertEqual(names, {'Transporteur', 'Colis perdu'})
                transporteur = next(
                    row for row in expense_list if row['name'] == 'Transporteur'
                )
                self.assertIn(self.client_user.pk, transporteur.get('client_ids', []))
                self.assertEqual(
                    transporteur.get('clients_detail')[0]['full_name'],
                    'Client Reports',
                )

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

    def test_support_chat_client_and_admin(self):
        self.client.force_authenticate(self.client_user)
        created = self.client.post(
            '/api/support-chat/',
            {'body': 'Bonjour support'},
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertFalse(created.json()['is_from_admin'])
        self.assertFalse(created.json()['is_read'])

        listed = self.client.get('/api/support-chat/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()['results']), 1)

        # L'admin consulte la boîte de réception globale (/api/support-chat/ sans client_id)
        self.client.force_authenticate(self.admin)
        inbox = self.client.get('/api/support-chat/')
        self.assertEqual(inbox.status_code, 200)
        inbox_data = inbox.json()
        self.assertGreaterEqual(inbox_data['unread_total'], 1)
        threads = inbox_data['threads']
        client_thread = next(
            t for t in threads if t['client_id'] == self.client_user.pk
        )
        self.assertEqual(client_thread['unread_count'], 1)
        self.assertEqual(
            client_thread['last_message']['body'], 'Bonjour support'
        )

        # AdminClientServiceView expose aussi les compteurs et le dernier message
        cs_resp = self.client.get('/api/admin/client-service/')
        self.assertEqual(cs_resp.status_code, 200)
        cs_card = next(
            r
            for r in cs_resp.json()['results']
            if r['id'] == self.client_user.pk
        )
        self.assertEqual(cs_card['unread_support_count'], 1)
        self.assertEqual(cs_card['support_messages_count'], 1)
        self.assertEqual(
            cs_card['last_support_message']['body'], 'Bonjour support'
        )

        # Quand l'admin ouvre le fil du client (PK ou UUID), le message du client passe à lu
        thread_by_uuid = self.client.get(
            f'/api/support-chat/{self.client_user.uuid}/'
        )
        self.assertEqual(thread_by_uuid.status_code, 200)
        self.assertEqual(thread_by_uuid.json()['results'][0]['is_read'], True)

        # L'admin répond au client
        reply = self.client.post(
            f'/api/support-chat/{self.client_user.pk}/',
            {'body': 'Nous vous aidons'},
            format='json',
        )
        self.assertEqual(reply.status_code, 201, reply.data)
        self.assertTrue(reply.json()['is_from_admin'])

        thread = self.client.get(f'/api/support-chat/{self.client_user.pk}/')
        self.assertEqual(thread.status_code, 200)
        self.assertEqual(len(thread.json()['results']), 2)

        # Quand le client ouvre son fil, la réponse de l'admin passe à lue
        self.client.force_authenticate(self.client_user)
        client_view = self.client.get('/api/support-chat/')
        self.assertEqual(client_view.status_code, 200)
        self.assertTrue(
            all(m['is_read'] for m in client_view.json()['results'])
        )

        # Envoi d'une photo jointe dans le chat
        image = BytesIO()
        Image.new('RGB', (12, 12), color=(255, 220, 0)).save(
            image, format='JPEG'
        )
        photo = SimpleUploadedFile(
            'capture.jpg',
            image.getvalue(),
            content_type='image/jpeg',
        )
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                with_photo = self.client.post(
                    '/api/support-chat/',
                    {'body': 'Voici la capture', 'attachment': photo},
                    format='multipart',
                )
                self.assertEqual(with_photo.status_code, 201, with_photo.data)
                self.assertTrue(
                    (with_photo.json().get('attachment_url') or '').endswith(
                        '.jpg'
                    )
                )
                self.assertTrue(with_photo.json().get('attachment_is_image'))

                # L'admin joint un fichier document (PDF) dans le chat
                self.client.force_authenticate(self.admin)
                pdf_file = SimpleUploadedFile(
                    'devis_bujito.pdf',
                    b'%PDF-1.4 fake pdf content',
                    content_type='application/pdf',
                )
                with_pdf = self.client.post(
                    f'/api/support-chat/{self.client_user.pk}/',
                    {'body': 'Voici le devis en PDF', 'attachment': pdf_file},
                    format='multipart',
                )
                self.assertEqual(with_pdf.status_code, 201, with_pdf.data)
                self.assertEqual(
                    with_pdf.json().get('attachment_name'),
                    'devis_bujito.pdf',
                )
                self.assertFalse(with_pdf.json().get('attachment_is_image'))

        # Liste à rappeler / à relancer (followup)
        self.client.force_authenticate(self.admin)
        followup_res = self.client.post(
            '/api/admin/client-service/',
            {
                'client_id': self.client_user.pk,
                'action': 'remind',
                'note': 'Relancer pour confirmation groupage',
                'send_reminder': True,
            },
            format='json',
        )
        self.assertEqual(followup_res.status_code, 200, followup_res.data)
        self.assertTrue(followup_res.json()['needs_followup'])
        self.assertEqual(
            followup_res.json()['followup_note'],
            'Relancer pour confirmation groupage',
        )
        self.assertIsNotNone(followup_res.json()['last_reminded_at'])

        # Filtrage par followup=true dans client-service et support-chat
        cs_followup = self.client.get(
            '/api/admin/client-service/', {'followup': 'true'}
        )
        self.assertEqual(cs_followup.status_code, 200)
        self.assertGreaterEqual(cs_followup.json()['followup_count'], 1)
        self.assertTrue(
            any(
                r['id'] == self.client_user.pk and r['needs_followup']
                for r in cs_followup.json()['results']
            )
        )

        # Retirer de la liste à relancer
        cleared = self.client.post(
            f'/api/admin/client-service/{self.client_user.pk}/followup/',
            {'action': 'remove'},
            format='json',
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertFalse(cleared.json()['needs_followup'])

    def test_support_quick_replies_and_first_auto_message(self):
        from reports.models import SupportAutoMessage, SupportMessage, SupportQuickReply

        SupportQuickReply.objects.all().delete()
        SupportAutoMessage.objects.all().delete()

        self.client.force_authenticate(self.admin)
        created = self.client.post(
            '/api/admin/support-quick-replies/',
            {
                'label': 'Salut',
                'body': 'Bonjour, comment allons-nous ?',
                'language': 'fr',
                'sort_order': 0,
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)

        listed = self.client.get(
            '/api/admin/support-quick-replies/', {'for_chat': 'true', 'lang': 'fr'}
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        SupportAutoMessage.objects.create(
            name='Welcome',
            body='Bienvenue, un agent arrive.',
            language='all',
            trigger=SupportAutoMessage.TRIGGER_FIRST_MESSAGE,
            is_active=True,
        )

        self.client.force_authenticate(self.client_user)
        first = self.client.post(
            '/api/support-chat/',
            {'body': 'Hello team'},
            format='json',
        )
        self.assertEqual(first.status_code, 201, first.data)
        thread = self.client.get('/api/support-chat/')
        self.assertEqual(thread.status_code, 200)
        bodies = [m['body'] for m in thread.json()['results']]
        self.assertIn('Hello team', bodies)
        self.assertIn('Bienvenue, un agent arrive.', bodies)
        self.assertEqual(SupportMessage.objects.filter(client=self.client_user).count(), 2)
