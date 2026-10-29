"""
Itinerary → itemised quote pricing. A direct port of the legacy
App\\Services\\ItineraryQuoteBuilder (build() + totals()) — same grouping
rules, same occupancy model, same line-item shape — so a quotation priced
here prints identically to one the PHP app priced.

Line items are plain dicts: description, unit_price, quantity_str,
amount, category (accommodation | transport | park_fee | activity |
other | service_fee). Everything except service_fee is supplier cost.
"""
from datetime import date

from apps.core.settings_store import get_setting

EAC_RESIDENT_COUNTRIES = {'tanzania', 'kenya', 'uganda', 'rwanda', 'burundi'}
SUPPLIER_CATEGORIES = ('accommodation', 'transport', 'park_fee', 'activity', 'other')


def _f(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _plural(n, one, many=None):
    return one if n == 1 else (many or one + 's')


class _Lookups:
    """Per-build cache of the rate columns the itinerary day JSON doesn't snapshot (child/resident/vehicle park fees, accommodation extras, vehicle components)."""

    def __init__(self):
        self._park, self._acc, self._veh = {}, {}, {}

    def park(self, name):
        if name not in self._park:
            from apps.packages.models import ParkFee
            row = ParkFee.objects.filter(name=name).values('child_fee', 'resident_adult', 'resident_child', 'vehicle_fee').first() or {}
            self._park[name] = {k: _f(row.get(k)) for k in ('child_fee', 'resident_adult', 'resident_child', 'vehicle_fee')}
        return self._park[name]

    def accommodation(self, name):
        if name not in self._acc:
            from apps.packages.models import Accommodation
            row = Accommodation.objects.filter(name=name).values('single_supplement', 'child_rate', 'rate_per_person').first() or {}
            self._acc[name] = {k: _f(row.get(k)) for k in ('single_supplement', 'child_rate', 'rate_per_person')}
        return self._acc[name]

    def vehicle(self, name):
        if name not in self._veh:
            from apps.packages.models import Vehicle
            row = Vehicle.objects.filter(name=name).values('daily_rate', 'fuel_cost_day', 'driver_cost_day').first() or {}
            self._veh[name] = {k: _f(row.get(k)) for k in ('daily_rate', 'fuel_cost_day', 'driver_cost_day')}
        return self._veh[name]


def build(days, adults, children=0, include_service_fee=True, nationality=None, service_fee_rates=None):
    """Price an itinerary's `days` JSON for a party. Returns line_items plus the descriptive extras (day titles, included/optional activities)."""
    adults = max(1, int(adults or 1))
    children = max(0, int(children or 0))
    pax = adults + children
    days = days or []
    service_fee_rates = service_fee_rates or {}
    is_resident = bool(nationality) and nationality.strip().lower() in EAC_RESIDENT_COUNTRIES
    lk = _Lookups()

    acc_groups, veh_groups, park_groups = {}, {}, {}
    act_paid, act_free, other_items = [], [], []
    meals_total, meals_days = 0.0, 0

    # ── Step 1: aggregate resources across all days ──
    for day in days:
        day_num = day.get('day', '?')

        acc_name = (day.get('accommodation_name') or '').strip()
        acc_rate = _f(day.get('accommodation_rate'))
        if acc_name and acc_rate > 0:
            g = acc_groups.setdefault(acc_name, {'name': acc_name, 'rate': acc_rate,
                                                 'rooms': int(day.get('accommodation_rooms') or 1), 'nights': 0})
            g['nights'] += 1

        veh_name = (day.get('vehicle_name') or '').strip()
        veh_rate = _f(day.get('vehicle_rate'))
        if veh_name and veh_rate > 0:
            veh_groups.setdefault(veh_name, {'name': veh_name, 'rate': veh_rate, 'days': 0})['days'] += 1

        park_name = (day.get('park_fee_name') or '').strip()
        park_fee = _f(day.get('park_adult_fee'))
        if park_name and park_fee > 0:
            if park_name not in park_groups:
                rates = lk.park(park_name)
                resident = is_resident and rates['resident_adult'] > 0
                park_groups[park_name] = {
                    'name': park_name,
                    'fee': rates['resident_adult'] if resident else park_fee,
                    'child_fee': rates['resident_child'] if resident and rates['resident_child'] > 0 else rates['child_fee'],
                    'vehicle_fee': rates['vehicle_fee'], 'entries': 0, 'resident': resident,
                }
            park_groups[park_name]['entries'] += 1

        for act in day.get('activities') or []:
            name = (act.get('name') or '').strip()
            if not name or act.get('type', 'included') == 'optional':
                continue
            price = _f(act.get('price_pp'))
            qty = max(1, int(act['qty'])) if act.get('qty') not in (None, '') else pax
            if price > 0:
                act_paid.append({'name': name, 'price': price, 'qty': qty})
            else:
                act_free.append(name)

        meals = _f(day.get('meals_cost_pp'))
        if meals > 0:
            meals_total += meals
            meals_days += 1

        for ot in day.get('other_items') or []:
            name = (ot.get('name') or '').strip()
            amt = _f(ot.get('amount'))
            if not name or amt <= 0:
                continue
            if 'per_pax' in ot:
                per_pax = bool(ot['per_pax'])
            else:
                low = name.lower()
                per_pax = any(w in low for w in ('transfer', 'water', 'contribution'))
            qty = max(1, int(ot['qty'])) if ot.get('qty') not in (None, '') else 1
            existing = next((o for o in other_items if o['name'] == name), None)
            if existing:
                existing['qty'] += qty
            else:
                other_items.append({'name': name, 'unit_price': amt, 'qty': qty,
                                    'unit_name': (ot.get('unit') or '').strip(), 'per_pax': per_pax})

    # ── Step 2: line items ──
    items = []

    def add(desc, unit, qty_str, amount, cat):
        items.append({'description': desc, 'unit_price': round(unit, 2), 'quantity_str': qty_str,
                      'amount': round(amount, 2), 'category': cat})

    for acc in acc_groups.values():
        n = acc['nights']
        nights = f'{n} {_plural(n, "Night")}'
        extras = lk.accommodation(acc['name'])
        if extras['rate_per_person'] > 0:
            # Per-person-sharing: adults pair into rooms, an odd adult pays the single supplement.
            rate = extras['rate_per_person']
            solo = adults % 2
            rooms_used = adults // 2 + solo
            add(f'Accommodation – {acc["name"]} (Per Person Sharing)', rate,
                f'{adults} {_plural(adults, "Adult")} × {nights} ({rooms_used} {_plural(rooms_used, "Room")})',
                rate * adults * n, 'accommodation')
            if solo and extras['single_supplement'] > 0:
                add(f'Single Supplement – {acc["name"]}', extras['single_supplement'], f'1 Guest × {nights}',
                    extras['single_supplement'] * n, 'accommodation')
        else:
            r = acc['rooms']
            qty_str = f'{r} Rooms × {nights}' if r > 1 else nights
            add(f'Accommodation – {acc["name"]}', acc['rate'], qty_str, acc['rate'] * n * r, 'accommodation')
            if adults == 1 and extras['single_supplement'] > 0:
                add(f'Single Supplement – {acc["name"]}', extras['single_supplement'], qty_str,
                    extras['single_supplement'] * n * r, 'accommodation')
        if children and extras['child_rate'] > 0:
            add(f'Child Rate – {acc["name"]}', extras['child_rate'],
                f'{children} {_plural(children, "Child", "Children")} × {nights}',
                extras['child_rate'] * children * n, 'accommodation')

    for veh in veh_groups.values():
        d = veh['days']
        day_str = f'1 Vehicle × {d} {_plural(d, "Day")}'
        comp = lk.vehicle(veh['name'])
        db_total = comp['daily_rate'] + comp['fuel_cost_day'] + comp['driver_cost_day']
        if db_total > 0 and abs(db_total - veh['rate']) < 0.01:
            for field, desc in (('daily_rate', veh['name']), ('fuel_cost_day', f'Fuel — {veh["name"]}'),
                                ('driver_cost_day', f'Driver Allowance — {veh["name"]}')):
                if comp[field] > 0:
                    add(desc, comp[field], day_str, comp[field] * d, 'transport')
        else:
            add(f'{veh["name"]} & Fuel', veh['rate'], day_str, veh['rate'] * d, 'transport')

    for park in park_groups.values():
        e = park['entries']
        guests = f'{adults} {_plural(adults, "Adult")}' + (
            f' + {children} {_plural(children, "Child", "Children")}' if children else '')
        add(f'{park["name"]} Entry Fees' + (' (Resident Rate)' if park['resident'] else ''), park['fee'],
            f'{guests} × {e} Days' if e > 1 else guests,
            (park['fee'] * adults + park['child_fee'] * children) * e, 'park_fee')
        if park['vehicle_fee'] > 0:
            add(f'{park["name"]} Vehicle Entry Fee', park['vehicle_fee'], f'{e} Days' if e > 1 else '1 Vehicle',
                park['vehicle_fee'] * e, 'park_fee')

    consolidated = {}
    for act in act_paid:
        c = consolidated.setdefault(act['name'], {'price': act['price'], 'qty': 0, 'days': 0})
        c['qty'] += act['qty']
        c['days'] += 1
    for name, c in consolidated.items():
        add(name, c['price'], f'{c["qty"]} {_plural(c["qty"], "Guest")}' + (f' × {c["days"]} Days' if c['days'] > 1 else ''),
            c['price'] * c['qty'], 'activity')

    if meals_total > 0:
        add(f'Meals (Full Board — {meals_days} {_plural(meals_days, "day")})', meals_total / max(1, meals_days),
            f'{pax} Guests × {meals_days} Days', meals_total * pax, 'activity')

    for ot in other_items:
        total_qty = ot['qty'] * pax if ot['per_pax'] else ot['qty']
        unit_label = ot['unit_name'] or _plural(ot['qty'], 'Unit')
        if ot['per_pax']:
            qty_str = f'{pax} {_plural(pax, "Guest")}' + (f' × {ot["qty"]} {unit_label}' if ot['qty'] > 1 else '')
        else:
            qty_str = f'{ot["qty"]} {unit_label}'
        add(ot['name'], ot['unit_price'], qty_str, ot['unit_price'] * total_qty, 'other')

    has_service_fee = any(
        li['category'] == 'service_fee' or any(k in li['description'].lower() for k in ('service charge', 'service fee', 'guide fee'))
        for li in items
    )
    if include_service_fee and not has_service_fee:
        adult_rate = _f(service_fee_rates.get('adult', 100))
        child_rate = _f(service_fee_rates.get('child', 100))
        add('Service Charge (Adults)', adult_rate, f'{adults} {_plural(adults, "Adult")}', adult_rate * adults, 'service_fee')
        if children:
            add('Service Charge (Children)', child_rate, f'{children} {_plural(children, "Child", "Children")}',
                child_rate * children, 'service_fee')

    optional = [
        {'name': a['name'], 'price': _f(a.get('price_pp')), 'day': d.get('day', '')}
        for d in days for a in (d.get('activities') or [])
        if a.get('type') == 'optional' and a.get('name')
    ]
    included = list(dict.fromkeys(act_free))
    return {
        'line_items': items,
        'day_titles': [{'day': d.get('day', ''), 'title': d.get('title', ''), 'location': d.get('location', ''),
                        'accommodation': d.get('accommodation_name', ''), 'park': d.get('park_fee_name', '')} for d in days],
        'optional_activities': optional,
        'included_activities': included,
        'notes_suggestion': f'Included activities: {", ".join(included)}' if included else '',
        'pax': pax, 'adults': adults, 'children': children,
    }


def totals(line_items, discount_pct=0, markup_pct=0):
    """subtotal → markup → discount → VAT → grand total → deposit, with VAT and deposit % from site settings."""
    subtotal = sum(_f(li.get('amount')) for li in line_items)
    markup = subtotal * _f(markup_pct) / 100
    marked = subtotal + markup
    discount = marked * _f(discount_pct) / 100
    after = marked - discount
    vat = round(after * _f(get_setting('vat_rate')), 2)
    grand = round(after + vat, 2)
    deposit = round(grand * _f(get_setting('deposit_percent')) / 100, 2)
    return {
        'subtotal': round(subtotal, 2), 'markup': round(markup, 2), 'discount': round(discount, 2),
        'vat': vat, 'grand_total': grand, 'deposit': deposit, 'balance': round(grand - deposit, 2),
    }


def supplier_cost(line_items):
    return round(sum(_f(li.get('amount')) for li in line_items if li.get('category') in SUPPLIER_CATEGORIES), 2)


def service_fee_rates_for(package):
    cb = (package.cost_breakdown or {}) if package else {}
    fallback = cb.get('service_charge_pax', 100)
    return {'adult': _f(cb.get('service_charge_adult', fallback)), 'child': _f(cb.get('service_charge_child', fallback))}


def detect_season(d: date) -> str:
    if d.month in (6, 7, 8, 9, 10) or (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 5):
        return 'peak'
    if d.month in (3, 4, 5):
        return 'shoulder'
    return 'low'


def price_package(package, adults, children=0, nationality=None, markup_pct=0, discount_pct=0):
    """Full price for a package + party: itemised when the package has an itinerary, else the flat price_1pax × travelers fallback api/book.php used."""
    if package.itinerary_id and package.itinerary and package.itinerary.days:
        built = build(package.itinerary.days, adults, children, True, nationality, service_fee_rates_for(package))
        t = totals(built['line_items'], discount_pct, markup_pct)
        return built, t
    travelers = max(1, int(adults or 1)) + max(0, int(children or 0))
    total = round(_f(package.price_1pax) * travelers, 2)
    deposit = round(total * _f(get_setting('deposit_percent')) / 100, 2)
    item = {'description': package.name, 'unit_price': _f(package.price_1pax), 'quantity_str': f'{travelers} {_plural(travelers, "Guest")}',
            'amount': total, 'category': 'other'}
    built = {'line_items': [item], 'day_titles': [], 'optional_activities': [], 'included_activities': [],
             'notes_suggestion': '', 'pax': travelers, 'adults': adults, 'children': children}
    vat_rate = _f(get_setting('vat_rate'))
    return built, {'subtotal': round(total / (1 + vat_rate), 2), 'markup': 0, 'discount': 0,
                   'vat': round(total - total / (1 + vat_rate), 2), 'grand_total': total,
                   'deposit': deposit, 'balance': round(total - deposit, 2)}
