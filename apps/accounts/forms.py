from django import forms
from django.contrib.auth.forms import AuthenticationForm


class StyledAuthenticationForm(AuthenticationForm):
    """Same validation as Django's built-in login form, just with the CSS classes our Tailwind templates expect."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'input-field', 'autofocus': True, 'autocomplete': 'username', 'placeholder': 'Username',
        })
        self.fields['password'].widget.attrs.update({
            'class': 'input-field', 'autocomplete': 'current-password', 'placeholder': 'Password',
        })


class ProfileForm(forms.Form):
    full_name = forms.CharField(max_length=150, required=True)
    phone = forms.CharField(max_length=30, required=False)
    bio = forms.CharField(widget=forms.Textarea, required=False)


class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput)
    new_password = forms.CharField(widget=forms.PasswordInput, min_length=10)
    confirm_password = forms.CharField(widget=forms.PasswordInput, min_length=10)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('new_password') != cleaned.get('confirm_password'):
            raise forms.ValidationError('New password and confirmation do not match.')
        return cleaned
