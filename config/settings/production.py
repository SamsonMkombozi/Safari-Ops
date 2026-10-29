from .base import *  # noqa: F401,F403

DEBUG = False

if not ALLOWED_HOSTS:
    raise RuntimeError('ALLOWED_HOSTS must be set explicitly in production (.env).')

# ── Transport security ──────────────────────────────────────────
# HTTPS_ENABLED=False is only for plain-HTTP IP:port demo hosts. It turns
# off the HTTPS redirect, HSTS and Secure cookies — otherwise browsers would
# drop the session/CSRF cookies over HTTP and nobody could log in.
HTTPS_ENABLED = env.bool('HTTPS_ENABLED', default=True)
SECURE_SSL_REDIRECT = HTTPS_ENABLED
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000 if HTTPS_ENABLED else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS_ENABLED
SECURE_HSTS_PRELOAD = HTTPS_ENABLED

# ── Cookies ──────────────────────────────────────────────────────
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SAMESITE = 'Strict'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = SESSION_TIMEOUT_MINUTES * 60  # noqa: F405

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
EMAIL_TIMEOUT = 20
if EMAIL_HOST and env.bool('EMAIL_USE_SSL', default=False):  # e.g. Hostinger on port 465
    EMAIL_USE_SSL, EMAIL_USE_TLS = True, False

ADMINS = [tuple(a.split(':')) for a in env.list('ADMINS', default=[])]
SERVER_EMAIL = env('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)

if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    CSRF_TRUSTED_ORIGINS = [f'{"https" if HTTPS_ENABLED else "http"}://{h.lstrip(".")}' for h in ALLOWED_HOSTS if h not in ('*', 'localhost', '127.0.0.1')]  # noqa: F405

if 'locmem' in CACHES['default']['BACKEND'].lower() and env.int('WEB_CONCURRENCY', default=1) > 1:  # noqa: F405
    import warnings
    warnings.warn('CACHE_URL is per-process LocMem with several workers — login lockouts and settings caching are not shared. Set CACHE_URL.')

# Unhandled 500s are emailed to ADMINS (when set) in addition to the log files.
LOGGING['handlers']['mail_admins'] = {'level': 'ERROR', 'class': 'django.utils.log.AdminEmailHandler'}  # noqa: F405
LOGGING['loggers']['django.request'] = {'handlers': ['file', 'mail_admins'], 'level': 'ERROR', 'propagate': False}  # noqa: F405
LOGGING['root']['level'] = 'WARNING'  # noqa: F405
