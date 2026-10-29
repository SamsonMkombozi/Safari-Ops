from django.db import models

from apps.core.models import TimeStampedModel
from apps.crm.models import Customer


class TeamMember(models.Model):
    MEMBER_TYPE_CHOICES = [('team', 'Team'), ('agent', 'Partner / Agent')]
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=150, blank=True)
    member_type = models.CharField(max_length=20, choices=MEMBER_TYPE_CHOICES, default='team')
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to='team/', null=True, blank=True)
    email = models.EmailField(max_length=200, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    linkedin_url = models.URLField(blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.name


class ContactMessage(TimeStampedModel):
    full_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=200)
    phone = models.CharField(max_length=50, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    first_response_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} — {self.subject or "(no subject)"}'


class CustomSafariRequest(TimeStampedModel):
    STATUS_CHOICES = [
        ('new', 'New'), ('in_review', 'In Review'), ('quoted', 'Quoted'),
        ('converted', 'Converted'), ('closed', 'Closed'),
    ]
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name='custom_requests')
    full_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(max_length=200, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=100, blank=True)
    travelers = models.CharField(max_length=50, blank=True)
    adults = models.PositiveSmallIntegerField(null=True, blank=True)
    children = models.PositiveSmallIntegerField(null=True, blank=True)
    infants = models.PositiveSmallIntegerField(null=True, blank=True)
    rooms = models.PositiveSmallIntegerField(null=True, blank=True)
    airport_pickup = models.BooleanField(default=False)
    submitted_by_agent = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='custom_requests_submitted')
    first_response_at = models.DateTimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    duration_days = models.PositiveSmallIntegerField(null=True, blank=True)
    destinations = models.TextField(blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    flexible_dates = models.CharField(max_length=10, blank=True)
    guide_language = models.CharField(max_length=100, blank=True)
    mainland_accommodation = models.CharField(max_length=100, blank=True)
    beach_accommodation = models.CharField(max_length=100, blank=True)
    meal_plan = models.CharField(max_length=100, blank=True)
    room_layout = models.CharField(max_length=100, blank=True)
    accommodation_standard = models.CharField(max_length=100, blank=True)
    total_budget = models.CharField(max_length=100, blank=True)
    experiences = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} — {self.status}'


class EmailTemplate(models.Model):
    template_key = models.SlugField(max_length=100, unique=True)
    subject = models.CharField(max_length=300)
    body_html = models.TextField()
    is_custom = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.template_key


class Review(models.Model):
    booking_ref = models.CharField(max_length=20, blank=True)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviews')
    guest_name = models.CharField(max_length=150)
    guest_country = models.CharField(max_length=100, blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    nps_score = models.PositiveSmallIntegerField(null=True, blank=True, help_text='0–10 likelihood to recommend.')
    comment = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.guest_name} — {self.rating}★'


class EmailQueue(models.Model):
    """Outbound mail is queued, never sent inline from a request — the `process_email_queue` command drains it, exactly like the legacy cron/process_email_queue.php."""
    STATUS_CHOICES = [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')]
    to_email = models.EmailField(max_length=255)
    to_name = models.CharField(max_length=150, blank=True)
    subject = models.CharField(max_length=500)
    template = models.CharField(max_length=60, blank=True)
    booking_ref = models.CharField(max_length=50, blank=True)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Email queue'

    def __str__(self):
        return f'{self.to_email} — {self.subject}'
