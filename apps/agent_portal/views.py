from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.bookings import pricing, services
from apps.bookings.models import Booking, Quotation
from apps.content import mailer
from apps.core.middleware import log_activity
from apps.core.permissions import agent_required
from apps.core.settings_store import get_setting
from apps.crm.models import PIPELINE_STAGES, Commission, Lead

from .forms import CustomRequestForm, DirectBookingForm

WON = ('booked', 'travelled', 'completed')


def _sum(qs, field):
    return qs.aggregate(t=Sum(field))['t'] or Decimal('0')


def _my_bookings(agent):
    # Ownership via the linked quotation's creator — the legacy OwnershipScope::bookingsListSql rule.
    return Booking.objects.filter(Q(quotation__created_by=agent) | Q(created_by=agent)).distinct()


@agent_required
def home(request):
    agent = request.user
    leads = Lead.objects.filter(agent=agent)
    comm = Commission.objects.filter(agent=agent)
    month_start = timezone.localdate().replace(day=1)
    month_value = _sum(leads.filter(pipeline_stage__in=WON, converted_at__date__gte=month_start), 'booking_value')
    stats = {
        'leads_total': leads.count(), 'leads_won': leads.filter(pipeline_stage__in=WON).count(),
        'comm_pending': _sum(comm.filter(status='pending'), 'commission_amount'),
        'comm_approved': _sum(comm.filter(status='approved'), 'commission_amount'),
        'comm_paid': _sum(comm.filter(status='paid'), 'commission_amount'),
        'sales_value': _sum(leads.filter(pipeline_stage__in=WON), 'booking_value'),
        'bookings': _my_bookings(agent).count(),
        'month_value': month_value, 'target': agent.target_monthly,
        'target_pct': min(100, round(month_value * 100 / agent.target_monthly)) if agent.target_monthly else None,
        'rate': agent.commission_rate or get_setting('default_commission_rate'),
    }
    return render(request, 'agent_portal/home.html', {
        'page_title': 'My Dashboard', 'stats': stats,
        'recent_leads': leads.order_by('-created_at')[:6], 'recent_commissions': comm.order_by('-created_at')[:5],
        'direct_booking_enabled': get_setting('agent_direct_booking_enabled'),
    })


@agent_required
def lead_list(request):
    stage = request.GET.get('stage', '')
    qs = Lead.objects.filter(agent=request.user).order_by('-created_at')
    counts = dict(qs.values_list('pipeline_stage').annotate(n=Count('id')))
    if stage:
        qs = qs.filter(pipeline_stage=stage)
    return render(request, 'agent_portal/leads.html', {
        'page_title': 'My Leads', 'page_obj': Paginator(qs, 20).get_page(request.GET.get('page')),
        'stage_filter': stage, 'stages': PIPELINE_STAGES, 'counts': counts,
        'direct_booking_enabled': get_setting('agent_direct_booking_enabled'),
    })


@agent_required
def lead_detail(request, pk):
    # The agent=request.user filter IS the ownership check — someone else's lead id is a 404, not a 403.
    lead = get_object_or_404(Lead, pk=pk, agent=request.user)
    return render(request, 'agent_portal/lead_detail.html', {
        'page_title': lead.full_name, 'lead': lead, 'commission': lead.commissions.first(),
        'quotations': lead.quotations.all(), 'bookings': Booking.objects.filter(booking_ref=lead.booking_ref) if lead.booking_ref else [],
    })


@agent_required
def direct_booking(request):
    if not get_setting('agent_direct_booking_enabled'):
        messages.error(request, 'Direct booking is currently disabled — please submit a custom request instead.')
        return redirect('agent_portal:custom_request')
    form = DirectBookingForm(request.POST or None)
    preview = None
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        if request.POST.get('confirm') != '1':
            built, totals = pricing.price_package(d['package'], d['adults'], d['children'], d['country'])
            preview = {'built': built, 'totals': totals}
        else:
            try:
                booking, password, lead = services.agent_direct_booking(
                    request.user, full_name=d['full_name'], email=d['email'], phone=d['phone'], country=d['country'],
                    package=d['package'], travel_date=d['travel_date'], adults=d['adults'], children=d['children'],
                    accommodation_level=d['accommodation_level'], notes=d['notes'])
                log_activity(request, request.user, 'create', 'Booking', booking.pk, f'{booking.booking_ref} via agent portal')
                comm = lead.commissions.first()
                messages.success(request, f'Booking {booking.booking_ref} created for {booking.full_name} (${booking.total_amount:,.2f}). '
                                          f'Client tracking password: {password} — it has also been emailed to them.'
                                 + (f' Your commission: ${comm.commission_amount:,.2f} (pending approval).' if comm else ''))
                return redirect('agent_portal:lead_detail', pk=lead.pk)
            except ValueError as exc:
                messages.error(request, str(exc))
    return render(request, 'agent_portal/form.html', {
        'page_title': 'Book a Package', 'form': form, 'preview': preview,
        'intro': 'Creates a confirmed booking for your client. The price is itemised from the package itinerary; your commission is created automatically.',
        'submit_label': 'Price this booking' if not preview else 'Confirm booking',
    })


@agent_required
def custom_request(request):
    form = CustomRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        notes = [f'Duration: {d["duration_days"]} day{"s" if d["duration_days"] != 1 else ""}' + (' (dates flexible)' if d['flexible_dates'] else '')]
        if d['notes']:
            notes.append(d['notes'])
        lead = Lead.objects.create(
            full_name=d['full_name'], email=d['email'], phone=d['phone'], country=d['country'], source='agent_custom_request',
            budget_range=d['total_budget'], travel_date=d['start_date'], party_size=d['adults'] + d['children'],
            destinations=', '.join(x.strip() for x in d['destinations'].split(',') if x.strip()), notes='\n\n'.join(notes),
            agent=request.user,
        )
        log_activity(request, request.user, 'create', 'Lead', lead.pk, f'{lead.full_name} via agent custom request')
        mailer.queue('custom_request_ack', {'to_email': lead.email, 'to_name': lead.full_name, 'client_name': lead.full_name})
        messages.success(request, f'Request for {lead.full_name} submitted — our team will build a quotation and it will appear under this lead.')
        return redirect('agent_portal:lead_detail', pk=lead.pk)
    return render(request, 'agent_portal/form.html', {
        'page_title': 'Custom Safari Request', 'form': form, 'submit_label': 'Submit request',
        'intro': 'For bespoke trips with no fixed price yet — it becomes one of your leads and the office prepares a quotation.',
    })


@agent_required
def booking_list(request):
    return render(request, 'agent_portal/bookings.html', {
        'page_title': 'My Bookings', 'bookings': _my_bookings(request.user).order_by('-created_at'),
    })


@agent_required
def quotation_list(request):
    return render(request, 'agent_portal/quotations.html', {
        'page_title': 'My Quotations', 'quotations': Quotation.objects.filter(Q(created_by=request.user) | Q(lead__agent=request.user)).distinct(),
    })


@agent_required
def commission_list(request):
    status = request.GET.get('status', '')
    qs = Commission.objects.filter(agent=request.user).order_by('-created_at')
    totals = {s: _sum(qs.filter(status=s), 'commission_amount') for s in ('pending', 'approved', 'paid', 'cancelled')}
    if status:
        qs = qs.filter(status=status)
    return render(request, 'agent_portal/commissions.html', {
        'page_title': 'My Commissions', 'commissions': qs, 'totals': totals, 'status_filter': status,
        'statuses': Commission._meta.get_field('status').choices,
        'rate': request.user.commission_rate or get_setting('default_commission_rate'),
    })
