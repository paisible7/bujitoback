from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Q, Count, Exists, OuterRef, Prefetch
from django.contrib.auth import get_user_model
from django.utils import timezone

from .roles import (
    CLIENT_ROLES,
    ROLE_ADMIN,
    ROLE_CLIENT,
    is_app_admin,
    is_platform_superuser,
    normalize_role,
)
from .permissions import IsAppAdmin
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    AdminCreateUserSerializer,
    AdminUserUpdateSerializer,
    AdminAgentUpdateSerializer,
    AgentSalaryPaymentSerializer,
    ProfileUpdateSerializer,
    CustomTokenObtainPairSerializer,
    PasswordResetVerifySerializer,
    PasswordResetSerializer,
    ChangePasswordSerializer,
    build_china_warehouse_address,
    build_china_air_address,
    build_china_sea_address,
)
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from core.serializers import UUIDLookupMixin, resolve_uuid_or_pk
from .admin_permissions import (
    normalize_admin_permissions,
    can_pay_worker_salary,
    can_list_workers_for_salary,
)
from .models import (
    AgentSalaryPayment,
    WORKER_SERVICE_KEYS,
)
from parcels.pagination import OptionalPageNumberPagination

AGENT_PATCH_KEYS = (
    'admin_permissions',
    'is_active',
    'service_percentages',
    'worker_status',
    'permissions_restricted',
)

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = serializer.save()
        except Exception as exc:
            # Contrainte unique DB (email / téléphone) → message clair.
            from django.db import IntegrityError

            if isinstance(exc, IntegrityError):
                msg = str(exc).lower()
                if 'phone' in msg:
                    return Response(
                        {'phone_number': ['Un compte existe déjà avec ce numéro.']},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                return Response(
                    {'email': ['Un compte existe déjà avec cet email.']},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'email': user.email,
            'role': normalize_role(user.role),
            'full_name': user.full_name,
            'phone_number': user.phone_number,
            'city': getattr(user, 'city', '') or '',
            'stars': getattr(user, 'stars', 0) or 0,
            'admin_permissions': normalize_admin_permissions(
                getattr(user, 'admin_permissions', None)
            ),
            'china_warehouse_address': build_china_warehouse_address(
                user.full_name,
                user.phone_number,
                getattr(user, 'city', '') or '',
            ),
            'china_air_address': build_china_air_address(
                user.full_name,
                user.phone_number,
                getattr(user, 'city', '') or '',
            ),
            'china_sea_address': build_china_sea_address(
                user.full_name,
                user.phone_number,
                getattr(user, 'city', '') or '',
            ),
        }, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        email = request.data.get('email') or request.data.get('username')
        print(
            f'[auth/login] host={request.get_host()!r} '
            f'email={email!r} has_password={bool(request.data.get("password"))}'
        )
        response = super().post(request, *args, **kwargs)
        print(f'[auth/login] status={response.status_code}')
        return response


def _jwt_auth_payload(user) -> dict:
    """Réponse commune login / register / Google."""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'email': user.email,
        'role': normalize_role(user.role),
        'full_name': user.full_name,
        'phone_number': user.phone_number,
        'city': getattr(user, 'city', '') or '',
        'stars': getattr(user, 'stars', 0) or 0,
        'admin_permissions': normalize_admin_permissions(
            getattr(user, 'admin_permissions', None)
        ),
        'china_warehouse_address': build_china_warehouse_address(
            user.full_name,
            user.phone_number,
            getattr(user, 'city', '') or '',
        ),
        'china_air_address': build_china_air_address(
            user.full_name,
            user.phone_number,
            getattr(user, 'city', '') or '',
        ),
        'china_sea_address': build_china_sea_address(
            user.full_name,
            user.phone_number,
            getattr(user, 'city', '') or '',
        ),
    }


