from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.middleware import log_activity
from apps.core.permissions import IsOwnerOrStaff, STAFF_ROLES

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
        """Mirrors PipelineSync::setLeadStageManual() — moving a lead to 'booked' is the one transition with a side effect (commission creation), handled explicitly here rather than in a generic PATCH."""
        lead = self.get_object()
        new_stage = request.data.get('pipeline_stage')
        valid_stages = dict(Lead._meta.get_field('pipeline_stage').choices)
        if new_stage not in valid_stages:
            return Response({'success': False, 'message': 'Invalid pipeline stage.'}, status=400)

        was_booked = lead.pipeline_stage == 'booked'
        lead.pipeline_stage = new_stage
        if new_stage == 'booked' and not was_booked:
            lead.converted_at = timezone.now()
        lead.save(update_fields=['pipeline_stage', 'converted_at', 'updated_at'])

        if new_stage == 'booked' and not was_booked and lead.booking_value:
            rate = lead.commission_rate or 10
            Commission.objects.create(
                agent=lead.agent, lead=lead, booking_ref=lead.booking_ref,
                client_name=lead.full_name, package_name=lead.package_name,
                booking_value=lead.booking_value, commission_rate=rate,
                commission_amount=(lead.booking_value * rate / 100), travel_date=lead.travel_date,
            )
        log_activity(request, request.user, 'status_change', 'Lead', lead.id, f'Stage -> {new_stage}')
        return Response(LeadSerializer(lead).data)


class CommissionViewSet(OwnershipScopedViewSet):
    queryset = Commission.objects.select_related('agent', 'lead').all()
    serializer_class = CommissionSerializer
    http_method_names = ['get', 'head', 'options', 'post']  # agents never edit their own commission rows directly

    def get_permissions(self):
        if self.action in ('approve', 'mark_paid'):
            from apps.core.permissions import IsStaffRole
            return [IsStaffRole()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        commission = self.get_object()
        commission.status = 'approved'
        commission.approved_by = request.user
        commission.approved_at = timezone.now()
        commission.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        log_activity(request, request.user, 'status_change', 'Commission', commission.id, 'Approved')
        return Response(CommissionSerializer(commission).data)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        commission = self.get_object()
        commission.status = 'paid'
        commission.paid_at = timezone.now()
        commission.save(update_fields=['status', 'paid_at', 'updated_at'])
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
