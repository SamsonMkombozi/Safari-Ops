from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.bookings.models import Booking, Quotation
from apps.content.models import ContactMessage, CustomSafariRequest
from apps.core.permissions import staff_required
from apps.crm.models import Commission, Lead
from apps.packages.models import Package


@staff_required
def home(request):
    today = timezone.now().date()
    month_start = today.replace(day=1)

    stats = {
        'bookings_total': Booking.objects.count(),
        'bookings_this_month': Booking.objects.filter(created_at__date__gte=month_start).count(),
        'bookings_pending_payment': Booking.objects.filter(payment_status='pending').count(),
        'revenue_this_month': Booking.objects.filter(
            created_at__date__gte=month_start, payment_status__in=['deposit_paid', 'fully_paid'],
        ).aggregate(total=Sum('amount_paid'))['total'] or 0,
        'quotations_open': Quotation.objects.filter(status__in=['draft', 'sent', 'viewed']).count(),
        'leads_active': Lead.objects.exclude(pipeline_stage__in=['completed', 'lost']).count(),
        'commissions_pending': Commission.objects.filter(status='pending').aggregate(total=Sum('commission_amount'))['total'] or 0,
        'new_contact_messages': ContactMessage.objects.filter(is_read=False).count(),
        'new_custom_requests': CustomSafariRequest.objects.filter(status='new').count(),
        'active_packages': Package.objects.filter(is_active=True).count(),
    }
    recent_bookings = Booking.objects.select_related('package').order_by('-created_at')[:8]
    recent_leads = Lead.objects.select_related('agent').order_by('-created_at')[:8]

    return render(request, 'dashboard/home.html', {
        'stats': stats, 'recent_bookings': recent_bookings, 'recent_leads': recent_leads,
    })


@staff_required
def package_list(request):
    packages = Package.objects.order_by('sort_order', 'id')
    return render(request, 'dashboard/packages/list.html', {'packages': packages})


@staff_required
def package_detail(request, pk):
    package = get_object_or_404(Package, pk=pk)
    return render(request, 'dashboard/packages/detail.html', {'package': package})


@staff_required
def booking_list(request):
    status = request.GET.get('status', '')
    bookings = Booking.objects.select_related('package', 'customer').order_by('-created_at')
    if status:
        bookings = bookings.filter(payment_status=status)
    return render(request, 'dashboard/bookings/list.html', {'bookings': bookings[:200], 'status_filter': status})


@staff_required
def booking_detail(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('package', 'customer', 'quotation'), pk=pk)
    return render(request, 'dashboard/bookings/detail.html', {'booking': booking})


@staff_required
def quotation_list(request):
    status = request.GET.get('status', '')
    quotations = Quotation.objects.select_related('package', 'customer').order_by('-created_at')
    if status:
        quotations = quotations.filter(status=status)
    return render(request, 'dashboard/quotations/list.html', {'quotations': quotations[:200], 'status_filter': status})


@staff_required
def lead_list(request):
    stage = request.GET.get('stage', '')
    leads = Lead.objects.select_related('agent', 'customer').order_by('-created_at')
    if stage:
        leads = leads.filter(pipeline_stage=stage)
    return render(request, 'dashboard/leads/list.html', {
        'leads': leads[:200], 'stage_filter': stage, 'stages': Lead._meta.get_field('pipeline_stage').choices,
    })


@staff_required
def commission_list(request):
    commissions = Commission.objects.select_related('agent', 'lead').order_by('-created_at')
    return render(request, 'dashboard/commissions/list.html', {'commissions': commissions[:200]})
