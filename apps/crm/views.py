from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.middleware import log_activity
from apps.core.permissions import IsOwnerOrStaff, STAFF_ROLES
from apps.crm import pipeline

from .models import AgentTarget, Commission, Customer, Lead
from .serializers import AgentTargetSerializer, CommissionSerializer, CustomerSerializer, LeadSerializer


class OwnershipScopedViewSet(viewsets.ModelViewSet):
    """Base for anything keyed by `agent` — staff see every row, an agent only ever sees their own, at the queryset level (not just object-permission, so list/filter can't leak another agent's rows either)."""
    permission_classes = [IsOwnerOrStaff]
    owner_field = 'agent'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role in STAFF_ROLES:
            return qs
        return qs.filter(**{self.owner_field: user})


class LeadViewSet(OwnershipScopedViewSet):
    queryset = Lead.objects.select_related('agent', 'customer').all()
    serializer_class = LeadSerializer

    def perform_create(self, serializer):
        lead = serializer.save()
        log_activity(self.request, self.request.user, 'create', 'Lead', lead.id, f'Created lead {lead.full_name}')

    @action(detail=True, methods=['post'])
    def set_stage(self, request, pk=None):
        """Staff-only stage change through the shared PipelineSync port — moving to 'booked' creates the agent's commission there, exactly once."""
        if request.user.role not in STAFF_ROLES:
            return Response({'success': False, 'message': 'Only staff can change a lead\'s pipeline stage.'}, status=403)
        lead = self.get_object()
        ok, msg, _ = pipeline.set_lead_stage_manual(lead, request.data.get('pipeline_stage'))
        if not ok:
            return Response({'success': False, 'message': msg}, status=400)
        log_activity(request, request.user, 'status_change', 'Lead', lead.id, f'Stage -> {lead.pipeline_stage}')
        return Response(LeadSerializer(lead).data)


class CommissionViewSet(OwnershipScopedViewSet):
    queryset = Commission.objects.select_related('agent', 'lead').all()
    serializer_class = CommissionSerializer
    http_method_names = ['get', 'head', 'options', 'post']  # agents never edit their own commission rows directly

    def get_permissions(self):
        # Creating, approving or paying a commission is staff-only — an agent
        # minting or approving their own commission row is self-dealing.
        if self.action in ('create', 'approve', 'mark_paid'):
            from apps.core.permissions import IsStaffRole
            return [IsStaffRole()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        commission = self.get_object()
        pipeline.set_commission_status(commission, 'approved', request.user)
        log_activity(request, request.user, 'status_change', 'Commission', commission.id, 'Approved')
        return Response(CommissionSerializer(commission).data)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        commission = self.get_object()
        pipeline.set_commission_status(commission, 'paid', request.user)
        log_activity(request, request.user, 'status_change', 'Commission', commission.id, 'Marked paid')
        return Response(CommissionSerializer(commission).data)


class CustomerViewSet(viewsets.ModelViewSet):
    from apps.core.permissions import IsStaffRole
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsStaffRole]


class AgentTargetViewSet(OwnershipScopedViewSet):
    queryset = AgentTarget.objects.select_related('agent').all()
    serializer_class = AgentTargetSerializer
