"""
Sidebar + notification-bell context for the admin panel — the same groups,
badges and role filtering as the legacy layouts/admin.php:

 - owner/admin see everything;
 - manager (legacy "staff") loses the Settings group and the two
   margin/cross-agent pages (Profitability, Agent Performance).
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

ADMIN_ONLY_URLS = {'dashboard:profitability', 'dashboard:agent_performance'}


def _groups():
    return [
        ('Dashboard', [('dashboard:home', 'Overview', 'dashboard', None)]),
        ('Operations', [
            ('dashboard:booking_list', 'Bookings', 'bookings', None),
            ('dashboard:request_list', 'Requests', 'requests', 'new_requests'),
            ('dashboard:lead_list', 'Leads', 'leads', 'new_leads'),
            ('dashboard:quotation_list', 'Quotations', 'quotations', None),
            ('dashboard:invoice_list', 'Invoices', 'invoices', None),
            ('dashboard:payment_list', 'Payments', 'commissions', None),
            ('crud:customers', 'Customers', 'customers', None),
            ('dashboard:message_list', 'Messages', 'messages', 'unread_messages'),
            ('crud:incidents', 'Incidents', 'incident', 'open_incidents'),
        ]),
        ('Communications', [
            ('crud:email-templates', 'Email Templates', 'email-template', None),
            ('dashboard:email_queue', 'Email Queue', 'email-queue', 'queue_pending'),
            ('dashboard:reminder_list', 'Reminders', 'reminders', 'reminders_due'),
        ]),
        ('Catalog', [
            ('crud:packages', 'Packages', 'packages', None),
            ('crud:itineraries', 'Itineraries', 'itineraries', None),
            ('crud:accommodations', 'Accommodations', 'accommodations', None),
            ('crud:activities', 'Activities', 'activities', None),
            ('crud:vehicles', 'Fleet', 'fleet', None),
            ('crud:park-fees', 'Park Fees', 'park-fees', None),
            ('crud:seasons', 'Seasons', 'seasons', None),
            ('dashboard:emergency_contacts', 'Emergency Contacts', 'alert', None),
        ]),
        ('People & Partners', [
            ('crud:team', 'Team', 'team', None),
            ('crud:suppliers', 'Suppliers', 'suppliers', None),
            ('crud:staff', 'Guides & Drivers', 'guide', None),
        ]),
        ('Analytics', [
            ('dashboard:profitability', 'Profitability', 'trending', None),
            ('dashboard:customer_experience', 'Customer Experience', 'star', None),
            ('crud:reviews', 'Reviews', 'star', None),
            ('dashboard:sales', 'Sales & Pipeline', 'analytics', None),
        ]),
        ('Agent', [
            ('dashboard:agent_performance', 'Agent Performance', 'target', None),
            ('dashboard:commission_list', 'Commissions', 'commissions', None),
        ]),
        ('Settings', [
            ('dashboard:settings', 'General', 'moon', None),
            ('crud:currencies', 'Currencies', 'currency', None),
            ('dashboard:user_list', 'Users', 'users', None),
            ('dashboard:activity_log', 'Activity Log', 'clock', None),
        ]),
    ]


def counts():
    from apps.bookings.models import Booking, BookingReminder
    from apps.content.models import ContactMessage, CustomSafariRequest, EmailQueue
    from apps.crm.models import Lead
    from apps.operations.models import Incident

    now = timezone.now()
    return {
        'unread_messages': ContactMessage.objects.filter(is_read=False).count(),
        'queue_pending': EmailQueue.objects.filter(status='pending').count(),
        'reminders_due': BookingReminder.objects.filter(status='pending', send_at__lte=now + timedelta(hours=24)).count(),
        'new_requests': CustomSafariRequest.objects.filter(status='new').count(),
        'open_incidents': Incident.objects.filter(status='open').count(),
        'new_leads': Lead.objects.filter(pipeline_stage='lead').count(),
        'new_bookings': Booking.objects.filter(created_at__gte=now - timedelta(hours=24)).count(),
    }


def admin_nav(request):
    path = request.path
    # request.user is absent when an error page renders before AuthenticationMiddleware ran (e.g. a 400 for a bad Host header).
    user = getattr(request, 'user', None)
    if not path.startswith(('/dashboard/', '/accounts/')) or not user or not user.is_authenticated or not user.is_staff_role:
        return {}
    from apps.bookings.models import Booking
    from apps.content.models import ContactMessage, CustomSafariRequest
    from apps.crm.models import Lead

    c = counts()
    groups = []
    for label, links in _groups():
        if label == 'Settings' and not user.is_admin_role:
            continue
        items, has_active = [], False
        for name, text, icon, badge_key in links:
            if name in ADMIN_ONLY_URLS and not user.is_admin_role:
                continue
            url = reverse(name)
            active = path == url or (url != reverse('dashboard:home') and path.startswith(url))
            has_active = has_active or active
            items.append({'url': url, 'label': text, 'icon': icon, 'active': active, 'badge': c.get(badge_key) if badge_key else None})
        if items:
            groups.append({'label': label, 'key': label.lower().replace(' & ', '-').replace(' ', '-'), 'items': items, 'has_active': has_active})

    day_ago = timezone.now() - timedelta(hours=24)
    notif = [
        {'label': 'Unread Messages', 'count': c['unread_messages'], 'url': reverse('dashboard:message_list'),
         'rows': [(m.full_name, m.message[:60]) for m in ContactMessage.objects.filter(is_read=False)[:5]]},
        {'label': 'New Requests', 'count': c['new_requests'], 'url': reverse('dashboard:request_list'),
         'rows': [(r.full_name, '') for r in CustomSafariRequest.objects.filter(status='new')[:5]]},
        {'label': 'New Leads', 'count': c['new_leads'], 'url': reverse('dashboard:lead_list'),
         'rows': [(lead.full_name, lead.source) for lead in Lead.objects.filter(pipeline_stage='lead')[:5]]},
        {'label': 'New Bookings', 'count': c['new_bookings'], 'url': reverse('dashboard:booking_list'),
         'rows': [(b.full_name, b.booking_ref) for b in Booking.objects.filter(created_at__gte=day_ago)[:5]]},
    ]
    return {
        'nav_groups': groups,
        'notif_groups': [g for g in notif if g['rows']],
        'notif_total': sum(g['count'] for g in notif),
    }
