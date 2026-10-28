from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.core.models import APIKey


class APIKeyAuthentication(BaseAuthentication):
    """
    Authenticates external integrations (a WordPress/Joomla plugin, any
    other CMS/backend) via a static `X-API-Key` header instead of a user
    login — this is a service credential, not tied to any human account,
    and is the mechanism CORS_ALLOWED_ORIGINS + can_read/can_write on the
    key itself are meant to gate.
    """

    def authenticate(self, request):
        key = request.headers.get('X-API-Key')
        if not key:
            return None  # let the next authentication class (JWT/session) try

        try:
            api_key = APIKey.objects.get(key=key)
        except APIKey.DoesNotExist:
            raise AuthenticationFailed('Invalid API key.')

        if not api_key.is_active:
            raise AuthenticationFailed('This API key has been revoked.')

        if api_key.allowed_origin:
            origin = request.headers.get('Origin', '') or request.headers.get('Referer', '')
            if api_key.allowed_origin not in origin:
                raise AuthenticationFailed('This API key is not authorized for this origin.')

        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=['last_used_at'])
        return (AnonymousUser(), api_key)

    def authenticate_header(self, request):
        return 'X-API-Key'
