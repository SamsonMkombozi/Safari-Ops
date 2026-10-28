import uuid

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base — every domain model gets created_at/updated_at for free, consistent audit trails across the whole system."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Abstract base for records that should never truly disappear (bookings, quotations, customers) — mirrors the legacy app's archive-before-delete convention, enforced structurally instead of by habit."""
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        from django.utils import timezone
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_active', 'deleted_at'])


class ActivityLog(TimeStampedModel):
    """Every meaningful write made through the dashboard/agent portal/API — who did what, to which record, from where. Mirrors the legacy admin's activity_log table."""
    ACTION_CHOICES = [
        ('create', 'Create'), ('update', 'Update'), ('delete', 'Delete'),
        ('login', 'Login'), ('login_failed', 'Login Failed'), ('logout', 'Logout'),
        ('view', 'View'), ('export', 'Export'), ('status_change', 'Status Change'),
    ]
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='activity_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=500, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['object_type', 'object_id']),
        ]

    def __str__(self):
        return f'{self.actor} {self.action} {self.object_type}:{self.object_id}'


def _generate_api_key():
    # Plain uuid4().hex is 32 chars — doubled to use the field's full 64
    # chars worth of entropy, matching the strength of a real bearer token.
    return uuid.uuid4().hex + uuid.uuid4().hex


class APIKey(TimeStampedModel):
    """Server-to-server credential for external integrations (a WordPress/Joomla plugin, another backend) — distinct from a user's JWT, scoped to specific permissions and revocable without touching any human account."""
    name = models.CharField(max_length=150, help_text='Which integration this key belongs to, e.g. "Main WordPress site".')
    key = models.CharField(max_length=64, unique=True, default=_generate_api_key)
    is_active = models.BooleanField(default=True)
    allowed_origin = models.CharField(max_length=255, blank=True, help_text='Optional — restrict this key to one origin domain.')
    can_read = models.BooleanField(default=True)
    can_write = models.BooleanField(default=False)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.name
