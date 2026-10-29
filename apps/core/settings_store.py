"""
Typed access to SiteSetting rows with the same defaults the legacy
config/app.php `_setting()` calls used — a missing row always resolves
to the documented default, never to None, so callers can do arithmetic
on the result directly.
"""
import json

from django.core.cache import cache

DEFAULTS = {
    'app_name': 'Safari-Ops',
    'deposit_percent': 25,
    'balance_days': 45,
    'vat_rate': 0.18,
    'service_charge_rate': 0.05,
    'default_commission_rate': 10,
    'quotation_validity_days': 14,
    'max_party_size': 60,
    'maintenance_mode': False,
    'agent_direct_booking_enabled': True,
    'auto_send_payment_emails': True,
    'session_timeout_minutes': 30,
    'site_email': 'info@safarizanguven.com',
    'admin_email': 'admin@safarizanguven.com',
    'whatsapp_number': '255663430934',
    'bank_name': 'ABSA Bank Tanzania',
    'bank_account_name': 'Safari Zangu Ventures Ltd',
    'bank_account_no': '',
    'bank_swift': 'BARCTZTZXXX',
    'wise_email': 'payments@safarizanguven.com',
    'emergency_contacts': {},
}

CACHE_KEY = 'site_settings:all'


def _coerce(raw, default):
    if isinstance(default, bool):
        return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')
    if isinstance(default, int):
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default
    if isinstance(default, (dict, list)):
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return default
    return raw


def _all():
    data = cache.get(CACHE_KEY)
    if data is None:
        from apps.core.models import SiteSetting
        data = dict(SiteSetting.objects.values_list('key', 'value'))
        cache.set(CACHE_KEY, data, 60)
    return data


def get_setting(key, default=None):
    fallback = DEFAULTS.get(key, default)
    raw = _all().get(key)
    if raw is None:
        return fallback
    return _coerce(raw, fallback) if fallback is not None else raw


def set_setting(key, value):
    from apps.core.models import SiteSetting
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    elif isinstance(value, bool):
        value = '1' if value else '0'
    SiteSetting.objects.update_or_create(key=key, defaults={'value': str(value)})
    cache.delete(CACHE_KEY)
