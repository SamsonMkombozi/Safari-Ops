from django.conf import settings

from apps.core.settings_store import get_setting


THEME_OPTIONS = [
    ('system', 'Match my device'), ('light', 'Light'), ('dark', 'Dark'), ('mono', 'Black & white'),
]


def site_meta(request):
    """Common template context every dashboard/agent-portal page needs — avoids repeating these lookups in every single view."""
    return {
        'SITE_NAME': get_setting('app_name'),
        'WHATSAPP_NUMBER': get_setting('whatsapp_number'),
        'DEBUG': settings.DEBUG,
        'theme_options': THEME_OPTIONS,
    }
