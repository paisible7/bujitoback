"""API admin : statistiques, comptabilité, service client."""
from __future__ import annotations

import csv
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.views import APIView

from core.serializers import UUIDLookupMixin
from parcels.models import Order, Parcel
from parcels.stats import PARCEL_RECEIVED_STATUSES, PARCEL_SENT_STATUSES
from payments.models import Payment
from payments.serializers import PaymentSerializer
from .models import Expense
from .serializers import ExpenseSerializer
from users.permissions import IsAppAdmin
from users.roles import CLIENT_ROLES
from users.serializers import (
    build_china_air_address,
    build_china_sea_address,
    build_china_warehouse_address,
)

User = get_user_model()


def _parse_date(value: str | None, *, end: bool = False):
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        day = datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError:
        return None
    dt = datetime.combine(day, time.max if end else time.min)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _period_bounds(request):
    start = _parse_date(request.query_params.get('from'))
    end = _parse_date(request.query_params.get('to'), end=True)
    return start, end


def _apply_created_range(qs, start, end, field='created_at'):
    if start is not None:
        qs = qs.filter(**{f'{field}__gte': start})
    if end is not None:
        qs = qs.filter(**{f'{field}__lte': end})
    return qs


def _payment_meta_type(payment: Payment) -> str:
    raw = payment.provider_raw_response
    if isinstance(raw, dict):
        t = (raw.get('type') or '').strip().lower()
        if t == 'money_transfer':
            return 'transfer'
        if t == 'expedition':
            return 'expedition'
    if payment.expedition_id:
        return 'expedition'
    if payment.order_id:
        return 'order'
    return 'other'


def _filter_payments_by_type(qs, type_filter: str):
    t = (type_filter or 'all').strip().lower()
    if t in ('', 'all'):
        return qs
    if t == 'order':
        return qs.filter(order_id__isnull=False).exclude(
            provider_raw_response__type='money_transfer'
        )
    if t == 'transfer':
        return qs.filter(provider_raw_response__type='money_transfer')
    if t == 'expedition':
        return qs.filter(
            Q(expedition_id__isnull=False)
            | Q(provider_raw_response__type='expedition')
        )
    return qs


def _filter_payment_search(qs, params):
    name = (params.get('name') or '').strip()
    client = (params.get('client') or '').strip()
    search = (params.get('search') or '').strip()
    amount = (params.get('amount') or '').strip()
    date_value = (params.get('date') or '').strip()

    if name:
        qs = qs.filter(
            Q(user__full_name__icontains=name)
            | Q(user__email__icontains=name)
            | Q(order__client_name__icontains=name)
        )
    if client:
        qs = qs.filter(
            Q(user__full_name__icontains=client)
            | Q(user__email__icontains=client)
            | Q(user__phone_number__icontains=client)
            | Q(order__client_name__icontains=client)
            | Q(order__client_phone__icontains=client)
        )
    if search:
        qs = qs.filter(
            Q(reference__icontains=search)
            | Q(user__full_name__icontains=search)
            | Q(user__email__icontains=search)
            | Q(order__client_name__icontains=search)
        )
    if amount:
        try:
            qs = qs.filter(amount=Decimal(amount.replace(',', '.')))
        except (InvalidOperation, ValueError):
            pass
    if date_value:
        day = _parse_date(date_value)
        if day:
            qs = qs.filter(created_at__gte=day, created_at__lte=_parse_date(date_value, end=True))
    return qs


def _filter_expenses(qs, params):
    name = (params.get('name') or '').strip()
    client = (params.get('client') or '').strip()
    search = (params.get('search') or '').strip()
    amount = (params.get('amount') or '').strip()
    date_value = (params.get('date') or '').strip()

    if name:
        qs = qs.filter(name__icontains=name)
    if client:
        qs = qs.filter(
            Q(client__full_name__icontains=client)
            | Q(client__email__icontains=client)
            | Q(client__phone_number__icontains=client)
        )
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(category__icontains=search)
            | Q(description__icontains=search)
            | Q(client__full_name__icontains=search)
            | Q(client__email__icontains=search)
        )
    if amount:
        try:
            qs = qs.filter(amount=Decimal(amount.replace(',', '.')))
        except (InvalidOperation, ValueError):
            pass
    if date_value:
        try:
            qs = qs.filter(expense_date=datetime.strptime(date_value[:10], '%Y-%m-%d').date())
        except ValueError:
            pass
    return qs


