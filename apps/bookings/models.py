import secrets
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models

from apps.core.models import TimeStampedModel
from apps.crm.models import Customer
from apps.packages.models import ACCOMMODATION_LEVELS, Itinerary, Package, Vehicle


def _generate_quote_token():
    return secrets.token_hex(24)  # 48 hex chars — matches the legacy public_token format


class Quotation(TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('sent', 'Sent'), ('viewed', 'Viewed'), ('negotiating', 'Negotiating'), ('accepted', 'Accepted'),
        ('declined', 'Declined'), ('expired', 'Expired'), ('converted', 'Converted'),
    ]
    SEASON_CHOICES = [('peak', 'Peak'), ('shoulder', 'Shoulder'), ('low', 'Low')]

    quote_ref = models.CharField(max_length=20, unique=True, db_index=True)
    public_token = models.CharField(max_length=48, unique=True, default=_generate_quote_token, editable=False,
                                     help_text='Unguessable token for the client-facing view link — the numeric id is never exposed.')
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name='quotations')
    package = models.ForeignKey(Package, null=True, blank=True, on_delete=models.SET_NULL, related_name='quotations')
    package_name = models.CharField(max_length=150, blank=True)
    vehicle = models.ForeignKey(Vehicle, null=True, blank=True, on_delete=models.SET_NULL)
    itinerary = models.ForeignKey(Itinerary, null=True, blank=True, on_delete=models.SET_NULL, related_name='quotations')

    park_fees_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vehicle_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    activities_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    accommodation_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    flight_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    markup_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    markup_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    version = models.PositiveSmallIntegerField(default=1)

    client_name = models.CharField(max_length=150)
    client_email = models.EmailField(max_length=200)
    client_phone = models.CharField(max_length=50, blank=True)
    client_country = models.CharField(max_length=100, blank=True)
    expedition_type = models.CharField(max_length=50, default='safari')

    adults = models.PositiveSmallIntegerField(default=2)
    children = models.PositiveSmallIntegerField(default=0)
    infants = models.PositiveSmallIntegerField(default=0)
    rooms = models.PositiveSmallIntegerField(default=1)
    duration_days = models.PositiveSmallIntegerField(default=5)
    start_date = models.DateField(null=True, blank=True)
    destinations = models.JSONField(default=list, blank=True)
    accommodation_level = models.CharField(max_length=50, choices=ACCOMMODATION_LEVELS, default='midrange')
    meal_plan = models.CharField(max_length=10, default='fb')
    guide_language = models.CharField(max_length=50, default='english')
    activities = models.JSONField(default=list, blank=True)
    internal_flight = models.BooleanField(default=False)
    season = models.CharField(max_length=20, choices=SEASON_CHOICES, default='peak')
    line_items = models.JSONField(default=list, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    per_person = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=5, default='USD')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    valid_until = models.DateField(null=True, blank=True)
    booking_ref = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)

    view_count = models.PositiveIntegerField(default=0)
    first_viewed_at = models.DateTimeField(null=True, blank=True)
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='quotations_created')
    # The two pipeline back-links PipelineSync advances automatically when
    # a quote is built from / converted for one of them.
    lead = models.ForeignKey('crm.Lead', null=True, blank=True, on_delete=models.SET_NULL, related_name='quotations')
    custom_request = models.ForeignKey('content.CustomSafariRequest', null=True, blank=True, on_delete=models.SET_NULL, related_name='quotations')

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status']), models.Index(fields=['client_email'])]

    def __str__(self):
        return self.quote_ref

    def record_view(self):
        from django.utils import timezone
        self.view_count += 1
        now = timezone.now()
        if not self.first_viewed_at:
            self.first_viewed_at = now
        self.last_viewed_at = now
        if self.status == 'sent':
            self.status = 'viewed'
        self.save(update_fields=['view_count', 'first_viewed_at', 'last_viewed_at', 'status'])


def _default_tracking_password():
    return secrets.token_urlsafe(6)[:8]


