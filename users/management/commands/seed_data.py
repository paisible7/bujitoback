from decimal import Decimal
from datetime import timedelta
from itertools import cycle
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from parcels.models import Order, Parcel, Consolidation, OrderImage
from notifications.models import Notification
from payments.models import PaymentMethod, Payment, SavedPaymentMethod

User = get_user_model()

# Comptes de test (mot de passe unique pour tous)
SEED_PASSWORD = 'Test1234!'

# Images optionnelles a placer avant le seed :
#   <MEDIA_ROOT>/seed/parcels/parcel_1.jpg ... parcel_6.jpg
#   <MEDIA_ROOT>/seed/orders/order_1.jpg ... order_3.jpg
SEED_PARCEL_IMAGES = Path(settings.MEDIA_ROOT) / 'seed' / 'parcels'
SEED_ORDER_IMAGES = Path(settings.MEDIA_ROOT) / 'seed' / 'orders'
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}

USERS = [
    {
        'email': 'admin@bujito.com',
        'full_name': 'Admin Bujito',
        'phone_number': '+243810000001',
        'role': 'admin',
        'is_staff': True,
        'is_superuser': True,
        'language': 'fr',
    },
    {
        'email': 'alice@bujito.com',
        'full_name': 'Alice Mbala',
        'phone_number': '+243810000002',
        'role': 'user',
        'is_staff': False,
        'is_superuser': False,
        'language': 'fr',
    },
    {
        'email': 'bob@bujito.com',
        'full_name': 'Bob Kalonji',
        'phone_number': '+243810000003',
        'role': 'user',
        'is_staff': False,
        'is_superuser': False,
        'language': 'en',
    },
]


