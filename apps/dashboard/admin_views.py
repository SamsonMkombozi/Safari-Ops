"""Messages, email queue, reminders, settings, users and the activity log."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.bookings.models import BookingReminder
from apps.content import mailer
from apps.content.models import ContactMessage, EmailQueue
from apps.core.middleware import log_activity
from apps.core.models import ActivityLog
from apps.core.permissions import staff_required
from apps.core.settings_store import get_setting, set_setting

from .forms import EmergencyContactsForm, SettingsForm, UserForm
from .views import _redirect_back


def admin_role_required(view):
    @staff_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_admin_role:
            raise PermissionDenied('Admin access required.')
        return view(request, *args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


# ── Contact messages ───────────────────────────────────────────────────

@staff_required
def message_list(request):
    show = request.GET.get('show', '')
    qs = ContactMessage.objects.all()
    if show == 'unread':
        qs = qs.filter(is_read=False)
    return render(request, 'dashboard/messages/list.html', {
        'page_title': 'Contact Messages', 'page_obj': Paginator(qs, 25).get_page(request.GET.get('page')), 'show': show,
    })


@staff_required
def message_detail(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    if not msg.is_read:
        msg.is_read = True
        msg.save(update_fields=['is_read', 'updated_at'])
    return render(request, 'dashboard/messages/detail.html', {'page_title': msg.subject or 'Message', 'msg': msg})


@staff_required
@require_POST
def message_action(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    action = request.POST.get('action')
    if action == 'unread':
        msg.is_read = False
        msg.save(update_fields=['is_read', 'updated_at'])
    elif action == 'reply' and request.POST.get('body', '').strip():
        mailer.queue('reply', {'to_email': msg.email, 'to_name': msg.full_name, 'subject': f'Re: {msg.subject or "Your enquiry"}',
                               'body': escape(request.POST['body']).replace('\n', '<br>')})
        messages.success(request, f'Reply queued to {msg.email}.')
    elif action == 'to_lead':
        from apps.crm.models import Lead
        Lead.objects.create(full_name=msg.full_name, email=msg.email, phone=msg.phone, source='contact_form',
                            notes=msg.message, assigned_to=request.user)
        messages.success(request, 'Lead created from message.')
    elif action == 'delete' and request.user.may_delete:
        msg.delete()
        messages.success(request, 'Message deleted.')
        return redirect('dashboard:message_list')
    return redirect('dashboard:message_detail', pk=pk)


# ── Email queue & reminders ────────────────────────────────────────────

@staff_required
def email_queue(request):
    status = request.GET.get('status', '')
    qs = EmailQueue.objects.all()
    if status:
        qs = qs.filter(status=status)
    return render(request, 'dashboard/email_queue.html', {
        'page_title': 'Email Queue', 'page_obj': Paginator(qs, 30).get_page(request.GET.get('page')), 'status_filter': status,
        'counts': {s: EmailQueue.objects.filter(status=s).count() for s in ('pending', 'sent', 'failed')},
        'preview': EmailQueue.objects.filter(pk=request.GET.get('view')).first() if request.GET.get('view') else None,
    })


@staff_required
@require_POST
def email_queue_action(request):
    action = request.POST.get('action')
    if action == 'process':
        sent = failed = 0
        for item in EmailQueue.objects.filter(status='pending')[:50]:
            if mailer.send_queued(item):
                sent += 1
            else:
                failed += 1
        messages.success(request, f'Processed queue: {sent} sent, {failed} not sent.')
    elif action == 'retry':
        EmailQueue.objects.filter(pk=request.POST.get('id'), status='failed').update(status='pending', attempts=0)
        messages.success(request, 'Email re-queued.')
    elif action == 'delete':
        EmailQueue.objects.filter(pk=request.POST.get('id')).delete()
        messages.success(request, 'Email removed from queue.')
    return _redirect_back(request, 'dashboard:email_queue')


@staff_required
def reminder_list(request):
    status = request.GET.get('status', 'pending')
    qs = BookingReminder.objects.select_related('booking').order_by('send_at')
    if status:
        qs = qs.filter(status=status)
    return render(request, 'dashboard/reminders.html', {
        'page_title': 'Booking Reminders', 'page_obj': Paginator(qs, 30).get_page(request.GET.get('page')),
        'status_filter': status, 'statuses': BookingReminder.STATUS_CHOICES, 'now': timezone.now(),
    })


@staff_required
@require_POST
def reminder_action(request, pk):
    r = get_object_or_404(BookingReminder.objects.select_related('booking'), pk=pk)
    action = request.POST.get('action')
    if action == 'send' and r.booking:
        mailer.queue('reminder', {'to_email': r.booking.email, 'to_name': r.booking.full_name, 'subject': r.subject, 'body': r.body},
                     booking_ref=r.booking_ref)
        r.status, r.sent_at = 'sent', timezone.now()
        r.save(update_fields=['status', 'sent_at', 'updated_at'])
        messages.success(request, f'Reminder queued to {r.booking.email}.')
    elif action == 'cancel':
        r.status = 'cancelled'
        r.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Reminder cancelled.')
    return _redirect_back(request, 'dashboard:reminder_list')


# ── Settings, users, log ───────────────────────────────────────────────

@admin_role_required
def settings_view(request):
    keys = list(SettingsForm.base_fields)
    form = SettingsForm(request.POST or None, initial={k: get_setting(k) for k in keys})
    if request.method == 'POST' and form.is_valid():
        for k in keys:
            set_setting(k, form.cleaned_data[k])
        log_activity(request, request.user, 'update', 'Settings', '', 'Updated general settings')
        messages.success(request, 'Settings saved.')
        return redirect('dashboard:settings')
    return render(request, 'dashboard/simple_form.html', {'page_title': 'General Settings', 'form': form,
                                                         'intro': 'Business rules used by pricing, payments, commissions and the agent portal.'})


@staff_required
def emergency_contacts(request):
    if request.user.is_agent_role:
        raise PermissionDenied
    form = EmergencyContactsForm(request.POST or None, initial=get_setting('emergency_contacts') or {})
    if request.method == 'POST' and form.is_valid():
        set_setting('emergency_contacts', form.cleaned_data)
        messages.success(request, 'Emergency contacts saved.')
        return redirect('dashboard:emergency_contacts')
    return render(request, 'dashboard/simple_form.html', {'page_title': 'Emergency Contacts', 'form': form,
                                                         'intro': 'Shown to guides/drivers and printed on trip manifests.'})


@admin_role_required
def user_list(request):
    role = request.GET.get('role', '')
    qs = User.objects.order_by('role', 'username')
    if role:
        qs = qs.filter(role=role)
    return render(request, 'dashboard/users/list.html', {'page_title': 'Users', 'users': qs, 'role_filter': role,
                                                        'roles': User.ROLE_CHOICES})


@admin_role_required
def user_form(request, pk=None):
    user = get_object_or_404(User, pk=pk) if pk else None
    form = UserForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        if user and user == request.user and form.cleaned_data['role'] not in ('owner', 'admin'):
            messages.error(request, 'You cannot remove your own admin role.')
        else:
            saved = form.save()
            log_activity(request, request.user, 'update' if user else 'create', 'User', saved.pk, saved.username)
            messages.success(request, f'User {saved.username} saved.')
            return redirect('dashboard:user_list')
    return render(request, 'dashboard/simple_form.html', {'page_title': f'Edit user: {user.username}' if user else 'Add User',
                                                         'form': form, 'back': '/dashboard/users/'})


@admin_role_required
def activity_log(request):
    q = request.GET.get('q', '').strip()
    action = request.GET.get('action', '')
    qs = ActivityLog.objects.select_related('actor')
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(object_type__icontains=q) | Q(actor__username__icontains=q))
    if action:
        qs = qs.filter(action=action)
    return render(request, 'dashboard/activity_log.html', {
        'page_title': 'Activity Log', 'page_obj': Paginator(qs, 50).get_page(request.GET.get('page')),
        'q': q, 'action_filter': action, 'actions': ActivityLog.ACTION_CHOICES,
    })
