from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*']

# Relaxed for local HTTP development only — production.py turns every one
# of these on. Never import development.py in a deployed environment.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Plain storage locally so runserver serves edited CSS/JS without a collectstatic manifest.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
