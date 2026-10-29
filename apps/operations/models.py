from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from apps.core.models import TimeStampedModel


def validate_contract_size(f):
    from apps.core.settings_store import get_setting
    limit_mb = int(get_setting('supplier_contract_max_mb', 15))
    if f.size > limit_mb * 1024 * 1024:
        raise ValidationError(f'Contract must be {limit_mb} MB or smaller.')


class Supplier(TimeStampedModel):
    CATEGORY_CHOICES = [
        ('accommodation', 'Accommodation'), ('park_operator', 'Park Operator'),
        ('activity_operator', 'Activity Operator'), ('transport', 'Transport'), ('other', 'Other'),
    ]
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    contact_person = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(max_length=200, blank=True)
    payment_terms = models.CharField(max_length=255, blank=True)
    # Under media/private/ — the web server must NOT serve that prefix (see
    # deploy/nginx.conf); contracts are only reachable through the
    # staff-only dashboard:supplier_contract view.
    contract = models.FileField(upload_to='private/contracts/', null=True, blank=True,
                                validators=[FileExtensionValidator(['pdf']), validate_contract_size],
                                help_text='PDF only.')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StaffMember(TimeStampedModel):
    """Field staff (guides/drivers) — not system users, just people we assign to trips. The legacy `staff` table."""
    ROLE_CHOICES = [('guide_driver', 'Guide / Driver'), ('guide', 'Guide'), ('driver', 'Driver')]
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='guide_driver')
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(max_length=200, blank=True)
    languages = models.CharField(max_length=255, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Guide / driver'

    def __str__(self):
        return self.full_name


class BookingAssignment(TimeStampedModel):
    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='assignments')
    staff = models.ForeignKey(StaffMember, null=True, blank=True, on_delete=models.SET_NULL, related_name='assignments')
    vehicle = models.ForeignKey('packages.Vehicle', null=True, blank=True, on_delete=models.SET_NULL, related_name='assignments')
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'{self.booking} — {self.staff or "unassigned"}'


class Incident(TimeStampedModel):
    TYPE_CHOICES = [
        ('vehicle_breakdown', 'Vehicle Breakdown'), ('medical', 'Medical'), ('weather_delay', 'Weather Delay'),
        ('accommodation_issue', 'Accommodation Issue'), ('guide_driver_issue', 'Guide/Driver Issue'),
        ('safety', 'Safety'), ('other', 'Other'),
    ]
    SEVERITY_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')]
    STATUS_CHOICES = [('open', 'Open'), ('resolved', 'Resolved')]

    booking_ref = models.CharField(max_length=20, blank=True)
    incident_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='other')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    description = models.TextField()
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='incidents_reported')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open', db_index=True)
    resolution_notes = models.TextField(blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_incident_type_display()} — {self.booking_ref or "no booking"}'
