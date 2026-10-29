"""
Booking/quotation write paths ported from the legacy admin/bookings.php,
api/record_payment.php, api/convert_quotation.php and the agent portal's
add_direct_booking action. Views and the API call these instead of
writing payment/status columns themselves, so the side effects (payment
ledger, commission clawback, pipeline advance, client emails) happen
identically no matter which screen triggered them.
"""
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.content import mailer
from apps.core.settings_store import get_setting
from apps.crm import pipeline

from . import pricing
from .models import Booking, BookingReminder, Payment, Quotation

REF_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def _token(n):
    return ''.join(secrets.choice(REF_ALPHABET) for _ in range(n))


def generate_booking_ref():
    while True:
        ref = f'SZV{timezone.now():%y}{_token(5)}'
        if not Booking.objects.filter(booking_ref=ref).exists():
            return ref


def generate_quote_ref():
    while True:
        ref = f'SZV-Q{_token(8)}'
        if not Quotation.objects.filter(quote_ref=ref).exists():
            return ref


def D(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def _status_for(booking):
    if booking.payment_status == 'cancelled':
        return 'cancelled'
    if booking.total_amount and booking.amount_paid >= booking.total_amount:
        return 'fully_paid'
    if booking.amount_paid > 0:
        return 'deposit_paid'
    return 'pending'


def record_payment(booking, amount, method='bank_transfer', reference='', received_at=None, notes='', user=None, kind=None):
    """Append to the payment ledger and recompute amount_paid/payment_status under a row lock (the legacy API-4 double-credit fix)."""
    amount = D(amount)
    if amount == 0:
        raise ValueError('Payment amount must be non-zero.')
    with transaction.atomic():
        locked = Booking.objects.select_for_update().get(pk=booking.pk)
        if reference and method == 'paypal' and locked.payments.filter(reference=reference).exists():
            return locked, None  # idempotent PayPal replay
        prev_status = locked.payment_status
        if kind is None:
            if amount < 0:
                kind = 'refund'
            elif locked.total_amount and locked.amount_paid + amount >= locked.total_amount:
                kind = 'full' if locked.amount_paid == 0 else 'balance'
            else:
                kind = 'deposit' if locked.amount_paid == 0 else 'balance'
        payment = Payment.objects.create(
            booking=locked, amount=amount, kind=kind, method=method, reference=reference,
            received_at=received_at or timezone.localdate(), notes=notes, recorded_by=user,
        )
        locked.amount_paid = D(locked.amount_paid + amount)
        locked.payment_method = method
        if method == 'paypal' and reference:
            locked.paypal_order_id = reference
        locked.payment_status = _status_for(locked)
        locked.save(update_fields=['amount_paid', 'payment_method', 'paypal_order_id', 'payment_status', 'updated_at'])
    _after_status_change(locked, prev_status, amount)
    return locked, payment


def set_payment_status(booking, status, amount_paid=None, user=None):
    """
    The admin status dropdown. 'deposit_paid' requires the amount actually
    received; 'fully_paid' settles the remaining balance; 'cancelled'
    claws back unpaid commission and marks the lead lost.
    """
    if status not in dict(Booking.PAYMENT_STATUS_CHOICES):
        raise ValueError('Invalid status.')
    if status == 'deposit_paid':
        amount_paid = D(amount_paid)
        if amount_paid <= 0:
            raise ValueError('Enter the amount actually received.')
        outstanding = amount_paid - booking.amount_paid
        if outstanding > 0:
            return record_payment(booking, outstanding, user=user, kind='deposit', notes='Recorded via status change')[0]
    if status == 'fully_paid':
        outstanding = (booking.total_amount or 0) - booking.amount_paid
        if outstanding > 0:
            return record_payment(booking, outstanding, user=user, notes='Recorded via status change')[0]
    prev = booking.payment_status
    booking.payment_status = status
    booking.save(update_fields=['payment_status', 'updated_at'])
    _after_status_change(booking, prev)
    return booking


def _lead_for(booking):
    from apps.crm.models import Lead
    if booking.quotation_id and booking.quotation and booking.quotation.lead_id:
        return booking.quotation.lead
    return Lead.objects.filter(booking_ref=booking.booking_ref).first()


def _after_status_change(booking, prev_status, amount=None):
    status = booking.payment_status
    if status == prev_status and amount is None:
        return
    if status == 'cancelled' and prev_status != 'cancelled':
        lead = _lead_for(booking)
        if lead:
            lead.commissions.exclude(status__in=['paid', 'cancelled']).update(status='cancelled', updated_at=timezone.now())
            if lead.pipeline_stage not in ('travelled', 'completed', 'lost'):
                lead.pipeline_stage = 'lost'
                lead.save(update_fields=['pipeline_stage', 'updated_at'])
        booking.reminders.filter(status='pending').update(status='cancelled')
        return
    if not get_setting('auto_send_payment_emails'):
        return
    ctx = {'to_email': booking.email, 'to_name': booking.full_name, 'client_name': booking.full_name,
           'booking_ref': booking.booking_ref, 'total_amount': booking.total_amount, 'amount_paid': booking.amount_paid,
           'balance_due': booking.balance_due, 'amount': amount}
    if status == 'fully_paid' and prev_status != 'fully_paid':
        mailer.queue('invoice_paid', ctx)
    elif status == 'deposit_paid' and amount and amount > 0:
        mailer.queue('deposit_receipt', ctx)


def schedule_reminders(booking):
    """Port of BookingReminderScheduler — balance-due and pre-departure reminders relative to the travel date."""
    if not booking.travel_date:
        return
    balance_days = int(get_setting('balance_days'))
    tz = timezone.get_current_timezone()
    at_nine = lambda d: timezone.make_aware(timezone.datetime(d.year, d.month, d.day, 9, 0), tz)  # noqa: E731
    plan = [
        ('balance_due', booking.travel_date - timedelta(days=balance_days), f'Balance due for {booking.booking_ref}',
         f'<p>Dear {booking.full_name},</p><p>A friendly reminder that the balance for booking {booking.booking_ref} is due.</p>'),
        ('departure', booking.travel_date - timedelta(days=7), f'Your safari starts soon — {booking.booking_ref}',
         f'<p>Dear {booking.full_name},</p><p>Your safari begins on {booking.travel_date:%d %b %Y}. We can\'t wait to welcome you!</p>'),
        ('post_trip', booking.travel_date + timedelta(days=10), 'How was your safari?',
         f'<p>Dear {booking.full_name},</p><p>We\'d love to hear about your trip — please leave us a review.</p>'),
    ]
    today = timezone.localdate()
    for kind, send_on, subject, body in plan:
        if send_on < today:
            continue
        BookingReminder.objects.get_or_create(
            booking=booking, type=kind,
            defaults={'booking_ref': booking.booking_ref, 'send_at': at_nine(send_on), 'subject': subject, 'body': body},
        )


def _customer(email, name, phone='', country=''):
    from apps.crm.models import Customer
    customer, created = Customer.objects.get_or_create(
        email=email.strip().lower(), defaults={'full_name': name, 'phone': phone, 'country': country})
    if not created and (phone and not customer.phone or country and not customer.country):
        customer.phone = customer.phone or phone
        customer.country = customer.country or country
        customer.save(update_fields=['phone', 'country', 'updated_at'])
    return customer


def convert_quotation(quote, user=None, travel_date=None):
    """Port of api/convert_quotation.php: quote → booking, advancing the linked lead/custom request and creating the agent's commission."""
    if quote.status == 'converted' and quote.booking_ref:
        return Booking.objects.get(booking_ref=quote.booking_ref), None
    travel_date = travel_date or quote.start_date
    if not travel_date:
        raise ValueError('The quotation needs a start date before it can become a booking.')
    with transaction.atomic():
        customer = quote.customer or _customer(quote.client_email, quote.client_name, quote.client_phone, quote.client_country)
        booking = Booking(
            booking_ref=generate_booking_ref(), quotation=quote, customer=customer, package=quote.package,
            itinerary=quote.itinerary, full_name=quote.client_name, email=quote.client_email,
            phone=quote.client_phone or '-', country=quote.client_country,
            travelers=quote.adults + quote.children, adults=quote.adults, children=quote.children,
            rooms=quote.rooms, package_name=quote.package_name, accommodation_level=quote.accommodation_level,
            travel_date=travel_date, special_request=quote.notes, total_amount=quote.grand_total,
            deposit_amount=quote.deposit_amount, supplier_cost=pricing.supplier_cost(quote.line_items),
            payment_method='quotation', created_by=user,
        )
        tracking_password = booking.set_tracking_password()
        booking.save()
        quote.status, quote.booking_ref, quote.customer = 'converted', booking.booking_ref, customer
        quote.accepted_at = quote.accepted_at or timezone.now()
        quote.save(update_fields=['status', 'booking_ref', 'customer', 'accepted_at', 'updated_at'])
        if quote.lead_id:
            lead = quote.lead
            lead.booking_value, lead.booking_ref = quote.grand_total, booking.booking_ref
            lead.save(update_fields=['booking_value', 'booking_ref', 'updated_at'])
        if quote.custom_request_id:
            pipeline.advance_custom_request(quote.custom_request, 'converted')
    if quote.lead_id:
        pipeline.advance_lead(quote.lead, 'booked')
    schedule_reminders(booking)
    _send_confirmation(booking, tracking_password)
    return booking, tracking_password


def _send_confirmation(booking, tracking_password):
    queued = mailer.queue('booking_confirmation', {
        'to_email': booking.email, 'to_name': booking.full_name, 'client_name': booking.full_name,
        'booking_ref': booking.booking_ref, 'tracking_password': tracking_password, 'package_name': booking.package_name,
        'travel_date': booking.travel_date, 'travelers': booking.travelers, 'total_amount': booking.total_amount,
        'deposit_amount': booking.deposit_amount,
    })
    if queued:
        Booking.objects.filter(pk=booking.pk).update(confirmation_email_sent=True)


def build_quotation(*, client, package=None, itinerary=None, adults=2, children=0, rooms=1, start_date=None,
                    accommodation_level='midrange', markup_pct=0, discount_pct=0, extra_items=None, user=None,
                    lead=None, custom_request=None, notes='', status='draft'):
    """Create a priced Quotation from a package/itinerary + party — the server-side half of admin/quotation_new.php."""
    itinerary = itinerary or (package.itinerary if package else None)
    if itinerary and itinerary.days:
        built = pricing.build(itinerary.days, adults, children, True, client.get('country'), pricing.service_fee_rates_for(package))
        line_items = built['line_items']
        destinations = list(dict.fromkeys(d['location'] for d in built['day_titles'] if d.get('location')))
    elif package:
        built, _ = pricing.price_package(package, adults, children)
        line_items, destinations = built['line_items'], []
    else:
        built, line_items, destinations = {'notes_suggestion': ''}, [], []
    line_items = line_items + list(extra_items or [])
    # pricing works in floats; money columns (and everything that does
    # arithmetic on this instance afterwards) must be Decimal.
    t = {k: D(v) for k, v in pricing.totals(line_items, discount_pct, markup_pct).items()}
    pax = max(1, int(adults) + int(children))
    validity = int(get_setting('quotation_validity_days'))
    customer = _customer(client['email'], client['name'], client.get('phone', ''), client.get('country', ''))
    quote = Quotation.objects.create(
        quote_ref=generate_quote_ref(), customer=customer, package=package, itinerary=itinerary,
        package_name=package.name if package else (itinerary.name if itinerary else 'Custom Safari'),
        client_name=client['name'], client_email=client['email'], client_phone=client.get('phone', ''),
        client_country=client.get('country', ''), adults=adults, children=children, rooms=rooms,
        duration_days=(itinerary.duration_days if itinerary else (package.duration_days if package else 5)),
        start_date=start_date, destinations=destinations, accommodation_level=accommodation_level,
        season=pricing.detect_season(start_date) if start_date else 'peak',
        line_items=line_items, subtotal=t['subtotal'], markup_pct=D(markup_pct), markup_amount=t['markup'],
        discount_pct=D(discount_pct), discount_amount=t['discount'], vat=t['vat'], grand_total=t['grand_total'],
        per_person=D(t['grand_total'] / pax), deposit_amount=t['deposit'], balance_due=t['balance'],
        valid_until=timezone.localdate() + timedelta(days=validity), notes=notes or built.get('notes_suggestion', ''),
        status=status, created_by=user, lead=lead, custom_request=custom_request,
        park_fees_total=sum(D(li['amount']) for li in line_items if li['category'] == 'park_fee'),
        vehicle_total=sum(D(li['amount']) for li in line_items if li['category'] == 'transport'),
        accommodation_total=sum(D(li['amount']) for li in line_items if li['category'] == 'accommodation'),
        activities_total=sum(D(li['amount']) for li in line_items if li['category'] == 'activity'),
    )
    if lead:
        lead.booking_value = quote.grand_total
        lead.save(update_fields=['booking_value', 'updated_at'])
        pipeline.advance_lead(lead, 'quoted')
    if custom_request:
        pipeline.advance_custom_request(custom_request, 'quoted')
    return quote


def send_quotation(quote, request=None):
    view_path = f'/q/{quote.public_token}/'
    mailer.queue('quotation_sent', {
        'to_email': quote.client_email, 'to_name': quote.client_name, 'client_name': quote.client_name,
        'quote_ref': quote.quote_ref, 'package_name': quote.package_name, 'grand_total': quote.grand_total,
        'per_person': quote.per_person, 'valid_until': quote.valid_until,
        'view_url': request.build_absolute_uri(view_path) if request else f'{settings.SITE_URL}{view_path}',
    })
    if quote.status == 'draft':
        quote.status = 'sent'
    quote.sent_at = timezone.now()
    quote.save(update_fields=['status', 'sent_at', 'updated_at'])
    if quote.lead_id:
        pipeline.advance_lead(quote.lead, 'quoted')


def agent_direct_booking(agent, *, full_name, email, phone, country, package, travel_date, adults, children,
                         accommodation_level='midrange', notes=''):
    """
    Port of agent-portal add_direct_booking: a real booking + a 'converted'
    quotation stamped created_by=agent (ownership) + a lead carried straight
    to 'booked' through PipelineSync so the commission is created exactly
    as a manual stage change would.
    """
    from apps.crm.models import Lead
    if not get_setting('agent_direct_booking_enabled'):
        raise ValueError('Direct booking is currently disabled — please submit a custom request instead.')
    with transaction.atomic():
        lead = Lead.objects.create(
            full_name=full_name, email=email, phone=phone, country=country, package_name=package.name,
            party_size=adults + children, travel_date=travel_date, source='agent_direct_booking', notes=notes, agent=agent,
        )
        quote = build_quotation(
            client={'name': full_name, 'email': email, 'phone': phone, 'country': country}, package=package,
            adults=adults, children=children, start_date=travel_date, accommodation_level=accommodation_level,
            user=agent, lead=lead, notes=notes, status='accepted',
        )
        lead.customer = quote.customer
        lead.save(update_fields=['customer'])
        booking, password = convert_quotation(quote, user=agent, travel_date=travel_date)
    lead.refresh_from_db()
    return booking, password, lead
