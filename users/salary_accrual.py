"""Commission travailleur — chaque service = 100 % de recettes à part.

Exemple :
  Admin A 10 % sur Commande  → sur 100 % net Commande, A reçoit 10 %, il reste 90 %.
  Admin B  5 % sur Groupage  → sur 100 % net Groupage, B reçoit  5 %, il reste 95 %.

Base nette par service :
  encaissé_brut − part des dépenses/pertes du mois (hors catégorie Salaire)
  → réparti au prorata des encaissements de chaque service.

Puis : gagné = encaissé_net × % ; solde = gagné − déjà payé.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

from .models import AgentSalaryPayment, WORKER_SERVICE_KEYS, normalize_service_percentages

TWOPLACES = Decimal('0.01')


def _d(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal('0')


def _money(value: Decimal) -> float:
    return float(value.quantize(TWOPLACES, rounding=ROUND_HALF_UP))


def _month_bounds(day=None):
    now = timezone.localtime()
    day = day or now.date()
    start = timezone.make_aware(
        datetime.combine(day.replace(day=1), time.min),
        timezone.get_current_timezone(),
    )
    end = timezone.make_aware(
        datetime.combine(day, time.max),
        timezone.get_current_timezone(),
    )
    _, days_in_month = monthrange(day.year, day.month)
    return start, end, day, days_in_month


def _fx_rates():
    """1 USD = rate[currency]. Devises inconnues → pas de conversion (0)."""
    rates = {
        'USD': Decimal('1'),
        'GBP': Decimal('0.79'),
        'CDF': Decimal('2270'),
        'FCFA': Decimal('600'),
        'XOF': Decimal('600'),
        'CNY': Decimal('6.3'),
    }
    try:
        from pricing.models import BusinessSettings

        s = BusinessSettings.load()
        if s.usd_to_gbp and s.usd_to_gbp > 0:
            rates['GBP'] = _d(s.usd_to_gbp)
        if s.usd_to_cdf and s.usd_to_cdf > 0:
            rates['CDF'] = _d(s.usd_to_cdf)
        if s.usd_to_xof and s.usd_to_xof > 0:
            rates['FCFA'] = _d(s.usd_to_xof)
            rates['XOF'] = _d(s.usd_to_xof)
        if getattr(s, 'usd_to_cny', None) and s.usd_to_cny > 0:
            rates['CNY'] = _d(s.usd_to_cny)
    except Exception:
        pass
    return rates


def _to_usd(amount, currency, rates) -> Decimal:
    cur = (currency or 'USD').strip().upper()
    if cur == 'XOF':
        cur = 'FCFA'
    amt = _d(amount)
    if amt <= 0:
        return Decimal('0')
    if cur == 'USD':
        return amt
    rate = rates.get(cur)
    if not rate or rate <= 0:
        return Decimal('0')
    return amt / rate


def _payment_usd(payment, rates) -> Decimal:
    raw = payment.provider_raw_response if isinstance(
        payment.provider_raw_response, dict
    ) else {}
    # Préférer le montant métier (hors frais passerelle) si présent.
    service_amt = raw.get('service_amount')
    if service_amt is not None:
        try:
            return _to_usd(service_amt, payment.currency, rates)
        except Exception:
            pass
    return _to_usd(payment.amount, payment.currency, rates)


def _grouping_fee_usd(payment, rates) -> Decimal:
    raw = payment.provider_raw_response if isinstance(
        payment.provider_raw_response, dict
    ) else {}
    fee = raw.get('grouping_fee')
    if fee is None:
        exp = getattr(payment, 'expedition', None)
        if exp is not None:
            fee = getattr(exp, 'grouping_fee', None)
    return _to_usd(fee or 0, payment.currency, rates)


def monthly_collections_usd(*, start=None, end=None) -> dict[str, Decimal]:
    """Encaissements (USD) du mois par clé WORKER_SERVICE."""
    from payments.models import Payment

    if start is None or end is None:
        start, end, _, _ = _month_bounds()

    rates = _fx_rates()
    qs = (
        Payment.objects.filter(
            status='completed',
            created_at__gte=start,
            created_at__lte=end,
        )
        .select_related('expedition')
    )

    totals = {k: Decimal('0') for k in WORKER_SERVICE_KEYS}

    for pay in qs.iterator(chunk_size=200):
        raw = pay.provider_raw_response if isinstance(
            pay.provider_raw_response, dict
        ) else {}
        meta_type = (raw.get('type') or '').strip().lower()
        usd = _payment_usd(pay, rates)
        if usd <= 0:
            continue

        if meta_type == 'money_transfer':
            totals['transfers'] += usd
            continue

        if pay.order_id and meta_type != 'expedition':
            totals['orders'] += usd
            continue

        if pay.expedition_id or meta_type in ('expedition', 'grouping', 'groupage'):
            g_fee = _grouping_fee_usd(pay, rates)
            was_grouped = (
                meta_type in ('grouping', 'groupage')
                or raw.get('was_grouped') is True
                or (
                    getattr(pay, 'expedition', None) is not None
                    and (
                        getattr(pay.expedition, 'was_grouped', False)
                        or _d(getattr(pay.expedition, 'grouping_fee', 0)) > 0
                    )
                )
            )
            if was_grouped and g_fee > 0:
                totals['grouping'] += g_fee
                ship = usd - g_fee
                if ship > 0:
                    totals['shipments'] += ship
            elif was_grouped and g_fee <= 0:
                # Groupage sans fee isolé : tout sur grouping pour éviter double compte.
                totals['grouping'] += usd
            else:
                totals['shipments'] += usd
            continue

        # Autres : ignorer (pas de base client_service).

    return totals


def today_collections_usd() -> dict[str, Decimal]:
    now = timezone.localtime()
    day = now.date()
    start = timezone.make_aware(
        datetime.combine(day, time.min),
        timezone.get_current_timezone(),
    )
    end = timezone.make_aware(
        datetime.combine(day, time.max),
        timezone.get_current_timezone(),
    )
    return monthly_collections_usd(start=start, end=end)


def monthly_deductions_usd(*, start=None, end=None) -> dict[str, Decimal]:
    """Dépenses + pertes du mois en USD (hors miroirs salaire)."""
    from reports.models import Expense

    if start is None or end is None:
        start, end, _, _ = _month_bounds()
    start_day = start.date() if hasattr(start, 'date') else start
    end_day = end.date() if hasattr(end, 'date') else end
    rates = _fx_rates()
    qs = Expense.objects.filter(
        expense_date__gte=start_day,
        expense_date__lte=end_day,
    ).exclude(category__iexact='Salaire')

    expenses = Decimal('0')
    losses = Decimal('0')
    for row in qs.iterator(chunk_size=200):
        usd = _to_usd(row.amount, row.currency, rates)
        if usd <= 0:
            continue
        if (row.entry_type or Expense.ENTRY_EXPENSE) == Expense.ENTRY_LOSS:
            losses += usd
        else:
            expenses += usd
    total = expenses + losses
    return {
        'expenses': expenses.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        'losses': losses.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        'total': total.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
    }


def net_collections_after_deductions(
    gross: dict[str, Decimal],
    deductions_total: Decimal,
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """Répartit dépenses/pertes au prorata des encaissements par service."""
    nets = {k: Decimal('0') for k in WORKER_SERVICE_KEYS}
    deducted = {k: Decimal('0') for k in WORKER_SERVICE_KEYS}
    keys_with = [k for k in WORKER_SERVICE_KEYS if _d(gross.get(k, 0)) > 0]
    gross_total = sum((_d(gross.get(k, 0)) for k in keys_with), Decimal('0'))
    if gross_total <= 0 or deductions_total <= 0:
        for k in WORKER_SERVICE_KEYS:
            nets[k] = _d(gross.get(k, 0))
        return nets, deducted

    remaining = _d(deductions_total)
    for i, key in enumerate(keys_with):
        g = _d(gross.get(key, 0))
        if i == len(keys_with) - 1:
            share = remaining
        else:
            share = (deductions_total * g / gross_total).quantize(
                TWOPLACES, rounding=ROUND_HALF_UP
            )
            remaining -= share
        if share < 0:
            share = Decimal('0')
        deducted[key] = share
        net = g - share
        nets[key] = net if net > 0 else Decimal('0')
    return nets, deducted


def worker_service_balances(worker, *, collections=None, today_collections=None):
    """Chaque service = 100 % net ; le travailleur prend son % sur ce service."""
    percentages = normalize_service_percentages(
        getattr(worker, 'service_percentages', None)
    )
    # Uniquement les services où CE travailleur a un %.
    active_keys = [k for k in WORKER_SERVICE_KEYS if _d(percentages.get(k, 0)) > 0]
    start, end, day, days_in_month = _month_bounds()
    if collections is None:
        collections = monthly_collections_usd(start=start, end=end)
    if today_collections is None:
        today_collections = today_collections_usd()

    deductions = monthly_deductions_usd(start=start, end=end)
    net_month, deducted_map = net_collections_after_deductions(
        collections, deductions['total']
    )
    # Aujourd’hui : même ratio net/brut pour rester cohérent.
    gross_month_total = sum(
        (_d(collections.get(k, 0)) for k in WORKER_SERVICE_KEYS),
        Decimal('0'),
    )
    net_month_total = sum(
        (_d(net_month.get(k, 0)) for k in WORKER_SERVICE_KEYS),
        Decimal('0'),
    )
    net_ratio = (
        (net_month_total / gross_month_total)
        if gross_month_total > 0
        else Decimal('1')
    )

    paid_rows = (
        AgentSalaryPayment.objects.filter(
            worker=worker,
            status=AgentSalaryPayment.STATUS_PAID,
            paid_at__gte=start,
            paid_at__lte=end,
        )
        .values('service')
        .annotate(total=Sum('amount'))
    )
    paid_map = {k: Decimal('0') for k in WORKER_SERVICE_KEYS}
    unassigned_paid = Decimal('0')
    for row in paid_rows:
        key = (row.get('service') or '').strip().lower()
        amt = _d(row.get('total'))
        if key in paid_map:
            paid_map[key] += amt
        else:
            unassigned_paid += amt

    collected_total = sum(
        (_d(net_month.get(k, 0)) for k in active_keys),
        Decimal('0'),
    )
    collected_gross_total = sum(
        (_d(collections.get(k, 0)) for k in active_keys),
        Decimal('0'),
    )
    collected_today_total = sum(
        (
            (_d(today_collections.get(k, 0)) * net_ratio).quantize(
                TWOPLACES, rounding=ROUND_HALF_UP
            )
            for k in active_keys
        ),
        Decimal('0'),
    )

    by_service = []
    earned_total = Decimal('0')
    earned_today_total = Decimal('0')

    for key in active_keys:
        pct = _d(percentages.get(key, 0))
        collected_gross = _d(collections.get(key, 0))
        collected = _d(net_month.get(key, 0))
        deducted = _d(deducted_map.get(key, 0))
        collected_today = (
            _d(today_collections.get(key, 0)) * net_ratio
        ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        # Sur 100 % NET de CE service → part travailleur.
        earned = (collected * pct / Decimal('100')).quantize(
            TWOPLACES, rounding=ROUND_HALF_UP
        )
        earned_today = (collected_today * pct / Decimal('100')).quantize(
            TWOPLACES, rounding=ROUND_HALF_UP
        )
        remaining_pct = (Decimal('100') - pct).quantize(
            TWOPLACES, rounding=ROUND_HALF_UP
        )
        if remaining_pct < 0:
            remaining_pct = Decimal('0')
        earned_total += earned
        earned_today_total += earned_today
        by_service.append(
            {
                'service': key,
                'percent': float(pct),
                'remaining_percent': float(remaining_pct),
                'collected_gross': _money(collected_gross),
                'deductions': _money(deducted),
                'collected': _money(collected),  # net = base du %
                'earned': _money(earned),
                'paid': 0.0,  # rempli après répartition des paiements
                'amount': 0.0,
                'balance': 0.0,
            }
        )

    # Répartir les paiements sans service au prorata des gains.
    if unassigned_paid > 0 and earned_total > 0:
        for row in by_service:
            share = _d(row['earned']) / earned_total
            paid_map[row['service']] += (unassigned_paid * share).quantize(
                TWOPLACES, rounding=ROUND_HALF_UP
            )

    balance_total = Decimal('0')
    for row in by_service:
        key = row['service']
        earned = _d(row['earned'])
        paid = paid_map.get(key, Decimal('0')).quantize(
            TWOPLACES, rounding=ROUND_HALF_UP
        )
        balance = earned - paid
        if balance < 0:
            balance = Decimal('0')
        row['paid'] = _money(paid)
        row['amount'] = _money(balance)
        row['balance'] = _money(balance)
        balance_total += balance

    return {
        'percentages': percentages,
        'currency': 'USD',
        # Solde dû (commission − payé).
        'month_total': _money(balance_total),
        'month_today': _money(earned_today_total),
        # Base du % = encaissé NET (après dépenses/pertes).
        'collected_total': _money(collected_total),
        'collected_gross_total': _money(collected_gross_total),
        'collected_today_total': _money(collected_today_total),
        'expenses_total': _money(deductions['expenses']),
        'losses_total': _money(deductions['losses']),
        'deductions_total': _money(deductions['total']),
        'earned_total': _money(earned_total),
        'month_progress_percent': round((day.day / max(days_in_month, 1)) * 100),
        'by_service': by_service,
        'collections': {k: _money(_d(net_month.get(k, 0))) for k in active_keys},
        'collections_gross': {
            k: _money(_d(collections.get(k, 0))) for k in active_keys
        },
    }


def balances_for_services(worker, services: list[str]) -> list[dict]:
    """Soldes > 0 pour les services demandés (paiement multi)."""
    dash = worker_service_balances(worker)
    wanted = {s.strip().lower() for s in services if s}
    rows = []
    for row in dash['by_service']:
        if row['service'] not in wanted:
            continue
        if _d(row['balance']) <= 0:
            continue
        rows.append(row)
    return rows
