from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm

from .models import User


class StyledAuthenticationForm(AuthenticationForm):
    """Same validation as Django's built-in login form, just with the CSS classes our Tailwind templates expect."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'admin-input', 'autofocus': True, 'autocomplete': 'username', 'placeholder': 'Username',
        })
        self.fields['password'].widget.attrs.update({
            'class': 'admin-input', 'autocomplete': 'current-password', 'placeholder': 'Password',
        })


class _Styled(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs['class'] = 'admin-input'


class ProfileForm(_Styled):
    full_name = forms.CharField(max_length=150, required=True)
    phone = forms.CharField(max_length=30, required=False)
    bio = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    theme_preference = forms.ChoiceField(choices=User.THEME_CHOICES, label='Theme')


class ChangePasswordForm(_Styled):
    current_password = forms.CharField(widget=forms.PasswordInput)
    new_password = forms.CharField(widget=forms.PasswordInput, min_length=10)
    confirm_password = forms.CharField(widget=forms.PasswordInput, min_length=10)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('new_password') != cleaned.get('confirm_password'):
            raise forms.ValidationError('New password and confirmation do not match.')
        return cleaned


class StyledPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({'class': 'admin-input', 'autofocus': True, 'placeholder': 'you@company.com'})

    def get_users(self, email):
        # Django's default skips accounts with an unusable password — exactly
        # the imported users who most need a reset link. Active users only.
        from django.contrib.auth import get_user_model
        return get_user_model()._default_manager.filter(email__iexact=email, is_active=True)


class StyledSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs['class'] = 'admin-input'
