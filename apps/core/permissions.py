"""
Role-based access control, mirroring the legacy PHP app's AuthMiddleware
(requireAdmin/requireAgent/isAgentRole) and OwnershipScope. Two layers:
view-level decorators for the template-rendered dashboard/agent_portal
apps, and DRF permission classes for the API — both read the same
`request.user.role`.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

ROLE_OWNER = 'owner'
ROLE_ADMIN = 'admin'
ROLE_MANAGER = 'manager'
ROLE_AGENT = 'agent'

STAFF_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER)


def role_required(*roles):
    """View decorator for dashboard/agent_portal pages — e.g. @role_required(ROLE_OWNER, ROLE_ADMIN)."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url='accounts:login')
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied('Your account role does not have access to this page.')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


staff_required = role_required(*STAFF_ROLES)
agent_required = role_required(ROLE_AGENT)
any_role_required = role_required(*STAFF_ROLES, ROLE_AGENT)


class IsStaffRole(BasePermission):
    """DRF permission — owner/admin/manager only, mirrors staff_required above."""
    message = 'This action requires a staff account.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role in STAFF_ROLES)


class IsAgentRole(BasePermission):
    message = 'This action requires an agent account.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == ROLE_AGENT)


class IsOwnerOrStaff(BasePermission):
    """
    Object-level permission for agent-scoped resources (leads,
    commissions): staff see everything, an agent only sees/edits rows
    where `obj.agent_id == request.user.id` — mirrors the legacy app's
    OwnershipScope so an agent can never read or modify another agent's
    pipeline through the API, even by guessing an ID.
    """
    def has_object_permission(self, request, view, obj):
        if request.user.role in STAFF_ROLES:
            return True
        agent_id = getattr(obj, 'agent_id', None)
        return agent_id == request.user.id
