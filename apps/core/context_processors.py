from django.conf import settings


def site_meta(request):
    """Common template context every dashboard/agent-portal page needs — avoids repeating these lookups in every single view."""
    return {
        'SITE_NAME': 'Safari Zangu Ventures',
        'WHATSAPP_NUMBER': getattr(settings, 'WHATSAPP_NUMBER', ''),
        'DEBUG': settings.DEBUG,
    }
