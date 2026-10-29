from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.bookings import pricing, services
from apps.bookings.models import Booking, BookingReminder, Payment, Quotation
from apps.content.models import ContactMessage, CustomSafariRequest
from apps.core.middleware import log_activity
from apps.core.permissions import staff_required
from apps.core.settings_store import get_setting
from apps.crm.models import Commission, Customer, Lead
from apps.operations.models import BookingAssignment, Incident
from apps.packages.models import Package

from .forms import AssignmentForm, BookingEditForm, PaymentForm, StatusForm


def _sum(qs, field):
    return qs.aggregate(t=Sum(field))['t'] or Decimal('0')


@staff_required
def home(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    live = Booking.objects.exclude(payment_status='cancelled')
    balance_days = int(get_setting('balance_days'))

    stats = {
        'bookings_month': Booking.objects.filter(created_at__date__gte=month_start).count(),
        'sales_month': _sum(live.filter(created_at__date__gte=month_start), 'total_amount'),
        'collected_month': _sum(Payment.objects.filter(received_at__gte=month_start), 'amount'),
        'collected_total': _sum(Payment.objects.all(), 'amount'),
        'outstanding': _sum(live, 'total_amount') - _sum(live, 'amount_paid'),
        'overdue_balances': live.exclude(payment_status='fully_paid').filter(travel_date__lte=today + timedelta(days=balance_days)).count(),
        'pending_quotes': Quotation.objects.filter(status__in=['draft', 'sent', 'viewed']).count(),
        'pipeline_value': _sum(Quotation.objects.filter(status__in=['sent', 'viewed', 'accepted']), 'grand_total'),
        'new_requests': CustomSafariRequest.objects.filter(status='new').count(),
        'unread_messages': ContactMessage.objects.filter(is_read=False).count(),
        'pending_reminders': BookingReminder.objects.filter(status='pending').count(),
        'leads_active': Lead.objects.exclude(pipeline_stage__in=['completed', 'lost']).count(),
        'commissions_due': _sum(Commission.objects.filter(status__in=['pending', 'approved']), 'commission_amount'),
        'open_incidents': Incident.objects.filter(status='open').count(),
    }
    gp = sum((b.gross_profit for b in live.filter(created_at__date__gte=month_start)), Decimal('0'))
    stats['profit_month'] = gp

    upcoming = live.filter(travel_date__gte=today, travel_date__lte=today + timedelta(days=30)).order_by('travel_date')[:8]
    recent_bookings = Booking.objects.order_by('-created_at')[:8]
    pipeline = list(Lead.objects.values('pipeline_stage').annotate(n=Count('id'), v=Sum('booking_value')))
    stage_labels = dict(Lead._meta.get_field('pipeline_stage').choices)
    pipeline = sorted(({'stage': p['pipeline_stage'], 'label': stage_labels.get(p['pipeline_stage']), 'n': p['n'], 'v': p['v'] or 0}
                       for p in pipeline), key=lambda p: list(stage_labels).index(p['stage']))
    max_n = max([p['n'] for p in pipeline] or [1])
    for p in pipeline:
        p['pct'] = round(p['n'] * 100 / max_n)

    return render(request, 'dashboard/home.html', {
        'page_title': 'Overview', 'stats': stats, 'upcoming': upcoming, 'recent_bookings': recent_bookings,
        'pipeline': pipeline, 'requests': CustomSafariRequest.objects.filter(status='new')[:5],
    })


# ── Bookings ───────────────────────────────────────────────────────────

@staff_required
def booking_list(request):
    status = request.GET.get('status', '')
    q = request.GET.get('q', '').strip()
    when = request.GET.get('when', '')
    qs = Booking.objects.select_related('package', 'quotation__created_by').order_by('-created_at')
    if status:
        qs = qs.filter(payment_status=status)
    if q:
        qs = qs.filter(Q(booking_ref__icontains=q) | Q(full_name__icontains=q) | Q(email__icontains=q) | Q(package_name__icontains=q))
    today = timezone.localdate()
    if when == 'upcoming':
        qs = qs.filter(travel_date__gte=today).order_by('travel_date')
    elif when == 'past':
        qs = qs.filter(travel_date__lt=today)
    counts = dict(Booking.objects.values_list('payment_status').annotate(n=Count('id')))
    return render(request, 'dashboard/bookings/list.html', {
        'page_title': 'Bookings', 'page_obj': Paginator(qs, 25).get_page(request.GET.get('page')),
        'status_filter': status, 'q': q, 'when': when, 'counts': counts, 'total_count': sum(counts.values()),
        'statuses': Booking.PAYMENT_STATUS_CHOICES,
    })


@staff_required
def booking_detail(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('package', 'customer', 'quotation__created_by', 'quotation__lead'), pk=pk)
    return render(request, 'dashboard/bookings/detail.html', {
        'page_title': f'Booking {booking.booking_ref}', 'booking': booking,
        'payments': booking.payments.select_related('recorded_by'),
        'reminders': booking.reminders.all(),
        'assignments': booking.assignments.select_related('staff', 'vehicle'),
        'incidents': Incident.objects.filter(booking_ref=booking.booking_ref),
        'commission': Commission.objects.filter(Q(booking_ref=booking.booking_ref) | Q(lead__booking_ref=booking.booking_ref)).first(),
        'payment_form': PaymentForm(initial={'received_at': timezone.localdate(), 'amount': booking.balance_due}),
        'status_form': StatusForm(initial={'status': booking.payment_status}),
        'assignment_form': AssignmentForm(),
        'line_items': booking.quotation.line_items if booking.quotation_id else [],
    })


def _require_status_permission(user):
    if not user.may_change_status:
        raise PermissionDenied('You do not have permission to change statuses.')


@staff_required
@require_POST
def booking_record_payment(request, pk):
    _require_status_permission(request.user)
    booking = get_object_or_404(Booking, pk=pk)
    form = PaymentForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        try:
            booking, payment = services.record_payment(booking, d['amount'], d['method'], d['reference'], d['received_at'],
                                                       d['notes'], request.user, d.get('kind') or None)
            log_activity(request, request.user, 'create', 'Payment', payment.pk if payment else '', f'{booking.booking_ref}: ${d["amount"]}')
            messages.success(request, f'Payment of ${d["amount"]:,.2f} recorded — booking is now {booking.get_payment_status_display()}.')
        except ValueError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'Payment not recorded: ' + '; '.join(f'{k}: {v[0]}' for k, v in form.errors.items()))
    return redirect('dashboard:booking_detail', pk=pk)


