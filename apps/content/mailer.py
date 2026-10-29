"""
Queue-only outbound mail, same contract as the legacy App\\Mail\\Mailer::queue():
a request never blocks on SMTP. A DB-stored EmailTemplate (template_key)
overrides the built-in default subject/body; both are rendered with
Django's template engine against the given context.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger('apps.mailer')

DEFAULT_TEMPLATES = {
    'booking_confirmation': (
        'Booking confirmed — {{ booking_ref }}',
        '<p>Dear {{ client_name }},</p><p>Thank you for booking <strong>{{ package_name }}</strong> with {{ site_name }}.</p>'
        '<p>Booking reference: <strong>{{ booking_ref }}</strong><br>Tracking password: <strong>{{ tracking_password }}</strong><br>'
        'Travel date: {{ travel_date }} · Travelers: {{ travelers }}</p>'
        '<p>Total: ${{ total_amount }} · Deposit due: ${{ deposit_amount }}</p><p>Karibu sana!</p>',
    ),
    'deposit_receipt': (
        'Deposit received — {{ booking_ref }}',
        '<p>Dear {{ client_name }},</p><p>We have received your payment of <strong>${{ amount }}</strong> for booking {{ booking_ref }}.</p>'
        '<p>Paid to date: ${{ amount_paid }} · Balance due: ${{ balance_due }}</p>',
    ),
    'invoice_paid': (
        'Invoice — {{ booking_ref }} (paid in full)',
        '<p>Dear {{ client_name }},</p><p>Your booking {{ booking_ref }} is now <strong>fully paid</strong> (${{ total_amount }}). '
        'Your final invoice is available on request. We look forward to welcoming you!</p>',
    ),
    'quotation_sent': (
        'Your safari quotation {{ quote_ref }}',
        '<p>Dear {{ client_name }},</p><p>Please find your quotation for <strong>{{ package_name }}</strong>: '
        '${{ grand_total }} total (${{ per_person }} per person), valid until {{ valid_until }}.</p>'
        '<p><a href="{{ view_url }}">View your quotation online</a></p>',
    ),
    'lead_converted': (
        'Commission earned — {{ client_name }}',
        '<p>Hi {{ agent_name }},</p><p>Your lead <strong>{{ client_name }}</strong> booked {{ package_name }} '
        '(${{ booking_value }}). Commission: <strong>${{ commission_amount }}</strong> at {{ commission_rate }}% — pending approval.</p>',
    ),
    'commission_approved': (
        'Commission approved — {{ client_name }}',
        '<p>Hi {{ agent_name }},</p><p>Your commission of <strong>${{ commission_amount }}</strong> for {{ client_name }} has been approved.</p>',
    ),
    'commission_paid': (
        'Commission paid — {{ client_name }}',
        '<p>Hi {{ agent_name }},</p><p>Your commission of <strong>${{ commission_amount }}</strong> for {{ client_name }} has been paid.</p>',
    ),
    'custom_request_ack': (
        'We received your safari request',
        '<p>Dear {{ client_name }},</p><p>Thank you — a safari specialist will be in touch within 24 hours with a tailored proposal.</p>',
    ),
    'reminder': ('{{ subject }}', '{{ body|safe }}'),
    # body is escaped by the caller before newlines become <br>
    'reply': ('{{ subject }}', '{{ body|safe }}'),
}


def render_template(template_key, context):
    from apps.content.models import EmailTemplate
    from apps.core.settings_store import get_setting
    context = {'site_name': get_setting('app_name'), **context}
    custom = EmailTemplate.objects.filter(template_key=template_key).first()
    subject_src, body_src = (custom.subject, custom.body_html) if custom else DEFAULT_TEMPLATES.get(template_key, ('{{ subject }}', '{{ body }}'))
    ctx = Context(context)
    return Template(subject_src).render(ctx).strip(), Template(body_src).render(ctx)


def queue(template_key, context, booking_ref=''):
    """Render and enqueue. Never raises into the caller — a mail problem must not roll back the business write that triggered it."""
    from apps.content.models import EmailQueue
    try:
        subject, body = render_template(template_key, context)
        return EmailQueue.objects.create(
            to_email=context['to_email'], to_name=context.get('to_name', ''), subject=subject[:500],
            template=template_key, booking_ref=booking_ref or context.get('booking_ref', ''), body=body,
        )
    except Exception:  # noqa: BLE001 — deliberately swallow, see docstring
        logger.exception('Failed to queue %s email', template_key)
        return None


def send_queued(item):
    item.attempts += 1
    try:
        msg = EmailMultiAlternatives(item.subject, strip_tags(item.body), getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                                     [f'{item.to_name} <{item.to_email}>' if item.to_name else item.to_email])
        msg.attach_alternative(item.body, 'text/html')
        msg.send()
        item.status, item.sent_at, item.last_error = 'sent', timezone.now(), ''
    except Exception as exc:  # noqa: BLE001
        item.status = 'failed' if item.attempts >= 3 else 'pending'
        item.last_error = str(exc)[:2000]
    item.save(update_fields=['attempts', 'status', 'sent_at', 'last_error'])
    return item.status == 'sent'
