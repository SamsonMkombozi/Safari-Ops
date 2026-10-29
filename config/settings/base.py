"""
Base settings shared by every environment. Environment-specific
overrides (DEBUG, ALLOWED_HOSTS, security flags, logging verbosity)
live in development.py / production.py — never branch on DEBUG inside
this file, that's exactly the pattern that leaks a dev-only setting
into production by accident.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

# ── Applications ────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    # Required by SIMPLE_JWT['BLACKLIST_AFTER_ROTATION'] below — without
    # it rotated refresh tokens are never actually revoked.
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
]

LOCAL_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.packages',
    'apps.bookings',
    'apps.crm',
    'apps.content',
    'apps.api',
    'apps.dashboard',
    'apps.agent_portal',
    'apps.operations',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = 'accounts.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.ActivityLogMiddleware',
    'apps.core.middleware.SessionTimeoutMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site_meta',
                'apps.dashboard.nav.admin_nav',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ── Database ────────────────────────────────────────────────────
# 'default' is the new Django-native database (fresh schema, Django
# migrations are the source of truth). 'legacy' is the OLD PHP app's
# MySQL database, wired up read-only-by-convention and used only by
# the one-time `import_legacy_data` management command — never by
# application code at request time.
DATABASES = {
    'default': {
        'ENGINE': env('DB_ENGINE', default='django.db.backends.mysql'),
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='3306'),
        'OPTIONS': {'charset': 'utf8mb4'},
    },
    'legacy': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('LEGACY_DB_NAME', default=''),
        'USER': env('LEGACY_DB_USER', default=''),
        'PASSWORD': env('LEGACY_DB_PASSWORD', default=''),
        'HOST': env('LEGACY_DB_HOST', default='localhost'),
        'PORT': env('LEGACY_DB_PORT', default='3306'),
        'OPTIONS': {'charset': 'utf8mb4'},
    },
}
DATABASE_ROUTERS = ['apps.core.db_routers.LegacyRouter']

# mysqlclient isn't installed (no libmysqlclient-dev build step available
# offline) — PyMySQL is, and this shim makes it satisfy Django's import of
# `MySQLdb`, which is all the mysql backend actually needs.
import pymysql  # noqa: E402
pymysql.install_as_MySQLdb()

# ── Password validation ─────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/accounts/login/'

# PBKDF2 for every new/changed password; bcrypt kept so passwords migrated
# from the legacy PHP app ('$2y$' hashes) still verify — Django re-hashes
# each one to PBKDF2 automatically on that user's next successful login.
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
]

# Cache backs the settings store, login/tracking lockouts and throttles.
# LocMem is per-process: fine for one worker; set CACHE_URL (e.g.
# dbcache://django_cache — run `createcachetable` — or rediscache://host:6379/1)
# when running several gunicorn workers so lockouts are shared.
CACHES = {'default': env.cache('CACHE_URL', default='locmemcache://')}

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# App-specific cookie names. Browsers share cookies across every PORT of a
# host, so on a server running several apps (IP:8200, IP:8300, IP:8600 …)
# Django's default 'csrftoken'/'sessionid' collide: another app's Secure
# 'csrftoken' even blocks this app from setting its own over HTTP, which
# made every login fail with "CSRF cookie not set".
SESSION_COOKIE_NAME = env('SESSION_COOKIE_NAME', default='safariops_sessionid')
CSRF_COOKIE_NAME = env('CSRF_COOKIE_NAME', default='safariops_csrftoken')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='Safari-Ops <no-reply@localhost>')
SERVER_EMAIL = env('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)

# Uploads (supplier contracts, team photos)
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

# ── I18N ────────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True

# ── Static & media ──────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Django 5.1 removed the STATICFILES_STORAGE setting outright (it was
# silently ignored here) — STORAGES is the only form it reads now.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── REST Framework ──────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'apps.api.authentication.APIKeyAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '300/min',
        'login': '10/min',
        'tracking': '8/hour',
        'quote_view': '120/hour',
    },
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'EXCEPTION_HANDLER': 'apps.api.exceptions.safariz_exception_handler',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=env.int('JWT_ACCESS_TOKEN_LIFETIME_MIN', default=30)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=env.int('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ── CORS — external sites (WordPress, Joomla, any CMS) integrating
#    with the API must be explicitly allow-listed here; never left wide
#    open, since the API carries authenticated booking/customer data. ──
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True

# ── App-specific business settings (mirrors the legacy PHP app's config) ──
SESSION_TIMEOUT_MINUTES = env.int('SESSION_TIMEOUT_MINUTES', default=30)
# Public base URL — used to build absolute links in emails sent outside a request (cron, management commands).
SITE_URL = env('SITE_URL', default='http://localhost:8010').rstrip('/')
WHATSAPP_NUMBER = env('WHATSAPP_NUMBER', default='')
BANK_NAME = env('BANK_NAME', default='')
BANK_ACCOUNT_NO = env('BANK_ACCOUNT_NO', default='')
BANK_SWIFT = env('BANK_SWIFT', default='')

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{asctime} [{levelname}] {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'safariz.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'security.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console', 'file'], 'level': 'INFO'},
    'loggers': {
        'django.security': {'handlers': ['security_file', 'console'], 'level': 'WARNING', 'propagate': False},
        'apps': {'handlers': ['file', 'console'], 'level': 'INFO', 'propagate': False},
    },
}
