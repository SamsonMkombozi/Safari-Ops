"""
Port of the legacy App\\Services\\PipelineSync — the single place lead
stage transitions and commission creation happen.

 - advance_lead / advance_custom_request: automatic, system-triggered,
   advance-only (never regresses, never resurrects 'lost'/'closed').
 - set_lead_stage_manual: an explicit staff decision; any stage allowed.

Both route a genuine transition into 'booked' through _create_commission
so that logic exists exactly once.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.content import mailer
from apps.core.settings_store import get_setting

LEAD_ORDER = {'lead': 0, 'qualified': 1, 'quoted': 2, 'negotiation': 3, 'booked': 4, 'travelled': 5, 'completed': 6}
REQUEST_ORDER = {'new': 0, 'in_review': 1, 'quoted': 2, 'converted': 3, 'closed': 4}


def advance_lead(lead, stage):
    if not lead or stage not in LEAD_ORDER or lead.pipeline_stage == 'lost':
        return False
    if LEAD_ORDER.get(lead.pipeline_stage, -1) >= LEAD_ORDER[stage]:
        return False
    _write_stage(lead, stage)
    return True


def advance_custom_request(req, status):
    if not req or status not in REQUEST_ORDER or req.status == 'closed':
        return
    if REQUEST_ORDER.get(req.status, -1) >= REQUEST_ORDER[status]:
        return
    req.status = status
    req.save(update_fields=['status', 'updated_at'])


def set_lead_stage_manual(lead, stage):
    """Returns (ok, message, commission_or_None)."""
    if stage not in LEAD_ORDER and stage != 'lost':
        return False, 'Invalid stage.', None
    return True, None, _write_stage(lead, stage)


def _write_stage(lead, stage):
    was_booked = lead.pipeline_stage == 'booked'
    commission = None
    with transaction.atomic():
        lead.pipeline_stage = stage
        lead.save(update_fields=['pipeline_stage', 'updated_at'])
        if stage == 'booked' and not was_booked and lead.agent_id:
            commission = _create_commission(lead)
    if commission and lead.agent.email:
        mailer.queue('lead_converted', {
            'to_email': lead.agent.email, 'to_name': lead.agent.get_full_name(), 'agent_name': lead.agent.get_full_name(),
            'client_name': lead.full_name, 'package_name': lead.package_name or 'Tanzania Safari',
            'booking_value': commission.booking_value, 'commission_rate': commission.commission_rate,
            'commission_amount': commission.commission_amount,
        })
    return commission


def commission_rate_for(lead):
    if lead.commission_rate and lead.commission_rate > 0:
        return lead.commission_rate
    if lead.agent and lead.agent.commission_rate and lead.agent.commission_rate > 0:
        return lead.agent.commission_rate
    return Decimal(str(get_setting('default_commission_rate')))


def _create_commission(lead):
    from apps.crm.models import Commission
    rate = commission_rate_for(lead)
    value = lead.booking_value or Decimal('0')
    amount = (value * rate / 100).quantize(Decimal('0.01'))
    # Upsert on the unique lead — a re-conversion refreshes figures, never duplicates the row.
    commission, _ = Commission.objects.update_or_create(
        lead=lead,
        defaults={'agent': lead.agent, 'client_name': lead.full_name, 'package_name': lead.package_name,
                  'booking_ref': lead.booking_ref, 'booking_value': value, 'commission_rate': rate,
                  'commission_amount': amount, 'travel_date': lead.travel_date},
    )
    if commission.status == 'cancelled':
        commission.status = 'pending'
        commission.save(update_fields=['status'])
    lead.commission_rate, lead.commission_amount, lead.converted_at = rate, amount, timezone.now()
    lead.save(update_fields=['commission_rate', 'commission_amount', 'converted_at'])
    return commission


def set_commission_status(commission, status, user):
    """Status changes from admin/commissions.php, including the agent notification emails on approve/pay."""
    commission.status = status
    fields = ['status', 'updated_at']
    now = timezone.now()
    if status == 'approved':
        commission.approved_by, commission.approved_at = user, now
        fields += ['approved_by', 'approved_at']
    if status == 'paid':
        commission.paid_at = now
        fields.append('paid_at')
        if not commission.approved_at:
            commission.approved_by, commission.approved_at = user, now
            fields += ['approved_by', 'approved_at']
    commission.save(update_fields=fields)
    if commission.lead_id:
        type(commission.lead).objects.filter(pk=commission.lead_id).update(commission_status=status)
    if status in ('approved', 'paid') and commission.agent.email:
        mailer.queue(f'commission_{status}', {
            'to_email': commission.agent.email, 'to_name': commission.agent.get_full_name(),
            'agent_name': commission.agent.get_full_name(), 'client_name': commission.client_name,
            'commission_amount': commission.commission_amount,
        })
