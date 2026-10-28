import logging

from rest_framework.views import exception_handler

security_logger = logging.getLogger('django.security')


def safariz_exception_handler(exc, context):
    """
    Wraps DRF's default handler so every API error comes back in one
    consistent JSON shape ({"success": false, "message": ..., "errors": ...})
    instead of each exception type having its own ad-hoc body — and so
    401/403s get written to the security log for later review, the same
    way the legacy app's RateLimiter/AuthMiddleware failures did.
    """
    response = exception_handler(exc, context)
    if response is None:
        return None

    request = context.get('request')
    if response.status_code in (401, 403):
        security_logger.warning(
            'API %s on %s from %s: %s',
            response.status_code,
            getattr(request, 'path', '?'),
            getattr(request, 'client_ip', getattr(request, 'META', {}).get('REMOTE_ADDR', '?')),
            response.data,
        )

    detail = response.data
    message = detail.get('detail') if isinstance(detail, dict) else None
    response.data = {
        'success': False,
        'message': message or 'Request could not be completed.',
        'errors': detail if not message else None,
    }
    return response
