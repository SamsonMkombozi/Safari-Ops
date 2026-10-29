from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Customer(TimeStampedModel):
    """The dedup anchor across leads/quotations/bookings — one row per real person, keyed by lowercased email, same as the legacy app."""
    full_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=200, unique=True, help_text='Stored lowercase+trimmed — the dedup key.')
    phone = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=100, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-first_seen_at']

    def __str__(self):
        return f'{self.full_name} <{self.email}>'

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


PIPELINE_STAGES = [
    ('lead', 'Lead'), ('qualified', 'Qualified'), ('quoted', 'Quoted'),
    ('negotiation', 'Negotiation'), ('booked', 'Booked'), ('travelled', 'Travelled'),
    ('completed', 'Completed'), ('lost', 'Lost'),
]
COMMISSION_STATUS_CHOICES = [
    ('pending', 'Pending'), ('approved', 'Approved'), ('paid', 'Paid'), ('cancelled', 'Cancelled'),
]


class Lead(TimeStampedModel):
    full_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=200, db_index=True)
    phone = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=50, default='website')
    pipeline_stage = models.CharField(max_length=20, choices=PIPELINE_STAGES, default='lead', db_index=True)
    budget_range = models.CharField(max_length=100, blank=True)
    travel_date = models.DateField(null=True, blank=True)
    travel_month = models.CharField(max_length=30, blank=True)
    party_size = models.PositiveSmallIntegerField(null=True, blank=True)
    destinations = models.TextField(blank=True)
    package_name = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    score = models.IntegerField(default=0)

    booking_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    commission_status = models.CharField(max_length=20, choices=COMMISSION_STATUS_CHOICES, default='pending')
    booking_ref = models.CharField(max_length=50, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)

    # agent_id is the ownership column OwnershipScope/IsOwnerOrStaff
    # checks against; assigned_to is a separate "who's working this"
    # field (a staff member can assign a lead without changing whose
    # commission it is) — kept distinct on purpose, matching the legacy
    # schema's own two columns.
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='leads')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_leads')
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name='leads')

    last_contact = models.DateTimeField(null=True, blank=True)
    next_follow_up = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['pipeline_stage']), models.Index(fields=['agent', 'pipeline_stage'])]

    def __str__(self):
        return f'{self.full_name} ({self.pipeline_stage})'


class Commission(TimeStampedModel):
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='commissions')
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name='commissions')
    booking_ref = models.CharField(max_length=50, blank=True)
    client_name = models.CharField(max_length=150, blank=True)
    package_name = models.CharField(max_length=150, blank=True)
    booking_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=COMMISSION_STATUS_CHOICES, default='pending')
    travel_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='commissions_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        # One commission per lead — the legacy uniq_commissions_lead index.
        # MySQL unique indexes allow many NULLs, so manual (lead-less)
        # commissions are unaffected.
        constraints = [models.UniqueConstraint(fields=['lead'], name='uniq_commission_lead')]

    def __str__(self):
        return f'{self.agent} — {self.booking_ref or self.client_name}'


class AgentTarget(models.Model):
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='targets')
    month = models.DateField(help_text='First day of the target month.')
    target_leads = models.PositiveIntegerField(default=0)
    target_bookings = models.PositiveIntegerField(default=0)
    target_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    actual_leads = models.PositiveIntegerField(default=0)
    actual_bookings = models.PositiveIntegerField(default=0)
    actual_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = [('agent', 'month')]
        ordering = ['-month']

    def __str__(self):
        return f'{self.agent} — {self.month:%B %Y}'