@staff_required
@require_POST
def booking_status(request, pk):
    _require_status_permission(request.user)
    booking = get_object_or_404(Booking, pk=pk)
    form = StatusForm(request.POST)
    if form.is_valid():
        try:
            booking = services.set_payment_status(booking, form.cleaned_data['status'], form.cleaned_data.get('amount_paid'), request.user)
            log_activity(request, request.user, 'status_change', 'Booking', booking.pk, f'{booking.booking_ref} → {booking.payment_status}')
            messages.success(request, f'Status updated to {booking.get_payment_status_display()}.')
        except ValueError as exc:
            messages.error(request, str(exc))
    return _redirect_back(request, 'dashboard:booking_detail', pk=pk)


def _redirect_back(request, fallback, **kwargs):
    """Honour a same-site `next` (list pages post status changes inline), otherwise go to the fallback."""
    nxt = request.POST.get('next', '')
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect(fallback, **kwargs)


@staff_required
def booking_edit(request, pk):
    if not request.user.is_admin_role:
        raise PermissionDenied('Only admins can edit booking details.')
    booking = get_object_or_404(Booking, pk=pk)
    form = BookingEditForm(request.POST or None, instance=booking)
    if request.method == 'POST' and form.is_valid():
        form.save()
        log_activity(request, request.user, 'update', 'Booking', booking.pk, f'Edited {booking.booking_ref}')
        messages.success(request, 'Booking updated.')
        return redirect('dashboard:booking_detail', pk=pk)
    return render(request, 'dashboard/simple_form.html', {
        'page_title': f'Edit {booking.booking_ref}', 'form': form, 'back': booking_detail_url(booking),
    })


def booking_detail_url(booking):
    from django.urls import reverse
    return reverse('dashboard:booking_detail', args=[booking.pk])