def _accounting_expenses(request):
    qs = Expense.objects.select_related('client', 'recorded_by').all()
    start, end = _period_bounds(request)
    if start:
        qs = qs.filter(expense_date__gte=start.date())
    if end:
        qs = qs.filter(expense_date__lte=end.date())
    return _filter_expenses(qs, request.query_params)


def _financial_summary(payments, expenses):
    revenues = {}
    for row in (
        payments.filter(status='completed')
        .values('currency')
        .annotate(amount=Sum('amount'))
    ):
        currency = _normalize_currency(row['currency'])
        revenues[currency] = revenues.get(currency, Decimal('0')) + (row['amount'] or Decimal('0'))

    expense_totals = {}
    for row in expenses.values('currency').annotate(amount=Sum('amount')):
        currency = _normalize_currency(row['currency'])
        expense_totals[currency] = expense_totals.get(currency, Decimal('0')) + (
            row['amount'] or Decimal('0')
        )
    rows = []
    for currency in sorted(set(revenues) | set(expense_totals)):
        revenue = revenues.get(currency, Decimal('0'))
        spent = expense_totals.get(currency, Decimal('0'))
        net = revenue - spent
        rows.append({
            'currency': currency,
            'revenue': float(revenue),
            'expenses': float(spent),
            'net': float(net),
            'profit': float(max(net, Decimal('0'))),
            'loss': float(max(-net, Decimal('0'))),
        })
    return rows


def _normalize_currency(code: str | None) -> str:
    c = (code or 'USD').strip().upper()
    if c == 'XOF':
        return 'FCFA'
    if c == 'FC':
        return 'CDF'
    return c


def _amount_buckets(qs):
    rows = (
        qs.values('status', 'currency')
        .annotate(amount=Sum('amount'), count=Count('id'))
        .order_by('status', 'currency')
    )
    out = {}
    for row in rows:
        status = row['status'] or 'pending'
        currency = _normalize_currency(row['currency'])
        bucket = out.setdefault(status, [])
        bucket.append(
            {
                'currency': currency,
                'amount': float(row['amount'] or 0),
                'count': row['count'] or 0,
            }
        )
    return out


class AdminStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAppAdmin]

    def get(self, request):
        start, end = _period_bounds(request)

        clients_qs = User.objects.filter(role__in=CLIENT_ROLES, is_active=True)
        orders_qs = Order.objects.all()
        parcels_qs = Parcel.objects.all()
        payments_qs = Payment.objects.all()

        if start or end:
            # Orders use order_date; parcels last_updated; payments created_at
            orders_qs = _apply_created_range(orders_qs, start, end, 'order_date')
            parcels_qs = _apply_created_range(parcels_qs, start, end, 'last_updated')
            payments_qs = _apply_created_range(payments_qs, start, end, 'created_at')

        orders_by_status = [
            {'status': row['status'], 'count': row['count']}
            for row in orders_qs.values('status').annotate(count=Count('id')).order_by('status')
        ]
        parcels_by_status = [
            {'status': row['status'], 'count': row['count']}
            for row in parcels_qs.values('status').annotate(count=Count('id')).order_by('status')
        ]

        received = parcels_qs.filter(status__in=PARCEL_RECEIVED_STATUSES).count()
        sent = parcels_qs.filter(status__in=PARCEL_SENT_STATUSES).count()
        awaiting = parcels_qs.filter(status='awaiting_arrival').count()

        completed_payments = payments_qs.filter(status='completed')
        pending_payments = payments_qs.filter(status='pending')

        payments_by_day = []
        day_rows = (
            completed_payments.annotate(day=TruncDate('created_at'))
            .values('day', 'currency')
            .annotate(amount=Sum('amount'), count=Count('id'))
            .order_by('day', 'currency')
        )
        for row in day_rows:
            day = row['day']
            payments_by_day.append(
                {
                    'date': day.isoformat() if day else None,
                    'currency': _normalize_currency(row['currency']),
                    'amount': float(row['amount'] or 0),
                    'count': row['count'] or 0,
                }
            )

        revenue_by_method = []
        method_rows = (
            completed_payments.values('method__code', 'method__name', 'currency')
            .annotate(amount=Sum('amount'), count=Count('id'))
            .order_by('method__code', 'currency')
        )
        for row in method_rows:
            revenue_by_method.append(
                {
                    'method': row['method__code'] or 'unknown',
                    'method_name': row['method__name'] or row['method__code'] or '—',
                    'currency': _normalize_currency(row['currency']),
                    'amount': float(row['amount'] or 0),
                    'count': row['count'] or 0,
                }
            )

        completed_by_currency = []
        for row in (
            completed_payments.values('currency')
            .annotate(amount=Sum('amount'), count=Count('id'))
            .order_by('currency')
        ):
            completed_by_currency.append(
                {
                    'currency': _normalize_currency(row['currency']),
                    'amount': float(row['amount'] or 0),
                    'count': row['count'] or 0,
                }
            )

        return Response(
            {
                'period': {
                    'from': start.date().isoformat() if start else None,
                    'to': end.date().isoformat() if end else None,
                },
                'clients_count': clients_qs.count(),
                'orders': {
                    'total': orders_qs.count(),
                    'by_status': orders_by_status,
                },
                'parcels': {
                    'total': parcels_qs.count(),
                    'received': received,
                    'sent': sent,
                    'awaiting': awaiting,
                    'by_status': parcels_by_status,
                },
                'payments': {
                    'completed_count': completed_payments.count(),
                    'pending_count': pending_payments.count(),
                    'completed_by_currency': completed_by_currency,
                },
                'payments_by_day': payments_by_day,
                'orders_by_status': orders_by_status,
                'parcels_by_status': parcels_by_status,
                'revenue_by_method': revenue_by_method,
            }
        )


class AdminAccountingView(APIView):
    permission_classes = [IsAuthenticated, IsAppAdmin]

    def get(self, request):
        start, end = _period_bounds(request)
        type_filter = request.query_params.get('type', 'all')
        page = max(1, int(request.query_params.get('page') or 1))
        page_size = min(100, max(1, int(request.query_params.get('page_size') or 20)))

        qs = Payment.objects.select_related('user', 'method', 'order', 'expedition').order_by(
            '-created_at'
        )
        qs = _apply_created_range(qs, start, end, 'created_at')
        qs = _filter_payments_by_type(qs, type_filter)
        qs = _filter_payment_search(qs, request.query_params)
        expenses = _accounting_expenses(request)

        totals = _amount_buckets(qs)
        by_method = []
        for row in (
            qs.filter(status='completed')
            .values('method__code', 'method__name', 'currency')
            .annotate(amount=Sum('amount'), count=Count('id'))
            .order_by('method__code', 'currency')
        ):
            by_method.append(
                {
                    'method': row['method__code'] or 'unknown',
                    'method_name': row['method__name'] or '—',
                    'currency': _normalize_currency(row['currency']),
                    'amount': float(row['amount'] or 0),
                    'count': row['count'] or 0,
                }
            )

        total_count = qs.count()
        offset = (page - 1) * page_size
        page_qs = qs[offset : offset + page_size]
        transactions = PaymentSerializer(
            page_qs, many=True, context={'request': request}
        ).data

        return Response(
            {
                'period': {
                    'from': start.date().isoformat() if start else None,
                    'to': end.date().isoformat() if end else None,
                },
                'type': (type_filter or 'all').strip().lower() or 'all',
                'totals': {
                    'completed': totals.get('completed', []),
                    'pending': totals.get('pending', []),
                    'failed': totals.get('failed', []),
                    'cancelled': totals.get('cancelled', []),
                },
                'by_method': by_method,
                'financial_summary': _financial_summary(qs, expenses),
                'expense_count': expenses.count(),
                'count': total_count,
                'page': page,
                'page_size': page_size,
                'results': transactions,
            }
        )


