"""
Registry-driven list/create/edit/delete pages for the admin panel's
plain-CRUD modules (catalog, people, config). Each legacy page like
admin/accommodations.php or admin/suppliers.php was the same shape — a
filterable table plus an add/edit form — so here it's one set of views
driven by a Resource declaration instead of one hand-written view each.
Anything with real workflow (bookings, quotations, leads, commissions)
has its own view module instead.
"""
import json
from dataclasses import dataclass, field

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.views.decorators.http import require_POST

from apps.content.models import EmailTemplate, Review, TeamMember
from apps.core.middleware import log_activity
from apps.core.models import CurrencyRate
from apps.core.permissions import staff_required
from apps.crm.models import Customer
from apps.operations.models import Incident, StaffMember, Supplier
from apps.packages.models import Accommodation, Activity, Itinerary, Package, ParkFee, SeasonalRate, Vehicle


class StyledModelForm(forms.ModelForm):
    """Adds the legacy admin-input class to every widget and renders JSON fields as editable JSON text."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, (forms.CheckboxInput, forms.ClearableFileInput)):
                continue
            if isinstance(w, forms.DateInput):
                w.input_type = 'date'
            if isinstance(w, forms.DateTimeInput):
                w.input_type = 'datetime-local'
                w.format = '%Y-%m-%dT%H:%M'
            if isinstance(f, forms.JSONField):
                w.attrs['class'] = 'admin-input code'
                w.attrs['rows'] = 12
                continue
            w.attrs['class'] = (w.attrs.get('class', '') + ' admin-input').strip()


@dataclass
class Resource:
    slug: str
    model: type
    title: str
    singular: str
    columns: list  # [(attr_path, label)]
    form_fields: list
    search: list = field(default_factory=list)
    filters: list = field(default_factory=list)  # choice/boolean fields rendered as filter pills
    ordering: list = field(default_factory=list)
    admin_only: bool = False
    deletable: bool = True
    creatable: bool = True
    soft_delete: bool = False  # deactivate (is_active=False) instead of deleting — catalog rows are referenced by history
    detail_url: str = ''  # optional url name taking pk, linked from the first column
    widgets: dict = field(default_factory=dict)
    help: str = ''

    def form_class(self):
        return forms.modelform_factory(self.model, form=StyledModelForm, fields=self.form_fields, widgets=self.widgets)

    def url(self):
        return reverse(f'crud:{self.slug}')


TEXTAREA = forms.Textarea(attrs={'rows': 3})

RESOURCES = {r.slug: r for r in [
    Resource('packages', Package, 'Packages', 'Package',
             [('name', 'Package'), ('duration_days', 'Days'), ('accommodation_level', 'Level'), ('price_1pax', 'From (1 pax)'),
              ('itinerary.name', 'Itinerary'), ('is_featured', 'Featured'), ('is_active', 'Active')],
             ['name', 'slug', 'duration_days', 'itinerary', 'accommodation_level', 'price_1pax', 'short_description', 'overview',
              'price_notes', 'includes', 'excludes', 'cost_breakdown', 'hero_image', 'is_featured', 'is_active', 'sort_order'],
             search=['name', 'slug'], filters=['accommodation_level', 'is_active'], ordering=['sort_order', 'id'], soft_delete=True,
             detail_url='dashboard:package_detail',
             help='Prices are itemised from the linked itinerary — use “Reprice from itinerary” on the package page after changing rates.'),
    Resource('itineraries', Itinerary, 'Itineraries', 'Itinerary',
             [('name', 'Itinerary'), ('duration_days', 'Days'), ('accommodation_level', 'Level'), ('base_price_pax', 'Base / pax'), ('is_active', 'Active')],
             ['name', 'slug', 'duration_days', 'accommodation_level', 'overview', 'base_price_pax', 'days', 'includes', 'excludes', 'is_active', 'sort_order'],
             search=['name'], filters=['accommodation_level', 'is_active'], soft_delete=True,
             help='“Days” is the day-by-day JSON (accommodation_name/rate, vehicle_name/rate, park_fee_name/park_adult_fee, activities, meals_cost_pp, other_items) the pricing engine reads.'),
    Resource('accommodations', Accommodation, 'Accommodations', 'Accommodation',
             [('name', 'Name'), ('level', 'Level'), ('location', 'Location'), ('rate_per_room', 'Per room'), ('rate_per_person', 'Per person'),
              ('single_supplement', 'Single supp.'), ('child_rate', 'Child'), ('meal_plan', 'Meals'), ('is_active', 'Active')],
             ['name', 'level', 'category', 'location', 'park_key', 'rate_per_room', 'rate_per_person', 'rate_low', 'rate_high',
              'single_supplement', 'child_rate', 'meal_plan', 'notes', 'is_active'],
             search=['name', 'location'], filters=['level', 'is_active'], soft_delete=True),
    Resource('activities', Activity, 'Activities', 'Activity',
             [('name', 'Activity'), ('category', 'Category'), ('price', 'Price'), ('price_unit', 'Unit'), ('is_active', 'Active')],
             ['name', 'activity_key', 'category', 'price', 'price_unit', 'description', 'is_active'],
             search=['name', 'category'], filters=['price_unit', 'is_active'], soft_delete=True),
    Resource('vehicles', Vehicle, 'Fleet', 'Vehicle',
             [('name', 'Vehicle'), ('level', 'Level'), ('capacity', 'Seats'), ('daily_rate', 'Daily rate'), ('fuel_cost_day', 'Fuel/day'),
              ('driver_cost_day', 'Driver/day'), ('is_active', 'Active')],
             ['name', 'vehicle_key', 'level', 'capacity', 'daily_rate', 'fuel_cost_day', 'driver_cost_day', 'is_active'],
             search=['name'], filters=['level', 'is_active'], soft_delete=True),
    Resource('park-fees', ParkFee, 'Park Fees', 'Park fee',
             [('name', 'Park'), ('country', 'Country'), ('adult_fee', 'Adult'), ('child_fee', 'Child'), ('resident_adult', 'Resident adult'),
              ('vehicle_fee', 'Vehicle'), ('is_active', 'Active')],
             ['name', 'park_key', 'country', 'adult_fee', 'child_fee', 'resident_adult', 'resident_child', 'vehicle_fee', 'fee_unit', 'notes', 'is_active'],
             search=['name'], filters=['is_active'], soft_delete=True),
    Resource('seasons', SeasonalRate, 'Seasons', 'Season',
             [('name', 'Season'), ('season_key', 'Key'), ('multiplier', 'Multiplier'), ('start_month', 'From month'), ('end_month', 'To month')],
             ['name', 'season_key', 'multiplier', 'start_month', 'end_month', 'description'], deletable=False),
    Resource('team', TeamMember, 'Team', 'Team member',
             [('name', 'Name'), ('role', 'Role'), ('member_type', 'Type'), ('email', 'Email'), ('sort_order', 'Order'), ('is_active', 'Active')],
             ['name', 'role', 'member_type', 'bio', 'photo', 'email', 'phone', 'linkedin_url', 'sort_order', 'is_active'],
             search=['name', 'role'], filters=['member_type', 'is_active'], ordering=['sort_order', 'id']),
    Resource('suppliers', Supplier, 'Suppliers', 'Supplier',
             [('name', 'Supplier'), ('category', 'Category'), ('contact_person', 'Contact'), ('phone', 'Phone'), ('payment_terms', 'Terms'), ('contract', 'Contract'), ('is_active', 'Active')],
             ['name', 'category', 'contact_person', 'phone', 'email', 'payment_terms', 'contract', 'notes', 'is_active'],
             search=['name', 'contact_person', 'email'], filters=['category', 'is_active'], soft_delete=True),
    Resource('staff', StaffMember, 'Guides & Drivers', 'Guide / driver',
             [('full_name', 'Name'), ('role', 'Role'), ('phone', 'Phone'), ('languages', 'Languages'), ('daily_rate', 'Daily rate'), ('is_active', 'Active')],
             ['full_name', 'role', 'phone', 'email', 'languages', 'license_number', 'daily_rate', 'notes', 'is_active'],
             search=['full_name', 'languages'], filters=['role', 'is_active'], soft_delete=True),
    Resource('customers', Customer, 'Customers', 'Customer',
             [('full_name', 'Name'), ('email', 'Email'), ('phone', 'Phone'), ('country', 'Country'), ('first_seen_at', 'First seen')],
             ['full_name', 'email', 'phone', 'country'],
             search=['full_name', 'email', 'phone', 'country'], ordering=['-first_seen_at'], detail_url='dashboard:customer_detail',
             deletable=False),
    Resource('incidents', Incident, 'Incidents', 'Incident',
             [('created_at', 'Logged'), ('booking_ref', 'Booking'), ('incident_type', 'Type'), ('severity', 'Severity'), ('status', 'Status'),
              ('description', 'Description')],
             ['booking_ref', 'incident_type', 'severity', 'status', 'occurred_at', 'description', 'resolution_notes'],
             search=['booking_ref', 'description'], filters=['status', 'severity', 'incident_type'], ordering=['-created_at']),
    Resource('reviews', Review, 'Reviews', 'Review',
             [('submitted_at', 'Submitted'), ('guest_name', 'Guest'), ('guest_country', 'Country'), ('rating', 'Rating'), ('nps_score', 'NPS'),
              ('booking_ref', 'Booking'), ('is_published', 'Published')],
             ['guest_name', 'guest_country', 'booking_ref', 'rating', 'nps_score', 'comment', 'is_published'],
             search=['guest_name', 'comment', 'booking_ref'], filters=['is_published', 'rating'], ordering=['-submitted_at']),
    Resource('email-templates', EmailTemplate, 'Email Templates', 'Email template',
             [('template_key', 'Template'), ('subject', 'Subject'), ('updated_at', 'Updated')],
             ['template_key', 'subject', 'body_html', 'is_custom'], search=['template_key', 'subject'],
             help='Any template key saved here overrides the built-in default (booking_confirmation, deposit_receipt, invoice_paid, '
                  'quotation_sent, lead_converted, commission_approved, commission_paid, custom_request_ack). Use {{ variable }} placeholders.'),
    Resource('currencies', CurrencyRate, 'Currencies', 'Currency',
             [('code', 'Code'), ('name', 'Name'), ('symbol', 'Symbol'), ('rate_to_usd', 'Per 1 USD'), ('is_active', 'Active'), ('updated_at', 'Updated')],
             ['code', 'name', 'symbol', 'rate_to_usd', 'is_active'], admin_only=True),
]}


def _resource(request, slug):
    res = RESOURCES.get(slug)
    if not res:
        raise Http404
    if res.admin_only and not request.user.is_admin_role:
        raise PermissionDenied('Admin access required.')
    return res


def _choice_filters(res, request):
    out = []
    for name in res.filters:
        f = res.model._meta.get_field(name)
        if f.get_internal_type() == 'BooleanField':
            choices = [('1', 'Yes'), ('0', 'No')]
        else:
            choices = [(str(k), v) for k, v in (f.choices or [])]
            if not choices:
                choices = [(str(v), str(v)) for v in res.model.objects.order_by(name).values_list(name, flat=True).distinct()]
        out.append({'name': name, 'label': f.verbose_name.title(), 'choices': choices, 'current': request.GET.get(name, '')})
    return out


@staff_required
def list_view(request, slug):
    res = _resource(request, slug)
    qs = res.model.objects.all()
    if res.ordering:
        qs = qs.order_by(*res.ordering)
    elif not res.model._meta.ordering:
        qs = qs.order_by('pk')  # stable pagination
    q = request.GET.get('q', '').strip()
    if q and res.search:
        cond = Q()
        for s in res.search:
            cond |= Q(**{f'{s}__icontains': q})
        qs = qs.filter(cond)
    for name in res.filters:
        val = request.GET.get(name)
        if val not in (None, ''):
            f = res.model._meta.get_field(name)
            qs = qs.filter(**{name: val == '1'} if f.get_internal_type() == 'BooleanField' else {name: val})
    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    return render(request, 'dashboard/crud/list.html', {
        'res': res, 'page_obj': page, 'q': q, 'filters': _choice_filters(res, request), 'page_title': res.title,
    })


@staff_required
def form_view(request, slug, pk=None):
    res = _resource(request, slug)
    obj = get_object_or_404(res.model, pk=pk) if pk is not None else None
    if obj is None and not res.creatable:
        raise Http404
    Form = res.form_class()
    if request.method == 'POST':
        form = Form(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            saved = form.save()
            if isinstance(saved, Incident) and not saved.reported_by_id:
                Incident.objects.filter(pk=saved.pk).update(reported_by=request.user)
            if isinstance(saved, Incident) and saved.status == 'resolved' and not saved.resolved_at:
                from django.utils import timezone
                Incident.objects.filter(pk=saved.pk).update(resolved_at=timezone.now())
            log_activity(request, request.user, 'update' if obj else 'create', res.model.__name__, saved.pk, f'{res.singular}: {saved}')
            messages.success(request, f'{res.singular} saved.')
            return redirect(res.url())
    else:
        form = Form(instance=obj)
    return render(request, 'dashboard/crud/form.html', {
        'res': res, 'form': form, 'obj': obj,
        'page_title': f'{"Edit" if obj else "Add"} {res.singular}',
    })


@staff_required
@require_POST
def delete_view(request, slug, pk):
    res = _resource(request, slug)
    if not res.deletable or not request.user.may_delete:
        raise PermissionDenied('You do not have permission to delete records.')
    obj = get_object_or_404(res.model, pk=pk)
    label = str(obj)
    if res.soft_delete and hasattr(obj, 'is_active'):
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        messages.success(request, f'{res.singular} “{label}” deactivated.')
    else:
        obj.delete()
        messages.success(request, f'{res.singular} “{label}” deleted.')
    log_activity(request, request.user, 'delete', res.model.__name__, pk, f'{res.singular}: {label}')
    return redirect(res.url())


def json_pretty(value):
    return json.dumps(value, indent=2, ensure_ascii=False)


urlpatterns = []
for _slug in RESOURCES:
    urlpatterns += [
        path(f'{_slug}/', list_view, {'slug': _slug}, name=_slug),
        path(f'{_slug}/new/', form_view, {'slug': _slug}, name=f'{_slug}-new'),
        path(f'{_slug}/<str:pk>/edit/', form_view, {'slug': _slug}, name=f'{_slug}-edit'),
        path(f'{_slug}/<str:pk>/delete/', delete_view, {'slug': _slug}, name=f'{_slug}-delete'),
    ]
