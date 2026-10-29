from django.core.management.base import BaseCommand

from apps.content import mailer
from apps.content.models import EmailQueue


class Command(BaseCommand):
    help = 'Send pending queued emails (legacy cron/process_email_queue.php). Run every few minutes from cron.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **opts):
        sent = failed = 0
        for item in EmailQueue.objects.filter(status='pending').order_by('created_at')[:opts['limit']]:
            if mailer.send_queued(item):
                sent += 1
            else:
                failed += 1
        self.stdout.write(self.style.SUCCESS(f'{sent} sent, {failed} not sent'))
