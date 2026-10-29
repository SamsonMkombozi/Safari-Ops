"""Line-icon set ported verbatim from the legacy App\\Helpers\\AdminIcon so both panels keep the same visual vocabulary."""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ICON_PATHS = {
    'dashboard': '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
    'analytics': '<line x1="4" y1="20" x2="20" y2="20"/><rect x="6" y="12" width="3" height="8"/><rect x="11" y="7" width="3" height="13"/><rect x="16" y="4" width="3" height="16"/>',
    'bookings': '<rect x="3" y="5" width="18" height="16" rx="1"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/><path d="M8 15l2.5 2.5L16 13"/>',
    'invoices': '<path d="M5 3h14v16l-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4V3Z"/><line x1="8" y1="8" x2="16" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/>',
    'customers': '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.6 2.7-6.2 6-6.2s6 2.6 6 6.2"/><circle cx="17.5" cy="9" r="2.3"/><path d="M15.8 14c2.4.4 4.2 2.4 4.2 6"/>',
    'requests': '<rect x="3" y="5" width="18" height="14" rx="1"/><path d="M3 13h5l2 3h4l2-3h5"/>',
    'messages': '<rect x="3" y="5" width="18" height="14" rx="1"/><path d="M3 6l9 7 9-7"/>',
    'leads': '<path d="M12 2L22 12 12 22 2 12Z"/>',
    'commissions': '<circle cx="12" cy="12" r="9"/><line x1="12" y1="7" x2="12" y2="17"/><path d="M15 9.3c0-1.4-1.5-2.1-3-2.1s-3 .7-3 2c0 1.3 1.3 1.7 3 2.1c1.7.4 3 .9 3 2.2s-1.5 2.4-3 2.4-3-.6-3-1.9"/>',
    'quotations': '<rect x="5" y="3" width="14" height="18" rx="1"/><line x1="8" y1="8" x2="16" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="16" x2="13" y2="16"/>',
    'email-template': '<rect x="3" y="4" width="18" height="16" rx="1"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="9" x2="9" y2="20"/>',
    'email-queue': '<path d="M3 11l18-8-8 18-2-8-8-2Z"/>',
    'reminders': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    'poster': '<rect x="3" y="4" width="18" height="14" rx="1"/><circle cx="8.5" cy="9.5" r="1.5"/><path d="M3 16l5-5 4 4 3-3 5 5"/>',
    'gallery': '<rect x="3" y="4" width="18" height="14" rx="1"/><circle cx="8" cy="9" r="1.5"/><path d="M3 15l4.5-4.5 3.5 3.5 4-4L21 15"/>',
    'itineraries': '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z"/><line x1="9" y1="4" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="20"/>',
    'packages': '<path d="M3 8l9-5 9 5-9 5-9-5Z"/><path d="M3 8v9l9 5 9-5V8"/><line x1="12" y1="13" x2="12" y2="22"/>',
    'plus': '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    'team': '<circle cx="7" cy="8" r="2.8"/><circle cx="17" cy="8" r="2.8"/><path d="M2 20c0-3.2 2.3-5.5 5-5.5s5 2.3 5 5.5"/><path d="M12 20c0-3.2 2.3-5.5 5-5.5s5 2.3 5 5.5"/>',
    'accommodations': '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
    'activities': '<path d="M12 2L14.8 9.3 22 9.3 16.2 14 18.4 21 12 16.8 5.6 21 7.8 14 2 9.3 9.2 9.3Z"/>',
    'fleet': '<rect x="1" y="7" width="13" height="9" rx="1"/><path d="M14 10h4l3 3v3h-7z"/><circle cx="6" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
    'park-fees': '<path d="M5 21C5 12 12 3 21 3c0 9-7 16-16 18Z"/><path d="M5 21c3-4 6-7 11-11"/>',
    'seasons': '<circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/><line x1="4.9" y1="4.9" x2="7" y2="7"/><line x1="17" y1="17" x2="19.1" y2="19.1"/><line x1="4.9" y1="19.1" x2="7" y2="17"/><line x1="17" y1="7" x2="19.1" y2="4.9"/>',
    'users': '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    'external-link': '<path d="M14 4h6v6"/><line x1="20" y1="4" x2="11" y2="13"/><path d="M19 14v6H5V6h6"/>',
    'key': '<circle cx="8" cy="8" r="4"/><line x1="11" y1="11" x2="21" y2="21"/><line x1="16.5" y1="15.5" x2="19.5" y2="12.5"/>',
    'logout': '<path d="M9 21H4V3h5"/><line x1="21" y1="12" x2="10" y2="12"/><path d="M16 7l5 5-5 5"/>',
    'close': '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
    'edit': '<path d="M4 20l1-4.5L15.5 5 19 8.5 8.5 19z"/><path d="M13.5 6.5l4 4"/>',
    'trash': '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    'check': '<path d="M4 12l5 5 11-11"/>',
    'alert': '<path d="M12 3l10 18H2Z"/><line x1="12" y1="9" x2="12" y2="14"/><circle cx="12" cy="17.2" r=".6" fill="currentColor" stroke="none"/>',
    'search': '<circle cx="10" cy="10" r="6.5"/><line x1="15" y1="15" x2="21" y2="21"/>',
    'refresh': '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>',
    'chevron-down': '<path d="M6 9l6 6 6-6"/>',
    'eye': '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="2.5"/>',
    'filter': '<path d="M4 5h16l-6 8v6l-4 2v-8Z"/>',
    'download': '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="1"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/>',
    'guide': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.4"/><line x1="12" y1="3" x2="12" y2="7"/><line x1="12" y1="17" x2="12" y2="21"/><line x1="3" y1="12" x2="7" y2="12"/><line x1="17" y1="12" x2="21" y2="12"/>',
    'currency': '<circle cx="12" cy="12" r="9"/><path d="M12 6v12M9 9.5c0-1.4 1.3-2.5 3-2.5s3 .9 3 2.2-1.3 1.9-3 2.3-3 1-3 2.3S10.6 16 12 16s3-.8 3-2.2"/>',
    'star': '<path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6-5.9-3.3-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8Z"/>',
    'suppliers': '<path d="M3 9l9-6 9 6"/><path d="M5 9v10h14V9"/><line x1="9" y1="21" x2="9" y2="13"/><line x1="15" y1="21" x2="15" y2="13"/>',
    'inventory': '<rect x="3" y="7" width="18" height="14" rx="1"/><path d="M3 7l2-4h14l2 4"/><line x1="9" y1="11" x2="15" y2="11"/>',
    'incident': '<path d="M4 3v18"/><path d="M4 4h13l-3 4 3 4H4"/>',
    'trending': '<polyline points="3,17 9,11 13,15 21,6"/><polyline points="15,6 21,6 21,12"/>',
    'target': '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/>',
    'bell': '<path d="M6 8a6 6 0 0 1 12 0c0 5.2 1.5 7.4 2.2 8.3.3.4 0 1-.5 1H4.3c-.5 0-.8-.6-.5-1C4.5 15.4 6 13.2 6 8Z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    'moon': '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z"/>',
    'dots-vertical': '<circle cx="12" cy="5" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="19" r="1.4" fill="currentColor" stroke="none"/>',
}


