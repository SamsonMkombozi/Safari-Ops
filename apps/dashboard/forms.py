from django import forms
from django.contrib.auth.password_validation import validate_password

from apps.accounts.models import User
from apps.bookings.models import Booking, Payment
from apps.crm.models import Lead
from apps.dashboard.crud import StyledModelForm
from apps.packages.models import ACCOMMODATION_LEVELS, Itinerary, Package


def check_party_size(data):
    """Shared adults+children cap (the max_party_size setting) — the legacy BookingValidator rule."""
    from apps.core.settings_store import get_setting
    cap = int(get_setting('max_party_size'))
    total = (data.get('adults') or 0) + (data.get('children') or 0)
    if total > cap:
        raise forms.ValidationError(f'Party size {total} exceeds the maximum of {cap} travelers per booking — split the group or raise the limit in Settings.')


class StyledForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                continue
            if isinstance(w, forms.DateInput):
                w.input_type = 'date'
            w.attrs['class'] = (w.attrs.get('class', '') + ' admin-input').strip()


class PaymentForm(StyledModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'method', 'kind', 'reference', 'received_at', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}
        help_texts = {'kind': 'Leave as-is to auto-classify; use Refund with a negative amount to record money returned.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kind'].required = False


class BookingEditForm(StyledModelForm):
    class Meta:
        model = Booking
        fields = ['full_name', 'email', 'phone', 'country', 'package', 'package_name', 'accommodation_level', 'travel_date',
                  'adults', 'children', 'rooms', 'total_amount', 'deposit_amount', 'supplier_cost', 'special_request', 'payment_notes']
        widgets = {'special_request': forms.Textarea(attrs={'rows': 3}), 'payment_notes': forms.Textarea(attrs={'rows': 3})}

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.travelers = obj.adults + obj.children
        if commit:
            obj.save()
        return obj


class StatusForm(StyledForm):
    status = forms.ChoiceField(choices=Booking.PAYMENT_STATUS_CHOICES)
    amount_paid = forms.DecimalField(required=False, min_value=0, decimal_places=2,
                                     help_text='Required for “Deposit Paid” — the amount actually received.')


class AssignmentForm(StyledForm):
    staff = forms.ModelChoiceField(queryset=None, required=False, label='Guide / driver')
    vehicle = forms.ModelChoiceField(queryset=None, required=False)
    notes = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        from apps.operations.models import StaffMember
        from apps.packages.models import Vehicle
        super().__init__(*args, **kwargs)
        self.fields['staff'].queryset = StaffMember.objects.filter(is_active=True)
        self.fields['vehicle'].queryset = Vehicle.objects.filter(is_active=True)


class QuotationForm(StyledForm):
    client_name = forms.CharField(max_length=150)
    client_email = forms.EmailField()
    client_phone = forms.CharField(max_length=50, required=False)
    client_country = forms.CharField(max_length=100, required=False, help_text='EAC residents (TZ/KE/UG/RW/BI) get resident park rates.')
    package = forms.ModelChoiceField(queryset=Package.objects.filter(is_active=True), required=False)
    itinerary = forms.ModelChoiceField(queryset=Itinerary.objects.filter(is_active=True), required=False,
                                       help_text='Optional — overrides the package’s own itinerary.')
    adults = forms.IntegerField(min_value=1, max_value=60, initial=2)
    children = forms.IntegerField(min_value=0, max_value=60, initial=0)
    rooms = forms.IntegerField(min_value=1, max_value=30, initial=1)
    start_date = forms.DateField(required=False)
    accommodation_level = forms.ChoiceField(choices=ACCOMMODATION_LEVELS, initial='midrange')
    markup_pct = forms.DecimalField(min_value=0, max_value=200, initial=0, label='Markup %')
    discount_pct = forms.DecimalField(min_value=0, max_value=100, initial=0, label='Discount %')
    flight_cost = forms.DecimalField(min_value=0, initial=0, required=False, label='Internal flights (total)')
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False, label='Notes for client')
    lead_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    request_id = forms.IntegerField(required=False, widget=forms.HiddenInput)

    def clean(self):
        data = super().clean()
        if not data.get('package') and not data.get('itinerary'):
            raise forms.ValidationError('Choose a package or an itinerary to price.')
        check_party_size(data)
        return data


