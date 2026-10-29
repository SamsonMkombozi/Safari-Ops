"""
The client-facing quotation page — what the "View your quotation" link in
the quote email opens. Access is by the unguessable public_token only (the
numeric id is never accepted), same rule as the JSON QuotationPublicView.
"""
import re

from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.content import mailer
from apps.core.settings_store import get_setting
from apps.crm import pipeline

from .models import Quotation

TOKEN_RE = re.compile(r'^[a-f0-9]{48}$')
ACCEPTABLE = ('sent', 'viewed', 'negotiating')


def _quote(token):
    if not TOKEN_RE.match(token):
        raise Http404
    quote = Quotation.objects.filter(public_token=token).first()
    if not quote:
        raise Http404
    return quote


def quote_page(request, token):
    quote = _quote(token)
    if quote.status in ('sent', 'viewed', 'draft', 'negotiating', 'accepted'):
        quote.record_view()
    expired = bool(quote.valid_until and quote.valid_until < timezone.localdate()) or quote.status == 'expired'
    return render(request, 'public/quote.html', {
        'quote': quote, 'expired': expired, 'can_accept': quote.status in ACCEPTABLE and not expired,
        'accepted': request.GET.get('accepted') == '1',
        'bank': {k: get_setting(k) for k in ('bank_name', 'bank_account_name', 'bank_account_no', 'bank_swift', 'wise_email')},
        'contact_email': get_setting('site_email'), 'whatsapp': get_setting('whatsapp_number'),
    })


@require_POST
def quote_accept(request, token):
    quote = _quote(token)
    expired = bool(quote.valid_until and quote.valid_until < timezone.localdate())
    if quote.status in ACCEPTABLE and not expired:
        quote.status, quote.accepted_at = 'accepted', timezone.now()
        quote.save(update_fields=['status', 'accepted_at', 'updated_at'])
        if quote.lead_id:
            pipeline.advance_lead(quote.lead, 'negotiation')
        mailer.queue('reminder', {
            'to_email': get_setting('admin_email'), 'to_name': 'Office',
            'subject': f'Quotation accepted — {quote.quote_ref} ({quote.client_name})',
            'body': f'<p>{quote.client_name} accepted quotation <strong>{quote.quote_ref}</strong> '
                    f'(${quote.grand_total:,.2f}). Convert it to a booking from the dashboard.</p>',
        })
    return redirect(f'{request.path.rsplit("accept/", 1)[0]}?accepted=1')
