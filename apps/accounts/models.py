from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.permissions import ROLE_ADMIN, ROLE_AGENT, ROLE_MANAGER, ROLE_OWNER


class User(AbstractUser):
    """
    Replaces the legacy app's single admin_users table (which held both
    admin/manager and agent accounts, distinguished by a role column) —
    same shape, now as Django's actual auth user so every built-in auth
    feature (password hashing, session auth, permissions, the Django
    admin) works on it for free instead of being hand-rolled.
    """
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_MANAGER, 'Manager'),
        (ROLE_AGENT, 'Agent'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_AGENT)
    phone = models.CharField(max_length=30, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Commission/target/permission columns carried over from the legacy
    # admin_users table — commission_rate is the agent's own default rate
    # (PipelineSync falls back to the site-wide default_commission_rate
    # setting when it's empty); the two can_* flags are the per-user
    # overrides admin/users.php exposed for non-agent staff.
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    target_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    can_change_status = models.BooleanField(default=True)
    can_delete_records = models.BooleanField(default=False)
    THEME_CHOICES = [('system', 'Match my device'), ('light', 'Light'), ('dark', 'Dark'), ('mono', 'Black & white')]
    theme_preference = models.CharField(max_length=10, choices=THEME_CHOICES, default='system')

    # Lockout bookkeeping — mirrors the legacy admin_login.php's
    # IP+account-keyed lockfile approach, but as real columns instead of
    # files on disk (cleaner under multiple app server processes, and
    # survives a redeploy).
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'accounts_user'

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.role})'

    @property
    def is_staff_role(self):
        return self.role in (ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER)

    @property
    def is_admin_role(self):
        """Owner/admin only — the legacy isAdminRole() gate for compensation, margin and settings pages."""
        return self.role in (ROLE_OWNER, ROLE_ADMIN)

    @property
    def may_change_status(self):
        return self.is_admin_role or (self.is_staff_role and self.can_change_status)

    @property
    def may_delete(self):
        return self.is_admin_role or (self.is_staff_role and self.can_delete_records)

    @property
    def is_agent_role(self):
        return self.role == ROLE_AGENT
