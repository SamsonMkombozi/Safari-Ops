from .base import *  # noqa: F401,F403

DEBUG = False

if not ALLOWED_HOSTS:
    raise RuntimeError('ALLOWED_HOSTS must be set explicitly in production (.env).')

# ── Transport security ──────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ── Cookies ──────────────────────────────────────────────────────
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SAMESITE = 'Strict'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = SESSION_TIMEOUT_MINUTES * 60

# ── Headers ──────────────────────────────────────────────────────
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

# CORS must never be wide open in production — only the explicit
# integration partners configured via CORS_ALLOWED_ORIGINS in .env.
CORS_ALLOW_ALL_ORIGINS = False

# ── Email (for password resets, booking notifications, etc.) ─────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)

ADMINS = [tuple(a.split(':')) for a in env.list('ADMINS', default=[])]
SERVER_EMAIL = env('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)

LOGGING['root']['level'] = 'WARNING'  # noqa: F405