class Booking(TimeStampedModel):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'), ('deposit_paid', 'Deposit Paid'),
        ('fully_paid', 'Fully Paid'), ('cancelled', 'Cancelled'),
    ]

    booking_ref = models.CharField(max_length=20, unique=True, db_index=True)
    quotation = models.ForeignKey(Quotation, null=True, blank=True, on_delete=models.SET_NULL, related_name='bookings')
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name='bookings')
    package = models.ForeignKey(Package, null=True, blank=True, on_delete=models.SET_NULL, related_name='bookings')
    itinerary = models.ForeignKey(Itinerary, null=True, blank=True, on_delete=models.SET_NULL, related_name='bookings')

    full_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=200)
    phone = models.CharField(max_length=50)
    country = models.CharField(max_length=100, blank=True)
    travelers = models.PositiveSmallIntegerField(default=1)
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    package_name = models.CharField(max_length=150, blank=True)
    accommodation_level = models.CharField(max_length=50, choices=ACCOMMODATION_LEVELS, default='midrange')
    travel_date = models.DateField()
    special_request = models.TextField(blank=True)
    rooms = models.PositiveSmallIntegerField(default=1)
    airport_pickup = models.BooleanField(default=False)
    trip_extension = models.CharField(max_length=255, blank=True)

    # Supplier-side cost snapshot (accommodation, transport, park fees,
    # activities, other — everything except our own service charge and
    # VAT), taken from the pricing build at booking time so profitability
    # reporting reflects what this trip actually cost, not today's rates.
    supplier_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=40, blank=True)
    paypal_order_id = models.CharField(max_length=100, blank=True)
    confirmation_email_sent = models.BooleanField(default=False)
    payment_notes = models.TextField(blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    # SEC-1-equivalent: a real one-time tracking password, same as the
    # legacy app's BookingTracking service — guests prove ownership with
    # ref+password, never with ref+travel_date alone (too low-entropy,
    # leaks too easily).
    tracking_password_hash = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='bookings_created')

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['booking_ref', 'travel_date']), models.Index(fields=['payment_status'])]

    def __str__(self):
        return self.booking_ref

    def set_tracking_password(self, raw_password: str | None = None) -> str:
        """Generates (if not given) and stores a hashed tracking password, returning the plaintext ONCE for display/email — never stored or logged in the clear."""
        raw_password = raw_password or _default_tracking_password()
        self.tracking_password_hash = make_password(raw_password)
        return raw_password

    def check_tracking_password(self, raw_password: str) -> bool:
        if not self.tracking_password_hash:
            return False
        return check_password(raw_password, self.tracking_password_hash)

    @property
    def balance_due(self):
        if self.total_amount is None:
            return None
        return self.total_amount - self.amount_paid

    @property
    def agent(self):
        """Ownership is derived the same way the legacy OwnershipScope did — through the linked quotation's creator when that creator is an agent."""
        creator = self.quotation.created_by if self.quotation_id and self.quotation else None
        return creator if creator and creator.role == 'agent' else None

    @property
    def net_revenue(self):
        from apps.core.settings_store import get_setting
        vat = Decimal(str(get_setting('vat_rate')))
        return (self.total_amount or Decimal('0')) / (1 + vat)

    @property
    def gross_profit(self):
        return self.net_revenue - self.supplier_cost


class Payment(TimeStampedModel):
    """
    One row per money-in event against a booking — a ledger the legacy app
    never had (it only kept a running bookings.amount_paid). Booking.amount_paid
    stays the denormalised running total; every write path goes through
    apps.bookings.services.record_payment so the two can never disagree.
    """
    METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'), ('paypal', 'PayPal'), ('wise', 'Wise'),
        ('card', 'Card'), ('cash', 'Cash'), ('mobile_money', 'Mobile Money'), ('other', 'Other'),
    ]
    KIND_CHOICES = [('deposit', 'Deposit'), ('balance', 'Balance'), ('full', 'Full Payment'), ('refund', 'Refund')]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='deposit')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='bank_transfer')
    reference = models.CharField(max_length=120, blank=True, help_text='Bank/PayPal/Wise transaction reference.')
    received_at = models.DateField()
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='payments_recorded')

    class Meta:
        ordering = ['-received_at', '-id']

    def __str__(self):
        return f'{self.booking.booking_ref} — {self.amount} ({self.kind})'


class BookingReminder(TimeStampedModel):
    TYPE_CHOICES = [
        ('deposit_due', 'Deposit Due'), ('balance_due', 'Balance Due'),
        ('departure', 'Departure'), ('post_trip', 'Post Trip'), ('win_back', 'Win-back'), ('custom', 'Custom'),
    ]
    STATUS_CHOICES = [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'), ('cancelled', 'Cancelled')]

    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.CASCADE, related_name='reminders')
    booking_ref = models.CharField(max_length=20)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='custom')
    send_at = models.DateTimeField(db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    subject = models.CharField(max_length=500, blank=True)
    body = models.TextField(blank=True)

    class Meta:
        ordering = ['send_at']

    def __str__(self):
        return f'{self.booking_ref} — {self.type} @ {self.send_at}'
