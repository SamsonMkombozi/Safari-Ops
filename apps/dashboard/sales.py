from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Quotation
from apps.content.models import CustomSafariRequest
from apps.core.middleware import log_activity
from apps.core.permissions import staff_required
from apps.crm import pipeline
from apps.crm.models import PIPELINE_STAGES, Commission, Lead

from .forms import AgentRateForm, LeadForm, QuotationForm
from .views import _redirect_back, _require_status_permission


# ── Quotations ─────────────────────────────────────────────────────────

@staff_required
def quotation_list(request):
    status = request.GET.get('status', '')
    q = request.GET.get('q', '').strip()
    qs = Quotation.objects.select_related('created_by').order_by('-created_at')
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(quote_ref__icontains=q) | Q(client_name__icontains=q) | Q(client_email__icontains=q) | Q(package_name__icontains=q))
    counts = dict(Quotation.objects.values_list('status').annotate(n=Count('id')))
    open_qs = Quotation.objects.filter(status__in=['sent', 'viewed', 'accepted'])
    total = Quotation.objects.exclude(status='draft').count()
    return render(request, 'dashboard/quotations/list.html', {
        'page_title': 'Quotations', 'page_obj': Paginator(qs, 25).get_page(request.GET.get('page')),
        'status_filter': status, 'q': q, 'counts': counts, 'statuses': Quotation.STATUS_CHOICES,
        'pipeline_value': open_qs.aggregate(t=Sum('grand_total'))['t'] or 0,
        'conversion_rate': round(counts.get('converted', 0) * 100 / total, 1) if total else 0,
    })


@staff_required
def quotation_new(request):
    initial = {'adults': 2, 'children': 0, 'rooms': 1, 'markup_pct': 0, 'discount_pct': 0, 'flight_cost': 0}
    lead = req = None
    if request.GET.get('from_lead'):
        lead = get_object_or_404(Lead, pk=request.GET['from_lead'])
        initial.update(client_name=lead.full_name, client_email=lead.email, client_phone=lead.phone,
                       client_country=lead.country, adults=lead.party_size or 2, start_date=lead.travel_date, lead_id=lead.pk)
    if request.GET.get('from_request'):
        req = get_object_or_404(CustomSafariRequest, pk=request.GET['from_request'])
        initial.update(client_name=req.full_name, client_email=req.email, client_phone=req.phone, client_country=req.country,
                       adults=req.adults or 2, children=req.children or 0, start_date=req.start_date, request_id=req.pk,
                       notes=req.message)
    form = QuotationForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        lead = Lead.objects.filter(pk=d.get('lead_id')).first() if d.get('lead_id') else None
        req = CustomSafariRequest.objects.filter(pk=d.get('request_id')).first() if d.get('request_id') else None
        extra = []
        if d.get('flight_cost'):
            extra.append({'description': 'Internal Flights', 'unit_price': float(d['flight_cost']), 'quantity_str': 'Group',
                          'amount': float(d['flight_cost']), 'category': 'transport'})
        quote = services.build_quotation(
            client={'name': d['client_name'], 'email': d['client_email'], 'phone': d['client_phone'], 'country': d['client_country']},
            package=d['package'], itinerary=d['itinerary'], adults=d['adults'], children=d['children'], rooms=d['rooms'],
            start_date=d['start_date'], accommodation_level=d['accommodation_level'], markup_pct=d['markup_pct'],
            discount_pct=d['discount_pct'], extra_items=extra, user=request.user, lead=lead, custom_request=req, notes=d['notes'],
        )
        if d.get('flight_cost'):
            Quotation.objects.filter(pk=quote.pk).update(flight_cost=d['flight_cost'], internal_flight=True)
        log_activity(request, request.user, 'create', 'Quotation', quote.pk, f'Created {quote.quote_ref}')
        messages.success(request, f'Quotation {quote.quote_ref} created — ${quote.grand_total:,.2f}.')
        return redirect('dashboard:quotation_detail', pk=quote.pk)
    return render(request, 'dashboard/quotations/new.html', {'page_title': 'New Quotation', 'form': form, 'lead': lead, 'req': req})


@staff_required
def quotation_detail(request, pk):
    quote = get_object_or_404(Quotation.objects.select_related('created_by', 'lead', 'custom_request', 'package'), pk=pk)
    cats = {}
    for li in quote.line_items:
        cats[li.get('category', 'other')] = cats.get(li.get('category', 'other'), 0) + float(li.get('amount', 0))
    return render(request, 'dashboard/quotations/detail.html', {
        'page_title': f'Quotation {quote.quote_ref}', 'quote': quote, 'categories': cats,
        'public_url': request.build_absolute_uri(f'/q/{quote.public_token}/'),
        'statuses': Quotation.STATUS_CHOICES,
    })


