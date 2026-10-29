"""Fast, isolated settings for `python manage.py test --settings=config.settings.test` — in-memory SQLite, no MySQL needed."""
from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ['testserver', 'localhost']
DATABASES = {
    'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'},
    'legacy': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'},
}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher', 'django.contrib.auth.hashers.BCryptPasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_THROTTLE_CLASSES': ()}  # noqa: F405
LOGGING = {'version': 1, 'disable_existing_loggers': False, 'root': {'handlers': [], 'level': 'CRITICAL'}}