@staff_required
@require_POST
def booking_assign(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    form = AssignmentForm(request.POST)
    if form.is_valid() and (form.cleaned_data['staff'] or form.cleaned_data['vehicle']):
        BookingAssignment.objects.create(booking=booking, **form.cleaned_data)
        messages.success(request, 'Assignment added.')
    else:
        messages.error(request, 'Pick a guide/driver or a vehicle to assign.')
    return redirect('dashboard:booking_detail', pk=pk)


@staff_required
@require_POST
def booking_unassign(request, pk, assignment_id):
    BookingAssignment.objects.filter(pk=assignment_id, booking_id=pk).delete()
    messages.success(request, 'Assignment removed.')
    return redirect('dashboard:booking_detail', pk=pk)


@staff_required
@require_POST
def booking_reset_tracking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    password = booking.set_tracking_password()
    booking.save(update_fields=['tracking_password_hash'])
    log_activity(request, request.user, 'update', 'Booking', booking.pk, 'Reset tracking password')
    messages.success(request, f'New tracking password for {booking.booking_ref}: {password} — share it with the client now, it is not shown again.')
    return redirect('dashboard:booking_detail', pk=pk)


# ── Payments & invoices (monetisation) ────────────────────────────────

@staff_required
def payment_list(request):
    method = request.GET.get('method', '')
    qs = Payment.objects.select_related('booking', 'recorded_by')
    if method:
        qs = qs.filter(method=method)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    by_method = list(Payment.objects.values('method').annotate(n=Count('id'), total=Sum('amount')).order_by('-total'))
    labels = dict(Payment.METHOD_CHOICES)
    for m in by_method:
        m['label'] = labels.get(m['method'], m['method'])
    return render(request, 'dashboard/payments/list.html', {
        'page_title': 'Payments', 'page_obj': Paginator(qs, 30).get_page(request.GET.get('page')),
        'method_filter': method, 'methods': Payment.METHOD_CHOICES, 'by_method': by_method,
        'collected_total': _sum(Payment.objects.all(), 'amount'),
        'collected_month': _sum(Payment.objects.filter(received_at__gte=month_start), 'amount'),
        'refunds': _sum(Payment.objects.filter(amount__lt=0), 'amount'),
    })


@staff_required
def invoice_list(request):
    status = request.GET.get('status', '')
    qs = Booking.objects.exclude(payment_status='cancelled').order_by('-created_at')
    if status == 'paid':
        qs = qs.filter(payment_status='fully_paid')
    elif status == 'partial':
        qs = qs.filter(payment_status='deposit_paid')
    elif status == 'unpaid':
        qs = qs.filter(payment_status='pending')
    elif status == 'overdue':
        qs = qs.exclude(payment_status='fully_paid').filter(travel_date__lte=timezone.localdate() + timedelta(days=int(get_setting('balance_days'))))
    live = Booking.objects.exclude(payment_status='cancelled')
    return render(request, 'dashboard/invoices/list.html', {
        'page_title': 'Invoices', 'page_obj': Paginator(qs, 25).get_page(request.GET.get('page')), 'status_filter': status,
        'invoiced': _sum(live, 'total_amount'), 'paid': _sum(live, 'amount_paid'),
        'outstanding': _sum(live, 'total_amount') - _sum(live, 'amount_paid'),
    })


@staff_required
def invoice_detail(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('quotation'), pk=pk)
    vat_rate = Decimal(str(get_setting('vat_rate')))
    total = booking.total_amount or Decimal('0')
    subtotal = (total / (1 + vat_rate)).quantize(Decimal('0.01'))
    return render(request, 'dashboard/invoices/detail.html', {
        'page_title': f'Invoice {booking.booking_ref}', 'booking': booking,
        'line_items': booking.quotation.line_items if booking.quotation_id else [],
        'subtotal': subtotal, 'vat': total - subtotal, 'vat_pct': vat_rate * 100,
        'payments': booking.payments.all(), 'today': timezone.localdate(),
        'bank': {k: get_setting(k) for k in ('bank_name', 'bank_account_name', 'bank_account_no', 'bank_swift', 'wise_email')},
        'is_paid': booking.payment_status == 'fully_paid',
    })


# ── Customers & packages ───────────────────────────────────────────────

@staff_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    bookings = Booking.objects.filter(Q(customer=customer) | Q(email__iexact=customer.email)).distinct()
    return render(request, 'dashboard/customers/detail.html', {
        'page_title': customer.full_name, 'customer': customer, 'bookings': bookings,
        'quotations': Quotation.objects.filter(Q(customer=customer) | Q(client_email__iexact=customer.email)).distinct(),
        'leads': Lead.objects.filter(Q(customer=customer) | Q(email__iexact=customer.email)).distinct(),
        'lifetime_value': _sum(bookings.exclude(payment_status='cancelled'), 'total_amount'),
        'paid': _sum(bookings, 'amount_paid'),
    })


@staff_required
def package_detail(request, pk):
    package = get_object_or_404(Package.objects.select_related('itinerary'), pk=pk)
    built, t = pricing.price_package(package, 2, 0)
    built1, t1 = pricing.price_package(package, 1, 0)
    sold = Booking.objects.filter(package=package).exclude(payment_status='cancelled')
    return render(request, 'dashboard/packages/detail.html', {
        'page_title': package.name, 'package': package, 'built': built, 'totals': t, 'totals_1pax': t1,
        'supplier_cost_2pax': pricing.supplier_cost(built['line_items']),
        'sold_count': sold.count(), 'sold_value': _sum(sold, 'total_amount'),
    })


@staff_required
def supplier_contract(request, pk):
    """Contracts live outside the public media path — this is the only way to download one."""
    from django.http import FileResponse, Http404

    from apps.operations.models import Supplier
    supplier = get_object_or_404(Supplier, pk=pk)
    if not supplier.contract:
        raise Http404
    log_activity(request, request.user, 'view', 'Supplier', supplier.pk, f'Downloaded contract for {supplier.name}')
    return FileResponse(supplier.contract.open('rb'), as_attachment=True,
                        filename=f'{supplier.name} contract.pdf', content_type='application/pdf')


@staff_required
@require_POST
def package_reprice(request, pk):
    package = get_object_or_404(Package, pk=pk)
    _, t = pricing.price_package(package, 1, 0)
    package.price_1pax = t['grand_total']
    package.save(update_fields=['price_1pax', 'updated_at'])
    log_activity(request, request.user, 'update', 'Package', package.pk, f'Repriced to {t["grand_total"]}')
    messages.success(request, f'“From” price updated to ${t["grand_total"]:,.2f} (1 traveler, itemised from the itinerary).')
    return redirect('dashboard:package_detail', pk=pk)
