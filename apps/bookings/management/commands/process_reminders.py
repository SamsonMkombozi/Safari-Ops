from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.bookings.models import BookingReminder, Quotation
from apps.content import mailer


class Command(BaseCommand):
    help = 'Queue due booking reminders and expire stale quotations (legacy cron/process_reminders.php + process_quotation_expiry.php).'

    def handle(self, *args, **opts):
        now = timezone.now()
        due = BookingReminder.objects.select_related('booking').filter(status='pending', send_at__lte=now)
        queued = 0
        for r in due:
            if not r.booking or r.booking.payment_status == 'cancelled':
                r.status = 'cancelled'
            elif r.type == 'balance_due' and r.booking.payment_status == 'fully_paid':
                r.status = 'cancelled'  # nothing left to remind about
            else:
                mailer.queue('reminder', {'to_email': r.booking.email, 'to_name': r.booking.full_name,
                                          'subject': r.subject, 'body': r.body}, booking_ref=r.booking_ref)
                r.status, r.sent_at = 'sent', now
                queued += 1
            r.save(update_fields=['status', 'sent_at', 'updated_at'])
        expired = Quotation.objects.filter(status__in=['draft', 'sent', 'viewed'], valid_until__lt=timezone.localdate()).update(status='expired')
        self.stdout.write(self.style.SUCCESS(f'{queued} reminders queued, {expired} quotations expired'))
