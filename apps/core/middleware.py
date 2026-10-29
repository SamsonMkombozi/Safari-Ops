import time

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


class SessionTimeoutMiddleware:
    """Mirrors the legacy PHP admin's inactivity-timeout rule (SESSION_TIMEOUT_MINUTES) — an authenticated session that's gone quiet for too long is force-logged-out on its next request, same as before, rather than staying valid indefinitely."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.path.startswith('/api/'):
            last_active = request.session.get('last_active')
            now = time.time()
            from apps.core.settings_store import get_setting
            timeout = max(5, int(get_setting('session_timeout_minutes', settings.SESSION_TIMEOUT_MINUTES)))
            if last_active and (now - last_active) > timeout * 60:
                logout(request)
                return redirect(f"{reverse('accounts:login')}?reason=timeout")
            request.session['last_active'] = now
        return self.get_response(request)


class ActivityLogMiddleware:
    """Attaches the request's IP/user-agent to a thread-local-ish request attribute so views and signal handlers can log who-did-what without threading request objects through every call site."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_ip = self._client_ip(request)
        return self.get_response(request)

    @staticmethod
    def _client_ip(request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


def log_activity(request, actor, action, object_type='', object_id='', description=''):
    """Call this from any view/serializer after a meaningful write. Kept as a plain function (not a signal) so the call site stays explicit about what it's logging, same reasoning as the legacy app's own activity-log helper."""
    from apps.core.models import ActivityLog
    ActivityLog.objects.create(
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        description=description[:500],
        ip_address=getattr(request, 'client_ip', None),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
    )
