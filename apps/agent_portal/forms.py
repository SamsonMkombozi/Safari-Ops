from django import forms

from apps.dashboard.forms import StyledForm, check_party_size
from apps.packages.models import ACCOMMODATION_LEVELS, Package


class DirectBookingForm(StyledForm):
    full_name = forms.CharField(max_length=150, label='Client name')
    email = forms.EmailField(label='Client email')
    phone = forms.CharField(max_length=50, required=False, label='Phone (WhatsApp)')
    country = forms.CharField(max_length=100, required=False)
    package = forms.ModelChoiceField(queryset=Package.objects.filter(is_active=True).order_by('sort_order'))
    travel_date = forms.DateField()
    adults = forms.IntegerField(min_value=1, max_value=60, initial=2)
    children = forms.IntegerField(min_value=0, max_value=60, initial=0)
    accommodation_level = forms.ChoiceField(choices=ACCOMMODATION_LEVELS, initial='midrange')
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False, label='Special requests')

    def clean(self):
        data = super().clean()
        check_party_size(data)
        return data

    def clean_travel_date(self):
        from django.utils import timezone
        d = self.cleaned_data['travel_date']
        if d < timezone.localdate():
            raise forms.ValidationError('Travel date must be in the future.')
        return d


class CustomRequestForm(StyledForm):
    full_name = forms.CharField(max_length=150, label='Client name')
    email = forms.EmailField(label='Client email')
    phone = forms.CharField(max_length=50, required=False)
    country = forms.CharField(max_length=100, required=False)
    adults = forms.IntegerField(min_value=1, initial=2)
    children = forms.IntegerField(min_value=0, initial=0)
    start_date = forms.DateField(required=False)
    duration_days = forms.IntegerField(min_value=1, max_value=60, initial=7)
    flexible_dates = forms.BooleanField(required=False, label='Dates are flexible')
    destinations = forms.CharField(required=False, help_text='Comma-separated, e.g. Serengeti, Ngorongoro, Zanzibar')
    total_budget = forms.CharField(required=False, label='Total budget')
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False, label='What does the client want?')

    def clean(self):
        data = super().clean()
        check_party_size(data)
        return data
