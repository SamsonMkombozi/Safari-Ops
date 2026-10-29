"""Sales & pipeline, profitability, customer experience and agent performance dashboards (the legacy dashboard_*.php pages)."""
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import pricing
from apps.bookings.models import Booking, Payment, Quotation
from apps.content.models import Review
from apps.core.permissions import staff_required
from apps.core.settings_store import get_setting
from apps.crm.models import PIPELINE_STAGES, Commission, Lead
from apps.operations.models import Incident
from apps.packages.models import Package


def _months(n=12):
    today = timezone.localdate().replace(day=1)
    out = []
    for i in range(n - 1, -1, -1):
        y, m = today.year, today.month - i
        while m <= 0:
            m += 12
            y -= 1
        out.append(today.replace(year=y, month=m))
    return out


def _series(qs, date_field, value_field=None, months=None):
    """Monthly totals bucketed in Python — TruncMonth on a datetime needs MySQL's timezone tables, which aren't guaranteed to be loaded."""
    months = months or _months()
    found = {}
    cols = (date_field, value_field) if value_field else (date_field,)
    start = months[0]
    if qs.model._meta.get_field(date_field).get_internal_type() == 'DateTimeField':
        # aware local midnight, not a naive date — otherwise the month boundary shifts by the UTC offset
        start = timezone.make_aware(timezone.datetime(start.year, start.month, 1))
    for row in qs.filter(**{f'{date_field}__gte': start}).values_list(*cols):
        d = row[0]
        if hasattr(d, 'astimezone'):
            d = timezone.localtime(d).date()
        key = d.replace(day=1)
        found[key] = found.get(key, 0) + (row[1] or 0 if value_field else 1)
    return [(m, found.get(m, 0)) for m in months]


def _with_pct(series):
    peak = max([float(v) for _, v in series] or [0]) or 1
    return [{'label': m.strftime('%b %y'), 'value': v, 'pct': round(float(v) * 100 / peak)} for m, v in series]


@staff_required
def sales(request):
    live = Booking.objects.exclude(payment_status='cancelled')
    months = _months()
    revenue = _with_pct(_series(live, 'created_at', 'total_amount', months))
    collected = _with_pct(_series(Payment.objects.all(), 'received_at', 'amount', months))
    bookings = _with_pct(_series(Booking.objects.all(), 'created_at', None, months))
    stage_counts = dict(Lead.objects.values_list('pipeline_stage').annotate(n=Count('id')))
    funnel = [{'stage': s, 'label': lbl, 'n': stage_counts.get(s, 0)} for s, lbl in PIPELINE_STAGES]
    peak = max([f['n'] for f in funnel] or [1]) or 1
    for f in funnel:
        f['pct'] = round(f['n'] * 100 / peak)
    quotes = Quotation.objects.exclude(status='draft')
    q_total = quotes.count()
    sources = Lead.objects.values('source').annotate(n=Count('id'), won=Count('id', filter=Q(pipeline_stage__in=['booked', 'travelled', 'completed']))).order_by('-n')
    top_packages = live.values('package_name').annotate(n=Count('id'), v=Sum('total_amount')).order_by('-v')[:8]
    countries = live.exclude(country='').values('country').annotate(n=Count('id'), v=Sum('total_amount')).order_by('-v')[:8]
    total_rev = live.aggregate(t=Sum('total_amount'))['t'] or 0
    return render(request, 'dashboard/analytics/sales.html', {
        'page_title': 'Sales & Pipeline', 'revenue': revenue, 'collected': collected, 'bookings': bookings, 'funnel': funnel,
        'q_total': q_total, 'q_converted': quotes.filter(status='converted').count(),
        'q_conversion': round(quotes.filter(status='converted').count() * 100 / q_total, 1) if q_total else 0,
        'avg_booking': (total_rev / live.count()) if live.count() else 0, 'total_rev': total_rev,
        'sources': sources, 'top_packages': top_packages, 'countries': countries,
    })