@staff_required
@require_POST
def quotation_action(request, pk):
    quote = get_object_or_404(Quotation, pk=pk)
    action = request.POST.get('action')
    if action == 'send':
        services.send_quotation(quote, request)
        messages.success(request, f'Quotation emailed to {quote.client_email} (queued).')
    elif action == 'status':
        _require_status_permission(request.user)
        status = request.POST.get('status')
        if status in dict(Quotation.STATUS_CHOICES) and status != 'converted':
            quote.status = status
            quote.save(update_fields=['status', 'updated_at'])
            if status == 'accepted' and quote.lead_id:
                pipeline.advance_lead(quote.lead, 'negotiation')
            if status == 'declined' and quote.lead_id and quote.lead.pipeline_stage not in ('booked', 'travelled', 'completed'):
                pipeline.set_lead_stage_manual(quote.lead, 'lost')
            messages.success(request, f'Status set to {quote.get_status_display()}.')
    elif action == 'convert':
        _require_status_permission(request.user)
        try:
            booking, password = services.convert_quotation(quote, request.user)
            log_activity(request, request.user, 'create', 'Booking', booking.pk, f'Converted {quote.quote_ref} → {booking.booking_ref}')
            msg = f'Booking {booking.booking_ref} created.'
            if password:
                msg += f' Client tracking password: {password} (also emailed).'
            messages.success(request, msg)
            return redirect('dashboard:booking_detail', pk=booking.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
    elif action == 'delete':
        if not request.user.may_delete:
            raise PermissionDenied
        ref = quote.quote_ref
        quote.delete()
        messages.success(request, f'Quotation {ref} deleted.')
        return redirect('dashboard:quotation_list')
    log_activity(request, request.user, 'update', 'Quotation', quote.pk, f'{action} on {quote.quote_ref}')
    return redirect('dashboard:quotation_detail', pk=pk)


# ── Leads ──────────────────────────────────────────────────────────────

@staff_required
def lead_list(request):
    stage = request.GET.get('stage', '')
    agent = request.GET.get('agent', '')
    q = request.GET.get('q', '').strip()
    qs = Lead.objects.select_related('agent', 'assigned_to').order_by('-created_at')
    if stage:
        qs = qs.filter(pipeline_stage=stage)
    if agent:
        qs = qs.filter(agent_id=agent)
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q) | Q(country__icontains=q) | Q(package_name__icontains=q))
    counts = dict(Lead.objects.values_list('pipeline_stage').annotate(n=Count('id')))
    return render(request, 'dashboard/leads/list.html', {
        'page_title': 'Leads Pipeline', 'page_obj': Paginator(qs, 25).get_page(request.GET.get('page')),
        'stage_filter': stage, 'agent_filter': agent, 'q': q, 'stages': PIPELINE_STAGES, 'counts': counts,
        'total_count': sum(counts.values()), 'agents': User.objects.filter(role='agent'),
        'form': LeadForm(),
    })


@staff_required
def lead_form(request, pk=None):
    lead = get_object_or_404(Lead, pk=pk) if pk else None
    form = LeadForm(request.POST or None, instance=lead)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        log_activity(request, request.user, 'update' if lead else 'create', 'Lead', saved.pk, saved.full_name)
        messages.success(request, f'Lead “{saved.full_name}” saved.')
        return redirect('dashboard:lead_list')
    return render(request, 'dashboard/simple_form.html', {
        'page_title': f'Edit lead: {lead.full_name}' if lead else 'Add Lead', 'form': form, 'back': '/dashboard/leads/',
    })


@staff_required
@require_POST
def lead_stage(request, pk):
    _require_status_permission(request.user)
    lead = get_object_or_404(Lead.objects.select_related('agent'), pk=pk)
    stage = request.POST.get('pipeline_stage')
    if stage == 'booked' and lead.agent_id and not lead.booking_value:
        messages.error(request, 'Set the lead’s booking value before marking it booked — the commission is calculated from it.')
        return _redirect_back(request, 'dashboard:lead_list')
    ok, msg, commission = pipeline.set_lead_stage_manual(lead, stage)
    if not ok:
        messages.error(request, msg)
    else:
        log_activity(request, request.user, 'status_change', 'Lead', lead.pk, f'Stage → {stage}')
        text = f'{lead.full_name} moved to {lead.get_pipeline_stage_display()}.'
        if commission:
            text += f' Commission of ${commission.commission_amount:,.2f} created for {lead.agent.get_full_name()}.'
        messages.success(request, text)
    return _redirect_back(request, 'dashboard:lead_list')


