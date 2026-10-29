from rest_framework import mixins, viewsets
from rest_framework.throttling import ScopedRateThrottle

from apps.api.permissions import HasAPIKey, IsStaffForWrite
from apps.core.permissions import IsStaffRole

from .models import ContactMessage, CustomSafariRequest, EmailTemplate, TeamMember
from .serializers import (
    ContactMessageSerializer, CustomSafariRequestSerializer, EmailTemplateSerializer, TeamMemberSerializer,
)


class TeamMemberViewSet(viewsets.ModelViewSet):
    queryset = TeamMember.objects.filter(is_active=True)
    serializer_class = TeamMemberSerializer
    permission_classes = [IsStaffForWrite]


class MaintenanceAwareCreate:
    """When the maintenance_mode setting is on, public submissions politely decline (legacy api/book.php, api/custom_safari.php behaviour)."""

    def create(self, request, *args, **kwargs):
        from rest_framework.response import Response

        from apps.core.settings_store import get_setting
        if get_setting('maintenance_mode'):
            return Response({'success': False, 'message': 'We are performing scheduled maintenance — please try again shortly or contact us directly.'}, status=503)
        return super().create(request, *args, **kwargs)


class PublicSubmissionThrottle(ScopedRateThrottle):
    throttle_scope = 'tracking'  # reuse the same strict per-IP window as booking tracking — both are unauthenticated public POSTs


class ContactMessageViewSet(MaintenanceAwareCreate, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Create is for the external site (via API key) submitting the contact form; list/retrieve is staff-only (reading guest messages is not something an integration partner needs)."""
    queryset = ContactMessage.objects.all()
    serializer_class = ContactMessageSerializer
    throttle_classes = [PublicSubmissionThrottle]

    def get_permissions(self):
        if self.action == 'create':
            return [HasAPIKey()]
        return [IsStaffRole()]


class CustomSafariRequestViewSet(MaintenanceAwareCreate, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = CustomSafariRequest.objects.select_related('customer').all()
    serializer_class = CustomSafariRequestSerializer
    throttle_classes = [PublicSubmissionThrottle]

    def get_permissions(self):
        if self.action == 'create':
            return [HasAPIKey()]
        return [IsStaffRole()]


class EmailTemplateViewSet(viewsets.ModelViewSet):
    queryset = EmailTemplate.objects.all()
    serializer_class = EmailTemplateSerializer
    permission_classes = [IsStaffRole]