class Command(BaseCommand):
    help = (
        'Seeder de test : 3 utilisateurs (1 admin + 2 clients) avec commandes, '
        'colis, groupages, notifications et paiements.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Supprime les données liées avant de re-seeder (conserve les autres users).',
        )

    def handle(self, *args, **options):
        if options['flush']:
            self._flush()

        users = self._ensure_users()
        admin, alice, bob = users['admin@bujito.com'], users['alice@bujito.com'], users['bob@bujito.com']

        methods = self._ensure_payment_methods()
        self._seed_client(alice, methods, prefix='AL')
        self._seed_client(bob, methods, prefix='BO')

        # Notif admin
        Notification.objects.get_or_create(
            user=admin,
            title='Bienvenue Admin',
            message='Compte admin prêt. Gérez colis, groupages et commandes.',
            defaults={'type': 'general', 'is_read': False},
        )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Seeder terminé. Comptes :'))
        self.stdout.write(f'  Admin  : admin@bujito.com  / {SEED_PASSWORD}')
        self.stdout.write(f'  Client : alice@bujito.com  / {SEED_PASSWORD}')
        self.stdout.write(f'  Client : bob@bujito.com    / {SEED_PASSWORD}')

    def _flush(self):
        self.stdout.write(self.style.WARNING('Flush des donnees de test...'))
        emails = [u['email'] for u in USERS]
        qs = User.objects.filter(email__in=emails)
        Payment.objects.filter(user__in=qs).delete()
        SavedPaymentMethod.objects.filter(user__in=qs).delete()
        Notification.objects.filter(user__in=qs).delete()
        Consolidation.objects.filter(user__in=qs).delete()
        Parcel.objects.filter(order__user__in=qs).delete()
        Order.objects.filter(user__in=qs).delete()
        # Ne pas supprimer les users : on les met à jour ensuite
        self.stdout.write(self.style.SUCCESS('Flush OK.'))

    def _ensure_users(self):
        users = {}
        for data in USERS:
            email = data['email']
            defaults = {k: v for k, v in data.items() if k != 'email'}
            user, created = User.objects.get_or_create(email=email, defaults=defaults)
            if not created:
                for k, v in defaults.items():
                    setattr(user, k, v)
            user.set_password(SEED_PASSWORD)
            user.save()
            users[email] = user
            label = 'créé' if created else 'mis à jour'
            self.stdout.write(self.style.SUCCESS(f'User {label}: {email} ({user.role})'))
        return users

    def _ensure_payment_methods(self):
        specs = [
            ('Orange Money', 'orange_money'),
            ('Wave', 'wave'),
            ('Carte bancaire', 'card'),
        ]
        methods = {}
        for name, code in specs:
            m, _ = PaymentMethod.objects.get_or_create(
                code=code,
                defaults={'name': name, 'is_active': True},
            )
            methods[code] = m
        return methods

    def _list_seed_images(self, folder: Path):
        if not folder.is_dir():
            return []
        files = [
            p for p in sorted(folder.iterdir())
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        ]
        return files

    def _attach_image(self, field, path: Path, dest_name: str):
        with path.open('rb') as f:
            field.save(dest_name, File(f), save=True)

    def _seed_client(self, user, methods, prefix):
        # Évite de doubler si déjà seedé (colis avec tracking préfixe)
        if Parcel.objects.filter(tracking_number__startswith=f'{prefix}-').exists():
            self.stdout.write(self.style.WARNING(
                f'Données déjà présentes pour {user.email} (préfixe {prefix}-). '
                f'Utilisez --flush pour régénérer.'
            ))
            return

        now = timezone.now()
        self.stdout.write(self.style.WARNING(f'Seed donnees -> {user.email}'))

        parcel_imgs = self._list_seed_images(SEED_PARCEL_IMAGES)
        order_imgs = self._list_seed_images(SEED_ORDER_IMAGES)
        parcel_cycle = cycle(parcel_imgs) if parcel_imgs else None
        order_cycle = cycle(order_imgs) if order_imgs else None
        if not parcel_imgs:
            self.stdout.write(self.style.WARNING(
                f'  (pas d\'images dans {SEED_PARCEL_IMAGES} — colis sans photo)'
            ))
        if not order_imgs:
            self.stdout.write(self.style.WARNING(
                f'  (pas d\'images dans {SEED_ORDER_IMAGES} — commandes sans photo)'
            ))

        # --- Commandes (statuts varies + champs detail) ---
        order_specs = [
            {
                'status': 'pending',
                'amount': Decimal('85.00'),
                'days_ago': 2,
                'country': 'RDC',
                'city': 'Kinshasa',
                'links': 'https://example.com/product/a',
                'qty': 1,
                'comment': 'Livraison urgente si possible',
                'parcels': [
                    ('pending', 'Entrepôt Guangzhou', '2.1 kg'),
                    ('pending', 'Entrepôt Guangzhou', '0.8 kg'),
                ],
            },
            {
                'status': 'processing',
                'amount': Decimal('210.50'),
                'days_ago': 8,
                'country': 'RDC',
                'city': 'Lubumbashi',
                'links': 'https://example.com/product/b\nhttps://example.com/product/c',
                'qty': 3,
                'comment': '',
                'parcels': [
                    ('in_transit', 'En route Dubai', '5.0 kg'),
                    ('in_transit', 'Hub Nairobi', '1.2 kg'),
                ],
            },
            {
                'status': 'shipped',
                'amount': Decimal('140.00'),
                'days_ago': 18,
                'country': 'RDC',
                'city': 'Goma',
                'links': 'https://example.com/product/d',
                'qty': 2,
                'comment': 'Fragile',
                'parcels': [
                    ('out_for_delivery', 'Kinshasa - last mile', '3.4 kg'),
                ],
            },
            {
                'status': 'delivered',
                'amount': Decimal('320.00'),
                'days_ago': 40,
                'country': 'RDC',
                'city': 'Kinshasa',
                'links': 'https://example.com/product/e',
                'qty': 1,
                'comment': 'Reçu OK',
                'parcels': [
                    ('delivered', 'Livré - Kinshasa', '4.0 kg'),
                    ('delivered', 'Livré - Kinshasa', '1.5 kg'),
                ],
            },
        ]

        created_orders = []
        parcel_counter = 1
        groupable = []

        for idx, spec in enumerate(order_specs, start=1):
            order = Order(
                user=user,
                status=spec['status'],
                total_amount=spec['amount'],
                client_name=user.full_name,
                client_phone=user.phone_number,
                country=spec['country'],
                city=spec['city'],
                product_links=spec['links'],
                quantity=spec['qty'],
                comment=spec['comment'] or None,
            )
            order.save()
            # order_date is auto_now_add — adjust via update
            Order.objects.filter(pk=order.pk).update(
                order_date=now - timedelta(days=spec['days_ago'])
            )
            order.refresh_from_db()
            created_orders.append(order)

            if order_cycle is not None:
                src = next(order_cycle)
                img = OrderImage(order=order)
                self._attach_image(img.image, src, f'orders/{prefix.lower()}_{order.id}{src.suffix}')
                # _attach_image already saves the ImageField (+ model)

            for p_status, location, weight in spec['parcels']:
                tracking = f'{prefix}-{order.id:04d}-{parcel_counter:03d}'
                parcel = Parcel.objects.create(
                    order=order,
                    tracking_number=tracking,
                    status=p_status,
                    current_location=location,
                    client_name=user.full_name,
                    client_phone=user.phone_number,
                    weight_volume=weight,
                    warehouse_number=f'WH-{prefix}-{idx}',
                    description=f'Colis test {tracking}',
                )
                if parcel_cycle is not None:
                    src = next(parcel_cycle)
                    self._attach_image(
                        parcel.image,
                        src,
                        f'parcels/{tracking.lower()}{src.suffix}',
                    )
                parcel_counter += 1
                if p_status in ('pending', 'in_transit'):
                    groupable.append(parcel)

        # --- Groupages : 1 pending + 1 completed ---
        if len(groupable) >= 2:
            pending_group = Consolidation.objects.create(user=user, status='pending')
            pending_group.parcels.set(groupable[:2])

        # Colis dédiés pour un groupage terminé
        done_order = Order.objects.create(
            user=user,
            status='processing',
            total_amount=Decimal('99.00'),
            client_name=user.full_name,
            client_phone=user.phone_number,
            country='RDC',
            city='Kinshasa',
            product_links='https://example.com/product/group',
            quantity=2,
        )
        p1 = Parcel.objects.create(
            order=done_order,
            tracking_number=f'{prefix}-GRP-001',
            status='consolidated',
            current_location='Entrepot consolide',
            client_name=user.full_name,
            weight_volume='2 kg',
            description='Colis groupe A',
        )
        p2 = Parcel.objects.create(
            order=done_order,
            tracking_number=f'{prefix}-GRP-002',
            status='consolidated',
            current_location='Entrepot consolide',
            client_name=user.full_name,
            weight_volume='1 kg',
            description='Colis groupe B',
        )
        if parcel_cycle is not None:
            for p in (p1, p2):
                src = next(parcel_cycle)
                self._attach_image(
                    p.image,
                    src,
                    f'parcels/{p.tracking_number.lower()}{src.suffix}',
                )
        done_group = Consolidation.objects.create(user=user, status='completed')
        done_group.parcels.set([p1, p2])

        # --- Moyens de paiement enregistrés ---
        SavedPaymentMethod.objects.create(
            user=user,
            type='orange_money',
            label='Orange Money principal',
            phone_number=user.phone_number,
            is_default=True,
        )
        SavedPaymentMethod.objects.create(
            user=user,
            type='wave',
            label='Wave',
            phone_number=user.phone_number,
            is_default=False,
        )

        # --- Paiements ---
        paid_order = created_orders[-1]  # delivered
        Payment.objects.create(
            user=user,
            order=paid_order,
            amount=paid_order.total_amount,
            currency='USD',
            reference=f'PAY-{prefix}-{paid_order.id}-OK',
            method=methods['orange_money'],
            status='completed',
            phone_number=user.phone_number,
        )
        pending_order = created_orders[0]
        Payment.objects.create(
            user=user,
            order=pending_order,
            amount=pending_order.total_amount,
            currency='USD',
            reference=f'PAY-{prefix}-{pending_order.id}-WAIT',
            method=methods['wave'],
            status='pending',
            phone_number=user.phone_number,
        )

        # --- Notifications ---
        Notification.objects.create(
            user=user,
            title='Bienvenue sur Bujito',
            message=f'Bonjour {user.full_name}, votre compte de test est prêt.',
            type='general',
            is_read=False,
        )
        Notification.objects.create(
            user=user,
            title='Colis en transit',
            message='Un de vos colis est en route vers la RDC.',
            type='parcel',
            reference_id=created_orders[1].id if len(created_orders) > 1 else None,
            is_read=False,
        )
        Notification.objects.create(
            user=user,
            title='Demande de groupage',
            message='Votre demande de groupage est en attente de validation.',
            type='consolidation',
            reference_id=pending_group.id if len(groupable) >= 2 else None,
            is_read=True,
        )

        self.stdout.write(self.style.SUCCESS(
            f'  -> {user.email}: {Order.objects.filter(user=user).count()} commandes, '
            f'{Parcel.objects.filter(order__user=user).count()} colis, '
            f'{Consolidation.objects.filter(user=user).count()} groupages'
        ))