class LeadForm(StyledModelForm):
    class Meta:
        model = Lead
        fields = ['full_name', 'email', 'phone', 'country', 'source', 'package_name', 'party_size', 'travel_date',
                  'budget_range', 'destinations', 'booking_value', 'commission_rate', 'agent', 'assigned_to', 'next_follow_up', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 3}), 'destinations': forms.TextInput()}
        help_texts = {'commission_rate': 'Leave empty to use the agent’s own rate (or the site default).'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['agent'].queryset = User.objects.filter(role='agent', is_active=True)
        self.fields['assigned_to'].queryset = User.objects.filter(is_active=True)


class UserForm(StyledModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=False), required=False,
                               help_text='Leave blank to keep the current password. Minimum 10 characters.')

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'role', 'commission_rate', 'target_monthly',
                  'can_change_status', 'can_delete_records', 'is_active', 'bio']
        widgets = {'bio': forms.Textarea(attrs={'rows': 2})}

    def clean_password(self):
        pw = self.cleaned_data.get('password')
        if not self.instance.pk and not pw:
            raise forms.ValidationError('A password is required for a new user.')
        if pw:
            validate_password(pw, self.instance)
        return pw

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('password'):
            user.set_password(self.cleaned_data['password'])
        user.is_staff = user.role in ('owner', 'admin')
        if commit:
            user.save()
        return user


class SettingsForm(StyledForm):
    deposit_percent = forms.IntegerField(min_value=0, max_value=100, label='Deposit %')
    balance_days = forms.IntegerField(min_value=0, label='Balance due (days before travel)')
    vat_rate = forms.FloatField(min_value=0, max_value=1, label='VAT rate (0.18 = 18%)')
    service_charge_rate = forms.FloatField(min_value=0, max_value=1, label='Service charge rate')
    default_commission_rate = forms.FloatField(min_value=0, max_value=100, label='Default agent commission %')
    quotation_validity_days = forms.IntegerField(min_value=1, label='Quotation validity (days)')
    max_party_size = forms.IntegerField(min_value=1)
    session_timeout_minutes = forms.IntegerField(min_value=5)
    agent_direct_booking_enabled = forms.BooleanField(required=False, label='Agents may book packages directly')
    auto_send_payment_emails = forms.BooleanField(required=False, label='Auto-send invoice/receipt emails on payment')
    maintenance_mode = forms.BooleanField(required=False, label='Maintenance mode (public submissions paused)')
    app_name = forms.CharField(max_length=60, label='App name', help_text='Shown in the sidebar, page titles, login page and emails.')
    site_email = forms.EmailField()
    admin_email = forms.EmailField()
    whatsapp_number = forms.CharField(required=False)
    bank_name = forms.CharField(required=False)
    bank_account_name = forms.CharField(required=False)
    bank_account_no = forms.CharField(required=False)
    bank_swift = forms.CharField(required=False)
    wise_email = forms.EmailField(required=False)


class EmergencyContactsForm(StyledForm):
    office_24h = forms.CharField(required=False, label='24-Hour Office Line')
    hospital = forms.CharField(required=False, label='Recommended Hospital (Arusha)')
    police = forms.CharField(required=False, label='Police Emergency')
    tourist_police = forms.CharField(required=False, label='Tourist Police')
    evacuation_provider = forms.CharField(required=False, label='Medical Evacuation Provider')
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}), label='Additional Notes')


class AgentRateForm(StyledForm):
    agent = forms.ModelChoiceField(queryset=User.objects.filter(role='agent'))
    rate = forms.DecimalField(min_value=0, max_value=100, decimal_places=2)
