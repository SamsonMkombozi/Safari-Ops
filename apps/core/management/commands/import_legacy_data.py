"""
One-time import from the legacy PHP app's MySQL database (the 'legacy'
connection alias — see config/settings/base.py and apps/core/db_routers)
into this project's own Django-native schema.

Password hashes ARE migrated: the legacy app's PHP password_hash()
bcrypt ('$2y$') hashes are wrapped for Django's BCryptPasswordHasher
(see apps.core.legacy.legacy_password — verified against a real
PHP-generated hash), so users keep their passwords and Django upgrades
each one to PBKDF2 on first login. Anything that isn't a bcrypt hash gets
an unusable password and must use "Forgot your password?".
Run with --dry-run first to see counts before writing anything.

Usage:
    python manage.py import_legacy_data --dry-run   # count rows, write nothing
    python manage.py import_legacy_data              # actually import
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connections, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import pricing
from apps.bookings.models import Booking, BookingReminder, Payment, Quotation
from apps.content.models import ContactMessage, CustomSafariRequest, EmailTemplate, TeamMember
from apps.core import legacy
from apps.core.legacy import dec, jsonval, rows
from apps.crm.models import AgentTarget, Commission, Customer, Lead
from apps.packages.models import Accommodation, Activity, Itinerary, Package, ParkFee, SeasonalRate, Vehicle


class Command(BaseCommand):
    help = 'One-time import of data from the legacy PHP app MySQL database.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Count legacy rows per table without writing anything.')

    def handle(self, *args, **options):
        if options['dry_run']:
            self._dry_run()
            return

        with transaction.atomic():
            user_by_legacy_id = self._import_users()
            itin_by_legacy_id, pkg_by_legacy_id = self._import_catalog()
            customer_by_email = self._import_customers()
            lead_by_legacy_id = self._import_leads(user_by_legacy_id, customer_by_email)
            self._import_commissions(user_by_legacy_id, lead_by_legacy_id)
            self._import_agent_targets(user_by_legacy_id)
            request_by_legacy_id = self._import_custom_safari_requests(customer_by_email, user_by_legacy_id)
            quote_by_legacy_id = self._import_quotations(customer_by_email, pkg_by_legacy_id, itin_by_legacy_id,
                                                         user_by_legacy_id, lead_by_legacy_id, request_by_legacy_id)
            self._import_bookings(customer_by_email, quote_by_legacy_id, pkg_by_legacy_id, itin_by_legacy_id)
            self._import_booking_reminders()
            self._import_team_members()
            self._import_contact_messages()
            self._import_email_templates()
            self.stdout.write(f'Settings: {legacy.import_settings()}, currencies: {legacy.import_currencies()}, '
                              f'suppliers: {legacy.import_suppliers()}, staff: {legacy.import_staff()}, '
                              f'reviews: {legacy.import_reviews()}, incidents: {legacy.import_incidents(user_by_legacy_id)}')

        self.stdout.write(self.style.WARNING(
            '\nUsers keep their legacy passwords where the hash was bcrypt; any without one must use "Forgot your password?".'
        ))
        self.stdout.write(self.style.SUCCESS('Import complete.'))

    def _dry_run(self):
        tables = [
            'admin_users', 'accommodations', 'vehicles', 'park_fees', 'activities', 'seasonal_rates',
            'itineraries', 'packages', 'customers', 'leads', 'commissions', 'agent_targets',
            'quotations', 'bookings', 'booking_reminders', 'team_members', 'contact_messages',
            'custom_safari_requests', 'email_templates', 'settings', 'currency_rates', 'suppliers', 'staff',
            'reviews', 'incidents',
        ]
        with connections['legacy'].cursor() as cur:
            for table in tables:
                cur.execute(f'SELECT COUNT(*) FROM `{table}`')
                self.stdout.write(f'{table:30s} {cur.fetchone()[0]}')

    # ── Accounts ───────────────────────────────────────────────
    def _import_users(self):
        mapping = {}
        count = 0
        for r in rows('admin_users'):
            user = User(username=r['username'])
            user.set_unusable_password()
            legacy.apply_user_fields(user, r)
            user.save()
            mapping[r['id']] = user
            count += 1
        self.stdout.write(f'Users: {count}')
        return mapping

    # ── Catalog ────────────────────────────────────────────────
    def _import_catalog(self):
        n = 0
        for r in rows('accommodations'):
            Accommodation.objects.create(
                name=r['name'], level=r.get('level') or 'midrange', category=r.get('category') or '',
                location=r.get('location') or '', park_key=r.get('park_key') or '',
                rate_per_room=dec(r.get('rate_per_room')), rate_per_person=dec(r.get('rate_per_person')),
                rate_low=dec(r['rate_low']) if r.get('rate_low') is not None else None,
                rate_high=dec(r['rate_high']) if r.get('rate_high') is not None else None,
                single_supplement=dec(r.get('single_supplement')), child_rate=dec(r.get('child_rate')),
                meal_plan=r.get('meal_plan') or 'fb', is_active=bool(r.get('is_active', 1)), notes=r.get('notes') or '',
                images=jsonval(r.get('images_json'), []),
            )
            n += 1
        self.stdout.write(f'Accommodations: {n}')

        n = 0
        for r in rows('vehicles'):
            Vehicle.objects.create(
                vehicle_key=r['vehicle_key'], name=r['name'], capacity=r.get('capacity') or 6,
                daily_rate=dec(r.get('daily_rate')), fuel_cost_day=dec(r.get('fuel_cost_day')),
                driver_cost_day=dec(r.get('driver_cost_day')), level=r.get('level') or 'standard',
                is_active=bool(r.get('is_active', 1)), images=jsonval(r.get('images_json'), []),
            )
            n += 1
        self.stdout.write(f'Vehicles: {n}')

        n = 0
        for r in rows('park_fees'):
            ParkFee.objects.create(
                park_key=r['park_key'], name=r['name'], country=r.get('country') or 'Tanzania',
                adult_fee=dec(r.get('adult_fee')), child_fee=dec(r.get('child_fee')),
                resident_adult=dec(r.get('resident_adult')), resident_child=dec(r.get('resident_child')),
                fee_unit=r.get('fee_unit') or 'per_person_per_entry', is_active=bool(r.get('is_active', 1)),
                notes=r.get('notes') or '',
            )
            n += 1
        self.stdout.write(f'Park fees: {n}')

        n = 0
        for r in rows('activities'):
            Activity.objects.create(
                activity_key=r['activity_key'], name=r['name'], description=r.get('description') or '',
                price=dec(r.get('price')), price_unit=r.get('price_unit') or 'per_person',
                category=r.get('category') or '', is_active=bool(r.get('is_active', 1)),
            )
            n += 1
        self.stdout.write(f'Activities: {n}')

        n = 0
        for r in rows('seasonal_rates'):
            SeasonalRate.objects.create(
                name=r['name'], season_key=r['season_key'], multiplier=dec(r.get('multiplier'), '1'),
                start_month=r.get('start_month'), end_month=r.get('end_month'), description=r.get('description') or '',
            )
            n += 1
        self.stdout.write(f'Seasonal rates: {n}')

        itin_map = {}
        n = 0
        for r in rows('itineraries'):
            itin = Itinerary.objects.create(
                name=r['name'], slug=r['slug'], duration_days=r.get('duration_days') or 5,
                overview=r.get('overview') or '', accommodation_level=r.get('accommodation_level') or 'midrange',
                days=jsonval(r.get('days'), []), includes=jsonval(r.get('includes'), []), excludes=jsonval(r.get('excludes'), []),
                base_price_pax=dec(r.get('base_price_pax')), is_active=bool(r.get('is_active', 1)),
                sort_order=r.get('sort_order') or 0,
            )
            itin_map[r['id']] = itin
            n += 1
        self.stdout.write(f'Itineraries: {n}')

        pkg_map = {}
        n = 0
        for r in rows('packages'):
            pkg = Package.objects.create(
                slug=r['slug'], name=r['name'], duration_days=r.get('duration_days') or 1,
                short_description=r.get('short_description') or '', overview=r.get('overview') or '',
                itinerary=itin_map.get(r.get('itinerary_id')), accommodation_level=r.get('accommodation_level') or '',
                includes=jsonval(r.get('includes'), []), excludes=jsonval(r.get('excludes'), []),
                cost_breakdown=jsonval(r.get('cost_breakdown'), {}), price_notes=r.get('price_notes') or '',
                price_1pax=dec(r.get('price_1pax')), hero_image=r.get('hero_image') or '',
                gallery_images=jsonval(r.get('gallery_images'), []), is_featured=bool(r.get('is_featured', 1)),
                is_active=bool(r.get('is_active', 1)), sort_order=r.get('sort_order') or 0,
            )
            pkg_map[r['id']] = pkg
            n += 1
        self.stdout.write(f'Packages: {n}')
        return itin_map, pkg_map

    # ── CRM ────────────────────────────────────────────────────
    def _import_customers(self):
        mapping = {}
        n = 0
        for r in rows('customers'):
            customer = Customer.objects.create(
                full_name=r['full_name'], email=r['email'], phone=r.get('phone') or '', country=r.get('country') or '',
            )
            mapping[r['email'].strip().lower()] = customer
            n += 1
        self.stdout.write(f'Customers: {n}')
        return mapping

    def _import_leads(self, user_by_legacy_id, customer_by_email):
        mapping = {}
        n = 0
        for r in rows('leads'):
            customer = customer_by_email.get((r.get('email') or '').strip().lower())
            mapping[r['id']] = Lead.objects.create(
                full_name=r['full_name'], email=r['email'], phone=r.get('phone') or '', country=r.get('country') or '',
                source=r.get('source') or 'website', pipeline_stage=r.get('pipeline_stage') or 'lead',
                budget_range=r.get('budget_range') or '', travel_date=r.get('travel_date'),
                travel_month=r.get('travel_month') or '', party_size=r.get('party_size'),
                destinations=r.get('destinations') or '', package_name=r.get('package_name') or '',
                notes=r.get('notes') or '', score=r.get('score') or 0, booking_value=dec(r.get('booking_value')),
                commission_rate=dec(r['commission_rate']) if r.get('commission_rate') is not None else None,
                commission_amount=dec(r.get('commission_amount')), commission_status=r.get('commission_status') or 'pending',
                booking_ref=r.get('booking_ref') or '', converted_at=r.get('converted_at'),
                agent=user_by_legacy_id.get(r.get('agent_id')), assigned_to=user_by_legacy_id.get(r.get('assigned_to')),
                customer=customer, last_contact=r.get('last_contact'), next_follow_up=r.get('next_follow_up'),
            )
            n += 1
        self.stdout.write(f'Leads: {n}')
        return mapping

    def _import_commissions(self, user_by_legacy_id, lead_by_legacy_id):
        n = 0
        for r in rows('commissions'):
            agent = user_by_legacy_id.get(r['agent_id'])
            if not agent:
                continue  # orphaned row with no matching agent — skip rather than crash the whole import
            Commission.objects.create(
                agent=agent, lead=lead_by_legacy_id.get(r.get('lead_id')),
                booking_ref=r.get('booking_ref') or '', client_name=r.get('client_name') or '',
                package_name=r.get('package_name') or '', booking_value=dec(r.get('booking_value')),
                commission_rate=dec(r.get('commission_rate'), '10'), commission_amount=dec(r.get('commission_amount')),
                status=r.get('status') or 'pending', travel_date=r.get('travel_date'), notes=r.get('notes') or '',
                approved_by=user_by_legacy_id.get(r.get('approved_by')), approved_at=r.get('approved_at'),
                paid_at=r.get('paid_at'),
            )
            n += 1
        self.stdout.write(f'Commissions: {n}')

    def _import_agent_targets(self, user_by_legacy_id):
        n = 0
        for r in rows('agent_targets'):
            agent = user_by_legacy_id.get(r['agent_id'])
            if not agent:
                continue
            AgentTarget.objects.create(
                agent=agent, month=r['month'], target_leads=r.get('target_leads') or 0,
                target_bookings=r.get('target_bookings') or 0, target_value=dec(r.get('target_value')),
                actual_leads=r.get('actual_leads') or 0, actual_bookings=r.get('actual_bookings') or 0,
                actual_value=dec(r.get('actual_value')),
            )
            n += 1
        self.stdout.write(f'Agent targets: {n}')

    # ── Bookings & Quotations ──────────────────────────────────
    def _import_quotations(self, customer_by_email, pkg_by_legacy_id, itin_by_legacy_id,
                           user_by_legacy_id, lead_by_legacy_id, request_by_legacy_id):
        mapping = {}
        n = 0
        for r in rows('quotations'):
            customer = customer_by_email.get((r.get('client_email') or '').strip().lower())
            quote = Quotation.objects.create(
                quote_ref=r['quote_ref'], customer=customer, package=pkg_by_legacy_id.get(r.get('package_id')),
                itinerary=itin_by_legacy_id.get(r.get('itinerary_id')), package_name=r.get('package_name') or '',
                park_fees_total=dec(r.get('park_fees_total')), vehicle_total=dec(r.get('vehicle_total')),
                activities_total=dec(r.get('activities_total')), accommodation_total=dec(r.get('accommodation_total')),
                flight_cost=dec(r.get('flight_cost')), discount_pct=dec(r.get('discount_pct')),
                discount_amount=dec(r.get('discount_amount')), version=r.get('version') or 1,
                client_name=r['client_name'], client_email=r['client_email'], client_phone=r.get('client_phone') or '',
                client_country=r.get('client_country') or '', expedition_type=r.get('expedition_type') or 'safari',
                adults=r.get('adults') or 2, children=r.get('children') or 0, infants=r.get('infants') or 0,
                rooms=r.get('rooms') or 1, duration_days=r.get('duration_days') or 5, start_date=r.get('start_date'),
                destinations=jsonval(r.get('destinations'), []), accommodation_level=r.get('accommodation_level') or 'midrange',
                meal_plan=r.get('meal_plan') or 'fb', guide_language=r.get('guide_language') or 'english',
                activities=jsonval(r.get('activities'), []), internal_flight=bool(r.get('internal_flight')),
                season=r.get('season') or 'peak', line_items=jsonval(r.get('line_items'), []),
                subtotal=dec(r.get('subtotal')), service_charge=dec(r.get('service_charge')), vat=dec(r.get('vat')),
                grand_total=dec(r.get('grand_total')), per_person=dec(r.get('per_person')),
                deposit_amount=dec(r.get('deposit_amount')), balance_due=dec(r.get('balance_due')),
                currency=r.get('currency') or 'USD', status=r.get('status') or 'draft', valid_until=r.get('valid_until'),
                booking_ref=r.get('booking_ref') or '', notes=r.get('notes') or '', admin_notes=r.get('admin_notes') or '',
                sent_at=r.get('sent_at'), accepted_at=r.get('accepted_at'),
                created_by=user_by_legacy_id.get(r.get('created_by')), lead=lead_by_legacy_id.get(r.get('lead_id')),
                custom_request=request_by_legacy_id.get(r.get('custom_request_id')), markup_pct=dec(r.get('markup_pct')),
                view_count=r.get('view_count') or 0, first_viewed_at=r.get('first_viewed_at'), last_viewed_at=r.get('last_viewed_at'),
            )
            token = r.get('public_token') or ''
            if len(token) == 48:  # keep already-emailed client links working
                Quotation.objects.filter(pk=quote.pk).update(public_token=token)
            mapping[r['id']] = quote
            n += 1
        self.stdout.write(f'Quotations: {n}')
        return mapping

    def _import_bookings(self, customer_by_email, quote_by_legacy_id, pkg_by_legacy_id, itin_by_legacy_id):
        n = 0
        for r in rows('bookings'):
            customer = customer_by_email.get((r.get('email') or '').strip().lower())
            quote = quote_by_legacy_id.get(r.get('quotation_id'))
            booking = Booking.objects.create(
                booking_ref=r['booking_ref'], quotation=quote, customer=customer,
                package=pkg_by_legacy_id.get(r.get('package_id')), itinerary=itin_by_legacy_id.get(r.get('itinerary_id')),
                full_name=r['full_name'], email=r['email'], phone=r['phone'], country=r.get('country') or '',
                rooms=r.get('rooms') or 1, airport_pickup=bool(r.get('airport_pickup')), trip_extension=r.get('trip_extension') or '',
                supplier_cost=dec(pricing.supplier_cost(quote.line_items)) if quote else Decimal('0'),
                travelers=r.get('travelers') or 1,
                adults=r.get('adults') or 1, children=r.get('children') or 0, package_name=r.get('package_name') or '',
                accommodation_level=r.get('accommodation_level') or 'midrange', travel_date=r['travel_date'],
                special_request=r.get('special_request') or '',
                total_amount=dec(r['total_amount']) if r.get('total_amount') is not None else None,
                deposit_amount=dec(r['deposit_amount']) if r.get('deposit_amount') is not None else None,
                amount_paid=dec(r.get('amount_paid')), payment_status=r.get('payment_status') or 'pending',
                payment_method=r.get('payment_method') or '', paypal_order_id=r.get('paypal_order_id') or '',
                confirmation_email_sent=bool(r.get('confirmation_email_sent')), payment_notes=r.get('payment_notes') or '',
                reminder_sent_at=r.get('reminder_sent_at'),
            )
            booking.set_tracking_password()  # legacy plaintext tracking passwords aren't recoverable from the DB either (also hashed there) — guests use "forgot tracking password" to get a fresh one
            booking.save(update_fields=['tracking_password_hash'])
            if booking.amount_paid > 0:
                # The legacy app kept only a running total; open the ledger with
                # it so ledger sum == amount_paid from day one.
                Payment.objects.create(
                    booking=booking, amount=booking.amount_paid,
                    kind='full' if booking.payment_status == 'fully_paid' else 'deposit',
                    method={'paypal': 'paypal'}.get(booking.payment_method, 'bank_transfer'),
                    reference=booking.paypal_order_id or 'legacy-import',
                    received_at=(r.get('updated_at') or r.get('created_at') or timezone.now()).date(),
                    notes='Opening balance imported from the legacy system.',
                )
            n += 1
        self.stdout.write(f'Bookings: {n}')

    def _import_booking_reminders(self):
        n = 0
        for r in rows('booking_reminders'):
            booking = Booking.objects.filter(booking_ref=r['booking_ref']).first()
            BookingReminder.objects.create(
                booking=booking, booking_ref=r['booking_ref'], type=r.get('type') or 'custom',
                send_at=r['send_at'], sent_at=r.get('sent_at'), status=r.get('status') or 'pending',
                subject=r.get('subject') or '', body=r.get('body') or '',
            )
            n += 1
        self.stdout.write(f'Booking reminders: {n}')

    # ── Content ────────────────────────────────────────────────
    def _import_team_members(self):
        n = 0
        for r in rows('team_members'):
            TeamMember.objects.create(
                name=r['name'], role=r.get('role') or '', member_type=r.get('member_type') or 'team',
                bio=r.get('bio') or '', email=r.get('email') or '', phone=r.get('phone') or '',
                linkedin_url=r.get('linkedin_url') or '', sort_order=r.get('sort_order') or 0,
                is_active=bool(r.get('is_active', 1)),
            )
            n += 1
        self.stdout.write(f'Team members: {n}')

    def _import_contact_messages(self):
        n = 0
        for r in rows('contact_messages'):
            ContactMessage.objects.create(
                full_name=r['full_name'], email=r['email'], phone=r.get('phone') or '',
                subject=r.get('subject') or '', message=r['message'], is_read=bool(r.get('is_read')),
                first_response_at=r.get('first_response_at'),
            )
            n += 1
        self.stdout.write(f'Contact messages: {n}')

    def _import_custom_safari_requests(self, customer_by_email, user_by_legacy_id):
        mapping = {}
        n = 0
        for r in rows('custom_safari_requests'):
            customer = customer_by_email.get((r.get('email') or '').strip().lower())
            mapping[r['id']] = CustomSafariRequest.objects.create(
                rooms=r.get('rooms'), airport_pickup=bool(r.get('airport_pickup')),
                submitted_by_agent=user_by_legacy_id.get(r.get('submitted_by_agent_id')),
                first_response_at=r.get('first_response_at'),
                customer=customer, full_name=r.get('full_name') or '', email=r.get('email') or '',
                phone=r.get('phone') or '', country=r.get('country') or '', travelers=r.get('travelers') or '',
                adults=r.get('adults'), children=r.get('children'), infants=r.get('infants'),
                start_date=r.get('start_date'), duration_days=r.get('duration_days'),
                destinations=r.get('destinations') or '', message=r.get('message') or '',
                status=r.get('status') or 'new', flexible_dates=r.get('flexible_dates') or '',
                guide_language=r.get('guide_language') or '', mainland_accommodation=r.get('mainland_accommodation') or '',
                beach_accommodation=r.get('beach_accommodation') or '', meal_plan=r.get('meal_plan') or '',
                room_layout=r.get('room_layout') or '', accommodation_standard=r.get('accommodation_standard') or '',
                total_budget=r.get('total_budget') or '', experiences=r.get('experiences') or '',
            )
            n += 1
        self.stdout.write(f'Custom safari requests: {n}')
        return mapping

    def _import_email_templates(self):
        n = 0
        for r in rows('email_templates'):
            EmailTemplate.objects.create(
                template_key=r['template_key'], subject=r['subject'], body_html=r['body_html'],
                is_custom=bool(r.get('is_custom')),
            )
            n += 1
        self.stdout.write(f'Email templates: {n}')
