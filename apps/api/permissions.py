from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.core.models import APIKey
from apps.core.permissions import STAFF_ROLES


class HasAPIKey(BasePermission):
    """For endpoints meant for external CMS/site integration — read access needs any active key, write access needs can_write=True on that specific key."""

    def has_permission(self, request, view):
        if not isinstance(request.auth, APIKey):
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return request.auth.can_read
        return request.auth.can_write


class IsAuthenticatedOrHasAPIKey(BasePermission):
    """Default for public-catalog endpoints (packages, itineraries) — a logged-in staff/agent user OR a valid API key may read; only a logged-in user may write."""

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        return HasAPIKey().has_permission(request, view)


class IsStaffForWrite(BasePermission):
    """Read for anyone already authenticated (any role or API key); write restricted to staff roles — booking/quotation/CRM data should never be writable by an external integration, only read where explicitly exposed."""

    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return IsAuthenticatedOrHasAPIKey().has_permission(request, view)
        return bool(request.user and request.user.is_authenticated and request.user.role in STAFF_ROLES)