@staff_required
def profitability(request):
    if not request.user.is_admin_role:
        raise PermissionDenied('Profitability is restricted to admins.')
    vat = Decimal(str(get_setting('vat_rate')))
    labels = OrderedDict([('accommodation', 'Accommodation'), ('transport', 'Transport'), ('park_fee', 'Park Fees'),
                          ('activity', 'Activities'), ('other', 'Other Supplier')])
    breakdown = []
    for p in Package.objects.select_related('itinerary').filter(is_active=True):
        cats = {k: 0.0 for k in labels}
        if p.itinerary and p.itinerary.days:
            built = pricing.build(p.itinerary.days, 1, 0, False)
            for li in built['line_items']:
                cats[li['category'] if li['category'] in cats else 'other'] += li['amount']
        supplier = sum(cats.values())
        price = float(p.price_1pax)
        net = price / (1 + float(vat))
        breakdown.append({'package': p, 'price': price, 'net': net, 'cats': [cats[k] for k in labels], 'supplier': supplier,
                          'margin': round((net - supplier) / net * 100, 1) if net > 0 and supplier > 0 else None,
                          'profit': net - supplier})
    breakdown.sort(key=lambda b: (b['margin'] is None, -(b['margin'] or 0)))

    since = timezone.now() - timedelta(days=365)
    realized = Booking.objects.exclude(payment_status='cancelled').filter(created_at__gte=since)
    revenue = sum((b.net_revenue for b in realized), Decimal('0'))
    cost = sum((b.supplier_cost for b in realized), Decimal('0'))
    commissions = Commission.objects.exclude(status='cancelled').filter(created_at__gte=since).aggregate(t=Sum('commission_amount'))['t'] or Decimal('0')
    per_pkg = {}
    for b in realized:
        row = per_pkg.setdefault(b.package_name or '—', {'name': b.package_name or '—', 'n': 0, 'rev': Decimal('0'), 'cost': Decimal('0')})
        row['n'] += 1
        row['rev'] += b.net_revenue
        row['cost'] += b.supplier_cost
    for row in per_pkg.values():
        row['profit'] = row['rev'] - row['cost']
        row['margin'] = round(row['profit'] * 100 / row['rev'], 1) if row['rev'] else None
    return render(request, 'dashboard/analytics/profitability.html', {
        'page_title': 'Profitability', 'labels': list(labels.values()), 'breakdown': breakdown,
        'revenue': revenue, 'cost': cost, 'gross': revenue - cost, 'commissions': commissions,
        'net': revenue - cost - commissions, 'margin': round((revenue - cost) * 100 / revenue, 1) if revenue else 0,
        'per_package': sorted(per_pkg.values(), key=lambda r: -r['profit']), 'count': realized.count(),
    })


@staff_required
def customer_experience(request):
    reviews = Review.objects.all()
    nps_rows = reviews.exclude(nps_score=None)
    n = nps_rows.count()
    promoters = nps_rows.filter(nps_score__gte=9).count()
    detractors = nps_rows.filter(nps_score__lte=6).count()
    dist = {r: reviews.filter(rating=r).count() for r in range(5, 0, -1)}
    peak = max(dist.values() or [1]) or 1
    return render(request, 'dashboard/analytics/customer_experience.html', {
        'page_title': 'Customer Experience', 'count': reviews.count(), 'avg': reviews.aggregate(a=Avg('rating'))['a'] or 0,
        'nps': round((promoters - detractors) * 100 / n) if n else None, 'promoters': promoters, 'detractors': detractors,
        'passives': n - promoters - detractors,
        'dist': [{'stars': k, 'n': v, 'pct': round(v * 100 / peak)} for k, v in dist.items()],
        'recent': reviews[:10], 'incidents': Incident.objects.values('incident_type').annotate(n=Count('id')).order_by('-n'),
        'open_incidents': Incident.objects.filter(status='open').count(),
        'repeat_customers': Booking.objects.values('email').annotate(n=Count('id')).filter(n__gt=1).count(),
    })


@staff_required
def agent_performance(request):
    if not request.user.is_admin_role:
        raise PermissionDenied('Agent performance is restricted to admins.')
    month_start = timezone.localdate().replace(day=1)
    rows = []
    for a in User.objects.filter(role='agent'):
        leads = Lead.objects.filter(agent=a)
        won = leads.filter(pipeline_stage__in=['booked', 'travelled', 'completed'])
        comm = Commission.objects.filter(agent=a)
        month_value = won.filter(converted_at__date__gte=month_start).aggregate(t=Sum('booking_value'))['t'] or Decimal('0')
        rows.append({
            'agent': a, 'leads': leads.count(), 'won': won.count(),
            'conversion': round(won.count() * 100 / leads.count(), 1) if leads.count() else 0,
            'value': won.aggregate(t=Sum('booking_value'))['t'] or 0,
            'pending': comm.filter(status='pending').aggregate(t=Sum('commission_amount'))['t'] or 0,
            'approved': comm.filter(status='approved').aggregate(t=Sum('commission_amount'))['t'] or 0,
            'paid': comm.filter(status='paid').aggregate(t=Sum('commission_amount'))['t'] or 0,
            'month_value': month_value, 'target': a.target_monthly,
            'target_pct': min(100, round(month_value * 100 / a.target_monthly)) if a.target_monthly else None,
        })
    rows.sort(key=lambda r: -float(r['value']))
    return render(request, 'dashboard/analytics/agents.html', {'page_title': 'Agent Performance', 'rows': rows})