class GoogleLoginView(APIView):
    """
    Connexion / inscription via Google ID token (Sign-In).
    Body: { "id_token": "..." }
    """

    permission_classes = [AllowAny]

    def post(self, request):
        from django.conf import settings
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        raw_token = (
            request.data.get('id_token')
            or request.data.get('idToken')
            or ''
        ).strip()
        if not raw_token:
            return Response(
                {'message': 'id_token is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        audiences = list(getattr(settings, 'GOOGLE_OAUTH_CLIENT_IDS', []) or [])
        if not audiences:
            return Response(
                {
                    'message': (
                        'Google Sign-In non configuré côté serveur '
                        '(GOOGLE_OAUTH_CLIENT_IDS).'
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            idinfo = None
            last_error = None
            for audience in audiences:
                try:
                    idinfo = google_id_token.verify_oauth2_token(
                        raw_token,
                        google_requests.Request(),
                        audience,
                    )
                    break
                except Exception as exc:  # noqa: BLE001 — essayer chaque audience
                    last_error = exc
            if idinfo is None:
                raise last_error or ValueError('invalid token')
        except Exception as exc:  # noqa: BLE001
            print(f'[auth/google] token invalid: {exc}')
            return Response(
                {'message': 'Jeton Google invalide ou expiré.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if idinfo.get('iss') not in {
            'accounts.google.com',
            'https://accounts.google.com',
        }:
            return Response(
                {'message': 'Émetteur Google invalide.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not idinfo.get('email'):
            return Response(
                {'message': 'Le compte Google ne fournit pas d\'e-mail.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if idinfo.get('email_verified') is False:
            return Response(
                {'message': 'E-mail Google non vérifié.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = str(idinfo['email']).strip().lower()
        full_name = (
            (idinfo.get('name') or '').strip()
            or f"{idinfo.get('given_name', '')} {idinfo.get('family_name', '')}".strip()
        )
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        created = False
        if user is None:
            user = User.objects.create_user(
                email=email,
                password=None,
                role=ROLE_CLIENT,
                full_name=full_name,
                phone_number=None,
                city='',
            )
            user.set_unusable_password()
            user.is_active = True
            user.save()
            created = True
        else:
            if not user.is_active:
                return Response(
                    {'message': 'Ce compte est désactivé.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # Enrichir le nom s'il était vide.
            if full_name and not (user.full_name or '').strip():
                user.full_name = full_name
                user.save(update_fields=['full_name'])

        payload = _jwt_auth_payload(user)
        payload['created'] = created
        return Response(
            payload,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def _enriched_user(self, request):
        from parcels.models import ExpeditionRequest, Order, Parcel
        from parcels.ownership import parcels_for_user_q
        from parcels.stats import PARCEL_RECEIVED_STATUSES, PARCEL_SENT_STATUSES
        from payments.models import Payment

        user = User.objects.filter(pk=request.user.pk).first() or request.user
        visible = Parcel.objects.filter(
            parcels_for_user_q(request.user)
        ).distinct()
        user.parcels_count = visible.count()
        user.parcels_received_count = visible.filter(
            status__in=PARCEL_RECEIVED_STATUSES
        ).count()
        user.parcels_sent_count = visible.filter(
            status__in=PARCEL_SENT_STATUSES
        ).count()

        # Commandes dashboard : ouvertes seulement (baisse quand validée/payée).
        paid_order = Payment.objects.filter(
            order_id=OuterRef('pk'),
            status='completed',
        )
        user.orders_count = (
            Order.objects.filter(user_id=request.user.pk)
            .exclude(status='cancelled')
            .exclude(Exists(paid_order))
            .count()
        )

        unpaid_orders = (
            Order.objects.filter(
                user_id=request.user.pk,
                quote_ready=True,
                status__in=('pending', 'processing'),
            )
            .exclude(Exists(paid_order))
            .count()
        )
        unpaid_expeditions = ExpeditionRequest.objects.filter(
            user_id=request.user.pk,
            status__in=('quoted', 'awaiting_payment'),
        ).count()
        user.invoices_to_pay_count = unpaid_orders + unpaid_expeditions
        return user

    def get(self, request):
        user = self._enriched_user(request)
        serializer = UserSerializer(user, context={'request': request})
        return Response(serializer.data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user = self._enriched_user(request)
        return Response(UserSerializer(user, context={'request': request}).data)


class UserListCreateView(generics.ListCreateAPIView):
    """
    Liste / création d'utilisateurs.
    - Admin : voit et crée des clients
    - Superuser : voit clients + admins, peut créer clients et admins
    """
    permission_classes = [IsAuthenticated, IsAppAdmin]
    pagination_class = OptionalPageNumberPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminCreateUserSerializer
        return UserSerializer

    def get_queryset(self):
        from parcels.stats import PARCEL_RECEIVED_STATUSES, PARCEL_SENT_STATUSES

        actor = self.request.user
        if is_platform_superuser(actor):
            qs = User.objects.filter(
                role__in=[ROLE_CLIENT, ROLE_ADMIN, 'user'],
            ).order_by('role', 'email')
        elif can_list_workers_for_salary(actor):
            # Comptable : clients + travailleurs (pour payer les salaires).
            qs = User.objects.filter(
                role__in=[ROLE_CLIENT, ROLE_ADMIN, 'user'],
            ).order_by('role', 'email')
        else:
            qs = User.objects.filter(role__in=CLIENT_ROLES).order_by('email')

        role_filter = self.request.query_params.get('role', '').strip().lower()
        if role_filter:
            role_filter = normalize_role(role_filter)
            if role_filter == ROLE_CLIENT:
                qs = qs.filter(role__in=CLIENT_ROLES)
            elif role_filter == ROLE_ADMIN and not (
                is_platform_superuser(actor) or can_list_workers_for_salary(actor)
            ):
                qs = qs.none()
            else:
                qs = qs.filter(role=role_filter)

        # Par défaut pour l'écran notif : clients actifs seulement
        clients_only = self.request.query_params.get('clients_only', '').lower() in (
            '1', 'true', 'yes',
        )
        if clients_only:
            qs = qs.filter(role__in=CLIENT_ROLES, is_active=True)

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(full_name__icontains=search)
                | Q(phone_number__icontains=search)
                | Q(city__icontains=search)
            )
        return qs.annotate(
            orders_count=Count('orders', distinct=True),
            parcels_count=Count('orders__parcels', distinct=True),
            parcels_received_count=Count(
                'orders__parcels',
                filter=Q(orders__parcels__status__in=PARCEL_RECEIVED_STATUSES),
                distinct=True,
            ),
            parcels_sent_count=Count(
                'orders__parcels',
                filter=Q(orders__parcels__status__in=PARCEL_SENT_STATUSES),
                distinct=True,
            ),
        ).prefetch_related(
            Prefetch(
                'salary_payments',
                queryset=AgentSalaryPayment.objects.order_by('-paid_at', '-created_at'),
            ),
        )

    def create(self, request, *args, **kwargs):
        serializer = AdminCreateUserSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class UserAdminDetailView(UUIDLookupMixin, generics.RetrieveUpdateAPIView):
    """Admin : détail / mise à jour (étoiles) d'un utilisateur."""

    permission_classes = [IsAuthenticated, IsAppAdmin]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        actor = self.request.user
        if is_platform_superuser(actor):
            qs = User.objects.filter(
                role__in=[ROLE_CLIENT, ROLE_ADMIN, 'user'],
            )
        else:
            qs = User.objects.filter(role__in=CLIENT_ROLES)
        from parcels.stats import PARCEL_RECEIVED_STATUSES, PARCEL_SENT_STATUSES

        return qs.annotate(
            orders_count=Count('orders', distinct=True),
            parcels_count=Count('orders__parcels', distinct=True),
            parcels_received_count=Count(
                'orders__parcels',
                filter=Q(orders__parcels__status__in=PARCEL_RECEIVED_STATUSES),
                distinct=True,
            ),
            parcels_sent_count=Count(
                'orders__parcels',
                filter=Q(orders__parcels__status__in=PARCEL_SENT_STATUSES),
                distinct=True,
            ),
        ).prefetch_related(
            Prefetch(
                'salary_payments',
                queryset=AgentSalaryPayment.objects.order_by('-paid_at', '-created_at'),
            ),
        )

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return AdminUserUpdateSerializer
        return UserSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        # Super Admin : mise à jour permissions / activation d'un agent.
        if (
            is_platform_superuser(request.user)
            and normalize_role(instance.role) == ROLE_ADMIN
            and any(key in request.data for key in AGENT_PATCH_KEYS)
        ):
            serializer = AdminAgentUpdateSerializer(
                instance, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            instance.refresh_from_db()
            return Response(
                UserSerializer(instance, context={'request': request}).data
            )

        serializer = AdminUserUpdateSerializer(
            instance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        instance.refresh_from_db()
        return Response(
            UserSerializer(instance, context={'request': request}).data
        )


class AgentSalaryView(APIView):
    """Salaire travailleur : liste (soi / Super Admin) + enregistrement (Super Admin)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def _worker(self, pk):
        qs = User.objects.filter(role=ROLE_ADMIN)
        try:
            return resolve_uuid_or_pk(qs, pk)
        except User.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Travailleur introuvable.')

    def _salary_dashboard(self, request, worker):
        from .salary_accrual import worker_service_balances

        payments = AgentSalaryPayment.objects.filter(worker=worker).order_by(
            '-paid_at', '-created_at'
        )
        dash = worker_service_balances(worker)
        dash['results'] = AgentSalaryPaymentSerializer(
            payments[:100], many=True, context={'request': request}
        ).data
        return dash

    def _mirror_expense(self, *, worker, payment, note, proof, recorded_by):
        try:
            from reports.models import Expense

            worker_label = (worker.full_name or '').strip() or worker.email
            service_label = payment.service or 'général'
            expense = Expense(
                name=worker_label[:200],
                category='Salaire',
                entry_type=Expense.ENTRY_EXPENSE,
                description=(
                    note
                    or f'Paiement salaire / commission ({service_label})'
                )[:2000],
                amount=payment.amount,
                currency=payment.currency,
                expense_date=timezone.localdate(),
                recorded_by=recorded_by,
            )
            if proof is not None:
                try:
                    proof.seek(0)
                except Exception:
                    pass
                expense.proof_image.save(
                    getattr(proof, 'name', 'salary_proof.jpg')
                    or 'salary_proof.jpg',
                    proof,
                    save=False,
                )
            expense.save()
        except Exception:
            pass

    def _parse_services(self, data):
        """Accepte services[] / services (JSON ou CSV) / service (legacy)."""
        raw = data.get('services')
        if raw is None:
            raw = data.getlist('services') if hasattr(data, 'getlist') else None
        services = []
        if isinstance(raw, list):
            services = [str(s).strip().lower() for s in raw if str(s).strip()]
        elif isinstance(raw, str) and raw.strip():
            text = raw.strip()
            if text.startswith('['):
                import json

                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        services = [
                            str(s).strip().lower()
                            for s in parsed
                            if str(s).strip()
                        ]
                except Exception:
                    services = [
                        s.strip().lower()
                        for s in text.split(',')
                        if s.strip()
                    ]
            else:
                services = [
                    s.strip().lower() for s in text.split(',') if s.strip()
                ]
        if not services:
            single = (data.get('service') or '').strip().lower()
            if single:
                services = [single]
        return services

    def get(self, request, pk=None):
        if pk is None:
            worker = request.user
        else:
            if not can_pay_worker_salary(request.user):
                return Response(
                    {'detail': 'Réservé au Super Admin ou comptable.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            worker = self._worker(pk)
        return Response(self._salary_dashboard(request, worker))

    def post(self, request, pk=None):
        if not can_pay_worker_salary(request.user):
            return Response(
                {'detail': 'Réservé au Super Admin ou comptable.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if pk is None:
            return Response(
                {'detail': 'Travailleur requis.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        worker = self._worker(pk)
        from .salary_accrual import balances_for_services

        note = (request.data.get('note') or '').strip()[:400]
        status_value = (
            request.data.get('status') or AgentSalaryPayment.STATUS_PAID
        ).strip()
        if status_value not in {
            AgentSalaryPayment.STATUS_PAID,
            AgentSalaryPayment.STATUS_PENDING,
        }:
            status_value = AgentSalaryPayment.STATUS_PAID
        proof = request.FILES.get('proof_image')
        currency = (request.data.get('currency') or 'USD').strip()[:10] or 'USD'

        # Mode auto si `services` est fourni (multi) OU pas de montant manuel.
        has_services_key = (
            'services' in request.data
            or (
                hasattr(request.data, 'getlist')
                and bool(request.data.getlist('services'))
            )
        )
        amount_raw = request.data.get('amount')
        services = self._parse_services(request.data)
        use_auto = has_services_key or (
            amount_raw in (None, '') and bool(services)
        )

        # Mode auto : multi-services → montant = solde dû (encaissé × %).
        if use_auto:
            unknown = [s for s in services if s not in WORKER_SERVICE_KEYS]
            if unknown:
                return Response(
                    {'services': [f'Service(s) inconnu(s): {", ".join(unknown)}']},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            rows = balances_for_services(worker, services)
            if not rows:
                return Response(
                    {
                        'services': [
                            'Aucun solde dû sur les services sélectionnés.'
                        ]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            created = []
            for row in rows:
                payment = AgentSalaryPayment.objects.create(
                    worker=worker,
                    amount=row['balance'],
                    currency=currency,
                    service=row['service'],
                    note=note,
                    status=status_value,
                    proof_image=proof if not created else None,
                    recorded_by=request.user,
                )
                if status_value == AgentSalaryPayment.STATUS_PAID:
                    self._mirror_expense(
                        worker=worker,
                        payment=payment,
                        note=note,
                        proof=proof if len(created) == 0 else None,
                        recorded_by=request.user,
                    )
                created.append(payment)
            payload = {
                'results': AgentSalaryPaymentSerializer(
                    created, many=True, context={'request': request}
                ).data,
                'dashboard': self._salary_dashboard(request, worker),
            }
            if len(created) == 1:
                payload.update(payload['results'][0])
            return Response(payload, status=status.HTTP_201_CREATED)

        # Legacy : montant manuel + un service optionnel.
        try:
            amount = float(request.data.get('amount'))
        except (TypeError, ValueError):
            return Response(
                {'amount': ['Montant invalide.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount <= 0:
            return Response(
                {'amount': ['Le montant doit être positif.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        service = (request.data.get('service') or '').strip().lower()
        if service and service not in WORKER_SERVICE_KEYS:
            return Response(
                {'service': ['Service inconnu.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment = AgentSalaryPayment.objects.create(
            worker=worker,
            amount=amount,
            currency=currency,
            service=service,
            note=note,
            status=status_value,
            proof_image=proof,
            recorded_by=request.user,
        )
        if status_value == AgentSalaryPayment.STATUS_PAID:
            self._mirror_expense(
                worker=worker,
                payment=payment,
                note=note,
                proof=proof,
                recorded_by=request.user,
            )
        return Response(
            AgentSalaryPaymentSerializer(
                payment, context={'request': request}
            ).data,
            status=status.HTTP_201_CREATED,
        )


class PasswordResetVerifyView(APIView):
    """Étape 1 : vérifier que l'email correspond à un compte actif."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {'detail': 'Email vérifié. Vous pouvez définir un nouveau mot de passe.'},
            status=status.HTTP_200_OK,
        )


class PasswordResetView(APIView):
    """Étape 2 : réinitialiser le mot de passe (sans lien email pour l'instant)."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'detail': 'Mot de passe mis à jour avec succès.'},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """Changer le mot de passe (utilisateur connecté)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'detail': 'Mot de passe mis à jour avec succès.'},
            status=status.HTTP_200_OK,
        )