class AdminAccountingExportView(APIView):
    permission_classes = [IsAuthenticated, IsAppAdmin]

    def get(self, request):
        start, end = _period_bounds(request)
        type_filter = request.query_params.get('type', 'all')
        qs = Payment.objects.select_related('user', 'method').order_by('-created_at')
        qs = _apply_created_range(qs, start, end, 'created_at')
        qs = _filter_payments_by_type(qs, type_filter)
        qs = _filter_payment_search(qs, request.query_params)

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="accounting_export.csv"'
        response.write('\ufeff')  # Excel-friendly BOM
        writer = csv.writer(response, delimiter=';')
        writer.writerow(
            [
                'id',
                'reference',
                'status',
                'amount',
                'currency',
                'method',
                'type',
                'user_email',
                'client_name',
                'order_id',
                'expedition_id',
                'created_at',
            ]
        )
        for p in qs.iterator(chunk_size=200):
            writer.writerow(
                [
                    p.id,
                    p.reference,
                    p.status,
                    str(p.amount),
                    _normalize_currency(p.currency),
                    getattr(p.method, 'code', '') or '',
                    _payment_meta_type(p),
                    getattr(p.user, 'email', '') or '',
                    getattr(p.user, 'full_name', '') or '',
                    p.order_id or '',
                    p.expedition_id or '',
                    p.created_at.isoformat() if p.created_at else '',
                ]
            )
        return response


class AdminAccountingExpensesView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAppAdmin]
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        return _accounting_expenses(self.request)


class AdminAccountingExpenseDetailView(UUIDLookupMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsAppAdmin]
    serializer_class = ExpenseSerializer
    queryset = Expense.objects.select_related('client', 'recorded_by')


class AdminClientServiceView(APIView):
    permission_classes = [IsAuthenticated, IsAppAdmin]

    def get(self, request):
        search = (request.query_params.get('search') or '').strip()
        qs = User.objects.filter(role__in=CLIENT_ROLES).annotate(
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
        )
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(full_name__icontains=search)
                | Q(phone_number__icontains=search)
            )
        qs = qs.order_by('-orders_count', 'email')[:50]

        results = []
        for user in qs:
            recent_orders = list(
                user.orders.order_by('-order_date').values(
                    'id', 'status', 'total_amount', 'order_date'
                )[:5]
            )
            for o in recent_orders:
                if o.get('order_date'):
                    o['order_date'] = o['order_date'].isoformat()
                if isinstance(o.get('total_amount'), Decimal):
                    o['total_amount'] = float(o['total_amount'])

            recent_payments = Payment.objects.filter(user=user).order_by('-created_at')[:5]
            payments_data = PaymentSerializer(
                recent_payments, many=True, context={'request': request}
            ).data

            results.append(
                {
                    'id': user.id,
                    'email': user.email,
                    'full_name': user.full_name or '',
                    'phone_number': user.phone_number or '',
                    'city': getattr(user, 'city', '') or '',
                    'stars': getattr(user, 'stars', 0) or 0,
                    'is_active': user.is_active,
                    'orders_count': user.orders_count,
                    'parcels_count': user.parcels_count,
                    'parcels_received_count': user.parcels_received_count,
                    'parcels_sent_count': user.parcels_sent_count,
                    'china_warehouse_address': build_china_warehouse_address(
                        user.full_name, user.phone_number, getattr(user, 'city', '') or ''
                    ),
                    'china_air_address': build_china_air_address(
                        user.full_name, user.phone_number, getattr(user, 'city', '') or ''
                    ),
                    'china_sea_address': build_china_sea_address(
                        user.full_name, user.phone_number, getattr(user, 'city', '') or ''
                    ),
                    'recent_orders': recent_orders,
                    'recent_payments': payments_data,
                }
            )

        return Response({'count': len(results), 'results': results})
