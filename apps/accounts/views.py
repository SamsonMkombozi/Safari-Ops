from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.middleware import log_activity
from apps.core.permissions import STAFF_ROLES

from .forms import ChangePasswordForm, ProfileForm, StyledAuthenticationForm
from .models import User

LOCKOUT_MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _is_locked(user) -> bool:
    return bool(user.locked_until and user.locked_until > timezone.now())


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_post_login_redirect(request.user))

    error = None
    if request.GET.get('reason') == 'timeout':
        error = 'Your session expired due to inactivity. Please sign in again.'

    if request.method == 'POST':
        form = StyledAuthenticationForm(request, data=request.POST)
        username = request.POST.get('username', '').strip()
        try:
            existing = User.objects.get(username=username)
        except User.DoesNotExist:
            existing = None

        if existing and _is_locked(existing):
            remaining = int((existing.locked_until - timezone.now()).total_seconds() / 60) + 1
            error = f'Too many failed attempts. Try again in {remaining} minute(s).'
        elif form.is_valid():
            user = form.get_user()
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=['failed_login_attempts', 'locked_until'])
            login(request, user)
            log_activity(request, user, 'login', 'User', user.id, f'{user.username} logged in')
            return redirect(_post_login_redirect(user))
        else:
            if existing:
                existing.failed_login_attempts += 1
                if existing.failed_login_attempts >= LOCKOUT_MAX_ATTEMPTS:
                    existing.locked_until = timezone.now() + timezone.timedelta(minutes=LOCKOUT_MINUTES)
                existing.save(update_fields=['failed_login_attempts', 'locked_until'])
                log_activity(request, request.user, 'login_failed', 'User', existing.id, f'Failed login for {username}')
            error = 'Invalid username or password.'
    else:
        form = StyledAuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form, 'error': error})


def _post_login_redirect(user):
    return reverse('dashboard:home') if user.role in STAFF_ROLES else reverse('agent_portal:home')


@login_required(login_url='accounts:login')
def logout_view(request):
    log_activity(request, request.user, 'logout', 'User', request.user.id, f'{request.user.username} logged out')
    logout(request)
    return redirect('accounts:login')


@login_required(login_url='accounts:login')
def profile_view(request):
    user = request.user
    if request.method == 'POST':
        form = ProfileForm(request.POST)
        if form.is_valid():
            user.first_name = form.cleaned_data['full_name']
            user.phone = form.cleaned_data['phone']
            user.bio = form.cleaned_data['bio']
            user.save(update_fields=['first_name', 'phone', 'bio', 'updated_at'])
            log_activity(request, user, 'update', 'User', user.id, 'Updated own profile')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(initial={'full_name': user.get_full_name(), 'phone': user.phone, 'bio': user.bio})
    return render(request, 'accounts/profile.html', {'form': form})


@login_required(login_url='accounts:login')
def change_password_view(request):
    error = None
    success = False
    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            user = request.user
            if not user.check_password(form.cleaned_data['current_password']):
                error = 'Current password is incorrect.'
            else:
                try:
                    validate_password(form.cleaned_data['new_password'], user=user)
                    user.set_password(form.cleaned_data['new_password'])
                    user.save(update_fields=['password'])
                    log_activity(request, user, 'update', 'User', user.id, 'Changed own password')
                    success = True
                except ValidationError as exc:
                    error = ' '.join(exc.messages)
    else:
        form = ChangePasswordForm()
    return render(request, 'accounts/change_password.html', {'form': form, 'error': error, 'success': success})