@staff_required
@require_POST
def lead_delete(request, pk):
    if not request.user.may_delete:
        raise PermissionDenied
    lead = get_object_or_404(Lead, pk=pk)
    log_activity(request, request.user, 'delete', 'Lead', lead.pk, lead.full_name)
    lead.delete()
    messages.success(request, 'Lead deleted.')
    return redirect('dashboard:lead_list')


# ── Custom safari requests ─────────────────────────────────────────────

@staff_required
def request_list(request):
    status = request.GET.get('status', '')
    qs = CustomSafariRequest.objects.order_by('-created_at')
    if status:
        qs = qs.filter(status=status)
    counts = dict(CustomSafariRequest.objects.values_list('status').annotate(n=Count('id')))
    return render(request, 'dashboard/requests/list.html', {
        'page_title': 'Custom Safari Requests', 'page_obj': Paginator(qs, 25).get_page(request.GET.get('page')),
        'status_filter': status, 'statuses': CustomSafariRequest.STATUS_CHOICES, 'counts': counts,
    })


@staff_required
def request_detail(request, pk):
    req = get_object_or_404(CustomSafariRequest, pk=pk)
    return render(request, 'dashboard/requests/detail.html', {
        'page_title': f'Request — {req.full_name}', 'req': req, 'statuses': CustomSafariRequest.STATUS_CHOICES,
        'quotations': req.quotations.all(),
    })


@staff_required
@require_POST
def request_action(request, pk):
    req = get_object_or_404(CustomSafariRequest, pk=pk)
    action = request.POST.get('action')
    if action == 'status' and request.POST.get('status') in dict(CustomSafariRequest.STATUS_CHOICES):
        req.status = request.POST['status']
        req.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Status set to {req.get_status_display()}.')
    elif action == 'to_lead':
        lead = Lead.objects.create(
            full_name=req.full_name, email=req.email, phone=req.phone, country=req.country, source='custom_request',
            travel_date=req.start_date, party_size=(req.adults or 0) + (req.children or 0) or None,
            destinations=req.destinations, budget_range=req.total_budget, notes=req.message, customer=req.customer,
            assigned_to=request.user,
        )
        pipeline.advance_custom_request(req, 'in_review')
        messages.success(request, f'Lead created for {lead.full_name}.')
        return redirect('dashboard:lead_list')
    return _redirect_back(request, 'dashboard:request_detail', pk=pk)


# ── Commissions ────────────────────────────────────────────────────────

@staff_required
def commission_list(request):
    status = request.GET.get('status', '')
    agent = request.GET.get('agent', '')
    qs = Commission.objects.select_related('agent', 'lead', 'approved_by').order_by('-created_at')
    if status:
        qs = qs.filter(status=status)
    if agent:
        qs = qs.filter(agent_id=agent)
    totals = {s: Commission.objects.filter(status=s).aggregate(t=Sum('commission_amount'))['t'] or Decimal('0')
              for s in ('pending', 'approved', 'paid', 'cancelled')}
    agents = User.objects.filter(role='agent').annotate(
        n_comm=Count('commissions'), earned=Sum('commissions__commission_amount', filter=Q(commissions__status__in=['approved', 'paid'])),
    )
    return render(request, 'dashboard/commissions/list.html', {
        'page_title': 'Commission Management', 'page_obj': Paginator(qs, 25).get_page(request.GET.get('page')),
        'status_filter': status, 'agent_filter': agent, 'totals': totals, 'agents': agents,
        'statuses': Commission._meta.get_field('status').choices, 'rate_form': AgentRateForm(),
    })


@staff_required
@require_POST
def commission_status(request, pk):
    _require_status_permission(request.user)
    commission = get_object_or_404(Commission.objects.select_related('agent'), pk=pk)
    status = request.POST.get('status')
    if status in dict(Commission._meta.get_field('status').choices):
        pipeline.set_commission_status(commission, status, request.user)
        log_activity(request, request.user, 'status_change', 'Commission', commission.pk, f'→ {status}')
        messages.success(request, f'Commission for {commission.client_name} marked {status}.')
    return _redirect_back(request, 'dashboard:commission_list')


@staff_required
@require_POST
def commission_agent_rate(request):
    if not request.user.is_admin_role:
        raise PermissionDenied('Only admins can set commission rates.')
    form = AgentRateForm(request.POST)
    if form.is_valid():
        agent = form.cleaned_data['agent']
        agent.commission_rate = form.cleaned_data['rate']
        agent.save(update_fields=['commission_rate'])
        log_activity(request, request.user, 'update', 'User', agent.pk, f'Commission rate → {agent.commission_rate}%')
        messages.success(request, f'{agent.get_full_name()} now earns {agent.commission_rate}% on new bookings.')
    return redirect('dashboard:commission_list')