@register.simple_tag
def icon(name, size=15):
    paths = ICON_PATHS.get(name, ICON_PATHS.get("dashboard", ""))
    return mark_safe(
        f'<svg class="admin-icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths}</svg>'
    )


STATUS_COLORS = {
    # bookings
    'pending': 'amber', 'deposit_paid': 'blue', 'fully_paid': 'green', 'cancelled': 'red',
    # quotations
    'draft': 'gray', 'sent': 'blue', 'viewed': 'purple', 'accepted': 'green', 'declined': 'red',
    'expired': 'gray', 'converted': 'green',
    # leads
    'lead': 'gray', 'qualified': 'blue', 'quoted': 'purple', 'negotiation': 'amber', 'booked': 'green',
    'travelled': 'dark', 'completed': 'green', 'lost': 'red',
    # commissions / requests / misc
    'approved': 'blue', 'paid': 'green', 'new': 'amber', 'in_review': 'blue', 'closed': 'gray',
    'open': 'red', 'resolved': 'green', 'failed': 'red', 'low': 'gray', 'medium': 'amber',
    'high': 'red', 'critical': 'red',
}


@register.simple_tag
def status_badge(value, label=None):
    color = STATUS_COLORS.get(str(value), 'gray')
    text = label or str(value or '—').replace('_', ' ')
    from django.utils.html import escape
    return mark_safe(f'<span class="badge-status badge-status--{color}">{escape(text)}</span>')


@register.filter
def money(value, decimals=0):
    try:
        return f'${float(value or 0):,.{int(decimals)}f}'
    except (TypeError, ValueError):
        return '$0'


@register.filter
def initials(user):
    name = (user.get_full_name() or user.username or 'A').split()
    return ''.join(p[0].upper() for p in name[:2])


@register.simple_tag(takes_context=True)
def qs_replace(context, **kwargs):
    """Rebuild the current query string with some keys changed — used by filter pills and pagination so they don't drop each other's params."""
    params = context['request'].GET.copy()
    for k, v in kwargs.items():
        if v in (None, ''):
            params.pop(k, None)
        else:
            params[k] = v
    params.pop('page', None) if 'page' not in kwargs else None
    encoded = params.urlencode()
    return f'?{encoded}' if encoded else '?'


@register.filter
def get_attr(obj, name):
    """Resolve a dotted attribute path on a model instance for the generic CRUD list template, preferring get_FOO_display for choice fields."""
    value = obj
    for part in str(name).split('.'):
        if isinstance(value, dict):
            value = value.get(part)
            if value is None:
                return ''
            continue
        display = getattr(value, f'get_{part}_display', None)
        value = display() if callable(display) else getattr(value, part, '')
        if callable(value):
            value = value()
        if value is None:
            return ''
    return value


@register.filter
def split_pairs(value):
    """'a|A,b|B' → [('a','A'), ('b','B')] — static filter-pill lists inline in a template."""
    return [tuple(part.split('|', 1)) for part in value.split(',')]


@register.filter
def raw_attr(obj, name):
    """The stored value (not the display label) — status_badge picks its colour from the raw choice key."""
    return getattr(obj, name, '')
