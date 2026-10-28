from django.db.models import Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.core.permissions import agent_required
from apps.crm.models import Commission, Lead


@agent_required
def home(request):
    agent = request.user
    month_start = timezone.now().date().replace(day=1)

    stats = {
        'leads_total': Lead.objects.filter(agent=agent).count(),
        'leads_active': Lead.objects.filter(agent=agent).exclude(pipeline_stage__in=['completed', 'lost']).count(),
        'leads_booked': Lead.objects.filter(agent=agent, pipeline_stage='booked').count(),
        'commission_pending': Commission.objects.filter(agent=agent, status='pending').aggregate(t=Sum('commission_amount'))['t'] or 0,
        'commission_approved': Commission.objects.filter(agent=agent, status='approved').aggregate(t=Sum('commission_amount'))['t'] or 0,
        'commission_paid_this_month': Commission.objects.filter(
            agent=agent, status='paid', paid_at__date__gte=month_start,
        ).aggregate(t=Sum('commission_amount'))['t'] or 0,
    }
    recent_leads = Lead.objects.filter(agent=agent).order_by('-created_at')[:8]
    recent_commissions = Commission.objects.filter(agent=agent).order_by('-created_at')[:8]

    return render(request, 'agent_portal/home.html', {
        'stats': stats, 'recent_leads': recent_leads, 'recent_commissions': recent_commissions,
    })


@agent_required
def lead_list(request):
    stage = request.GET.get('stage', '')
    leads = Lead.objects.filter(agent=request.user).order_by('-created_at')
    if stage:
        leads = leads.filter(pipeline_stage=stage)
    return render(request, 'agent_portal/leads.html', {
        'leads': leads, 'stage_filter': stage, 'stages': Lead._meta.get_field('pipeline_stage').choices,
    })


@agent_required
def lead_detail(request, pk):
    lead = get_object_or_404(Lead, pk=pk, agent=request.user)  # the `agent=request.user` filter IS the ownership check — a 404, not a 403, for someone else's lead id
    return render(request, 'agent_portal/lead_detail.html', {'lead': lead})


@agent_required
def commission_list(request):
    commissions = Commission.objects.filter(agent=request.user).order_by('-created_at')
    return render(request, 'agent_portal/commissions.html', {'commissions': commissions})
