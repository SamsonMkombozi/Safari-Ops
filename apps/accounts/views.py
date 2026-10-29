from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
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
@require_POST
def theme_view(request):
    """Persist the theme picker choice on the user, so it follows them across browsers/devices instead of living only in one browser's localStorage."""
    theme = request.POST.get('theme', '')
    if theme not in dict(User.THEME_CHOICES):
        return JsonResponse({'success': False, 'message': 'Unknown theme.'}, status=400)
    request.user.theme_preference = theme
    request.user.save(update_fields=['theme_preference', 'updated_at'])
    return JsonResponse({'success': True, 'theme': theme})


def _base_template(user):
    return 'dashboard/_base.html' if user.role in STAFF_ROLES else 'agent_portal/_base.html'


@login_required(login_url='accounts:login')
def logout_view(request):
    # POST-only so a cross-site <img src=".../logout/"> can't sign someone out.
    if request.method != 'POST':
        return redirect(_post_login_redirect(request.user))
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
            user.last_name = ''
            user.theme_preference = form.cleaned_data['theme_preference']
            user.save(update_fields=['first_name', 'last_name', 'phone', 'bio', 'theme_preference', 'updated_at'])
            log_activity(request, user, 'update', 'User', user.id, 'Updated own profile')
            messages.success(request, 'Profile saved.')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(initial={'full_name': user.get_full_name(), 'phone': user.phone, 'bio': user.bio,
                                    'theme_preference': user.theme_preference})
    return render(request, 'accounts/profile.html', {'form': form, 'base_template': _base_template(user), 'page_title': 'My Profile'})


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
                    update_session_auth_hash(request, user)  # keep this session signed in after the hash changes
                    log_activity(request, user, 'update', 'User', user.id, 'Changed own password')
                    success = True
                except ValidationError as exc:
                    error = ' '.join(exc.messages)
    else:
        form = ChangePasswordForm()
    return render(request, 'accounts/change_password.html', {
        'form': form, 'error': error, 'success': success,
        'base_template': _base_template(request.user), 'page_title': 'Change Password',
    })
