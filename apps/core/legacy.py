"""
Shared legacy-PHP → Django mapping used by both `import_legacy_data`
(fresh full import) and `sync_legacy_data` (idempotent top-up of an
already-imported database). Every function reads from the 'legacy'
connection with raw SQL and is safe to run more than once.
"""
import json
from decimal import Decimal

from django.db import connections

ROLE_MAP = {'superadmin': 'owner', 'admin': 'admin', 'staff': 'manager', 'agent': 'agent'}
THEME_MAP = {'light': 'light', 'dark': 'dark'}


def rows(table, columns='*'):
    with connections['legacy'].cursor() as cur:
        cur.execute(f'SELECT {columns} FROM `{table}`')
        cols = [c[0] for c in cur.description]
        for row in cur.fetchall():
            yield dict(zip(cols, row))


def table_exists(table):
    with connections['legacy'].cursor() as cur:
        cur.execute('SHOW TABLES LIKE %s', [table])
        return cur.fetchone() is not None


def jsonval(value, default):
    """PyMySQL's raw cursor returns MySQL JSON columns as text — decode them, never double-encode into a JSONField."""
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def dec(value, default='0'):
    return Decimal(str(value)) if value is not None else Decimal(default)


def legacy_password(php_hash):
    """
    PHP password_hash() bcrypt ('$2y$…') → Django's bcrypt hasher format.
    $2y$ and $2b$ are the same algorithm; the python bcrypt library verifies
    either. Verified against a real PHP-generated hash before adopting this.
    Returns None for anything that isn't a bcrypt hash.
    """
    if php_hash and php_hash.startswith(('$2y$', '$2b$', '$2a$')) and len(php_hash) == 60:
        return 'bcrypt$' + php_hash
    return None


def apply_user_fields(user, r, set_password=True):
    role = ROLE_MAP.get(r.get('role'), 'agent')
    user.email = r.get('email') or user.email
    user.first_name = (r.get('full_name') or user.first_name or '')[:150]
    user.role = role
    user.is_staff = role in ('owner', 'admin')
    user.is_active = bool(r.get('is_active', 1))
    user.phone = r.get('phone') or user.phone
    user.bio = r.get('bio') or user.bio
    user.commission_rate = dec(r['commission_rate']) if r.get('commission_rate') is not None else None
    user.target_monthly = dec(r.get('target_monthly'))
    user.can_change_status = bool(r.get('can_change_status', 1))
    user.can_delete_records = bool(r.get('can_delete_records', 0))
    user.theme_preference = THEME_MAP.get(r.get('theme_preference'), 'system')
    migrated = False
    if set_password and not user.has_usable_password():
        encoded = legacy_password(r.get('password_hash'))
        if encoded:
            user.password = encoded
            migrated = True
        else:
            user.set_unusable_password()
    return migrated


def import_settings(overwrite=True):
    from apps.core.models import SiteSetting
    n = 0
    for r in rows('settings'):
        key, value = r['key'], r.get('value') or ''
        if overwrite:
            SiteSetting.objects.update_or_create(key=key, defaults={'value': value})
        else:
            SiteSetting.objects.get_or_create(key=key, defaults={'value': value})
        n += 1
    from django.core.cache import cache
    from apps.core.settings_store import CACHE_KEY
    cache.delete(CACHE_KEY)
    return n


def import_currencies():
    from apps.core.models import CurrencyRate
    n = 0
    for r in rows('currency_rates'):
        CurrencyRate.objects.update_or_create(code=r['code'], defaults={
            'name': r['name'], 'symbol': r.get('symbol') or '', 'rate_to_usd': dec(r['rate_to_usd'], '1'),
            'is_active': bool(r.get('is_active', 1)),
        })
        n += 1
    return n


def import_suppliers():
    from apps.operations.models import Supplier
    n = 0
    for r in rows('suppliers'):
        Supplier.objects.update_or_create(name=r['name'], defaults={
            'category': r.get('category') or 'other', 'contact_person': r.get('contact_person') or '',
            'phone': r.get('phone') or '', 'email': r.get('email') or '', 'payment_terms': r.get('payment_terms') or '',
            'is_active': bool(r.get('is_active', 1)), 'notes': r.get('notes') or '',
        })
        n += 1
    return n


def import_staff():
    from apps.operations.models import StaffMember
    n = 0
    for r in rows('staff'):
        StaffMember.objects.update_or_create(full_name=r['full_name'], defaults={
            'role': r.get('role') or 'guide_driver', 'phone': r.get('phone') or '', 'email': r.get('email') or '',
            'languages': r.get('languages') or '', 'license_number': r.get('license_number') or '',
            'daily_rate': dec(r.get('daily_rate')), 'is_active': bool(r.get('is_active', 1)), 'notes': r.get('notes') or '',
        })
        n += 1
    return n


def import_reviews():
    from apps.content.models import Review
    from apps.crm.models import Customer
    email_by_legacy_id = {c['id']: (c['email'] or '').strip().lower() for c in rows('customers', 'id, email')}
    n = 0
    for r in rows('reviews'):
        email = email_by_legacy_id.get(r.get('customer_id'))
        customer = Customer.objects.filter(email=email).first() if email else None
        Review.objects.update_or_create(booking_ref=r['booking_ref'], guest_name=r['guest_name'], defaults={
            'customer': customer, 'guest_country': r.get('guest_country') or '',
            'rating': r.get('rating') or 5, 'nps_score': r.get('nps_score'), 'comment': r.get('comment') or '',
            'is_published': bool(r.get('is_published')),
        })
        n += 1
    return n


def import_incidents(user_by_legacy_id=None):
    from apps.operations.models import Incident
    user_by_legacy_id = user_by_legacy_id or {}
    n = 0
    for r in rows('incidents'):
        Incident.objects.get_or_create(
            booking_ref=r.get('booking_ref') or '', description=r['description'], occurred_at=r.get('occurred_at'),
            defaults={'incident_type': r.get('incident_type') or 'other', 'severity': r.get('severity') or 'medium',
                      'status': r.get('status') or 'open', 'resolution_notes': r.get('resolution_notes') or '',
                      'resolved_at': r.get('resolved_at'), 'reported_by': user_by_legacy_id.get(r.get('reported_by'))},
        )
        n += 1
    return n
