"""
Seed realistic demo data for testing the admin panel, agent portal and the
revenue side (quotes → bookings → payments → commissions → profit).

Every transactional row is created through the real service layer
(pricing.build, services.build_quotation / convert_quotation /
record_payment / agent_direct_booking, pipeline.set_lead_stage_manual),
so the demo exercises the same code paths production uses rather than
hand-inserted numbers.

Demo rows are tagged so they can be removed again without touching real
data: guest emails end in DEMO_DOMAIN, demo users' usernames are listed in
DEMO_USERS, field staff/suppliers carry DEMO_TAG in their notes.

    python manage.py seed_demo_data            # seed (refuses if demo data already exists)
    python manage.py seed_demo_data --reset    # remove previous demo data, then seed
    python manage.py seed_demo_data --purge    # remove demo data only
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Booking, BookingReminder, Payment, Quotation
from apps.content.models import ContactMessage, CustomSafariRequest, EmailQueue, Review
from apps.core.models import ActivityLog, APIKey, CurrencyRate, SiteSetting
from apps.core.settings_store import set_setting
from apps.crm import pipeline
from apps.crm.models import AgentTarget, Commission, Customer, Lead
from apps.operations.models import BookingAssignment, Incident, StaffMember, Supplier
from apps.packages.models import Package, Vehicle

DEMO_DOMAIN = 'demo.example.com'
DEMO_TAG = '[demo]'
DEMO_PASSWORD = 'Safari@2026!'
DEMO_USERS = [
    # username, first, last, role, commission_rate, monthly target
    ('demo.owner', 'Neema', 'Mollel', 'owner', None, 0),
    ('demo.admin', 'Baraka', 'Mushi', 'admin', None, 0),
    ('demo.manager', 'Rehema', 'Kimaro', 'manager', None, 0),
    ('agent.amina', 'Amina', 'Hassan', 'agent', Decimal('12.00'), Decimal('25000')),
    ('agent.joseph', 'Joseph', 'Lyimo', 'agent', Decimal('10.00'), Decimal('18000')),
    ('agent.grace', 'Grace', 'Wanjiru', 'agent', None, Decimal('12000')),
]

FIRST = ['Emma', 'Liam', 'Sophie', 'Lucas', 'Charlotte', 'Noah', 'Hannah', 'Felix', 'Mia', 'Oliver', 'Clara', 'Jonas', 'Isla',
         'Mateo', 'Freya', 'Hugo', 'Ava', 'Leon', 'Chloe', 'Daniel', 'Maya', 'Elias', 'Zara', 'Samuel', 'Nora', 'Ethan', 'Lena',
         'Aiden', 'Ruth', 'Kwame', 'Wanjiku', 'Kofi']
LAST = ['Schmidt', 'Johnson', 'Dubois', 'Rossi', 'Van Dijk', 'Andersson', 'Williams', 'Müller', 'Garcia', 'Brown', 'Nielsen',
        'Taylor', 'Kowalski', 'Moreau', 'Fischer', 'Okafor', 'Silva', 'Martin', 'Becker', 'Murphy', 'Otieno', 'Mensah']
COUNTRIES = ['United Kingdom', 'Germany', 'United States', 'France', 'Netherlands', 'Italy', 'Sweden', 'Australia', 'Canada',
             'Switzerland', 'Spain', 'Kenya', 'Tanzania', 'Denmark', 'Belgium']
SOURCES = ['website', 'instagram', 'referral', 'tripadvisor', 'google_ads', 'whatsapp', 'travel_fair']


class Command(BaseCommand):
    help = 'Seed demo users, customers, leads, quotations, bookings, payments, commissions and ops data.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Remove existing demo data first.')
        parser.add_argument('--purge', action='store_true', help='Only remove demo data.')
        parser.add_argument('--seed', type=int, default=2026, help='Random seed (same seed → same data).')
        parser.add_argument('--allow-production', action='store_true', help='Allow running with DEBUG=False (staging/demo servers only).')

    def handle(self, *args, **opts):
        from django.conf import settings
        if not settings.DEBUG and not opts['allow_production']:
            raise CommandError('Refusing to seed demo data with DEBUG=False (looks like production). '
                               'Pass --allow-production if this really is a staging/demo server.')
        if opts['purge'] or opts['reset']:
            self._purge()
            if opts['purge']:
                return
        elif Customer.objects.filter(email__endswith=DEMO_DOMAIN).exists():
            raise CommandError('Demo data already exists — use --reset to replace it.')
        if not Package.objects.filter(is_active=True).exists():
            raise CommandError('No active packages — run import_legacy_data first so quotes can be priced from real itineraries.')

        self.rng = random.Random(opts['seed'])
        self.now = timezone.now()
        self.today = timezone.localdate()
        with transaction.atomic():
            self._settings()
            self.users = self._users()
            self.agents = [u for u in self.users.values() if u.role == 'agent']
            self.staff_user = self.users['demo.manager']
            self._ops_people()
            self._funnel()
            self._agent_direct_bookings()
            self._commission_lifecycle()
            self._requests_messages()
            self._reviews_incidents()
            self._targets()
        self._report()

    # ── helpers ────────────────────────────────────────────────────────

    def _person(self):
        first, last = self.rng.choice(FIRST), self.rng.choice(LAST)
        tag = self.rng.randint(10, 999)
        return {
            'name': f'{first} {last}',
            'email': f'{first}.{last}{tag}'.lower().replace(' ', '').replace('ü', 'u') + f'@{DEMO_DOMAIN}',
            'phone': f'+{self.rng.choice(["44", "49", "1", "33", "31", "39"])}7{self.rng.randint(100000000, 999999999)}',
            'country': self.rng.choice(COUNTRIES),
        }

    def _backdate(self, obj, days_ago, field='created_at'):
        when = self.now - timedelta(days=days_ago, hours=self.rng.randint(0, 20))
        type(obj).objects.filter(pk=obj.pk).update(**{field: when})
        return when

    # ── seed steps ─────────────────────────────────────────────────────

    def _settings(self):
        # Business settings are never overwritten — real values (e.g. imported
        # from the legacy app) always win; demo values only fill gaps.
        existing = set(SiteSetting.objects.values_list('key', flat=True))
        for k, v in {'agent_direct_booking_enabled': True, 'auto_send_payment_emails': True}.items():
            if k not in existing:
                set_setting(k, v)
        if 'emergency_contacts' not in existing:
            set_setting('emergency_contacts', {'office_24h': '+255 663 430 934', 'hospital': 'Arusha Lutheran Medical Centre — +255 27 254 8030',
                                           'police': '112', 'tourist_police': '+255 27 250 3641', 'evacuation_provider': 'AMREF Flying Doctors — +254 20 699 2299',
                                           'notes': 'Demo values — replace with real numbers before go-live.'})
        for code, name, sym, rate in [('USD', 'US Dollar', '$', 1), ('EUR', 'Euro', '€', '0.92'), ('GBP', 'British Pound', '£', '0.79'),
                                      ('TZS', 'Tanzanian Shilling', 'TSh', '2650'), ('KES', 'Kenyan Shilling', 'KSh', '129.5')]:
            CurrencyRate.objects.get_or_create(code=code, defaults={'name': name, 'symbol': sym, 'rate_to_usd': Decimal(str(rate))})

    def _users(self):
        users = {}
        for username, first, last, role, rate, target in DEMO_USERS:
            u, _ = User.objects.get_or_create(username=username)
            u.first_name, u.last_name, u.role = first, last, role
            u.email = f'{username}@{DEMO_DOMAIN}'
            u.commission_rate, u.target_monthly = rate, target
            u.is_active, u.is_staff = True, role in ('owner', 'admin')
            u.can_change_status, u.can_delete_records = True, role != 'manager'
            u.phone = f'+2557{self.rng.randint(10000000, 99999999)}'
            u.set_password(DEMO_PASSWORD)
            u.save()
            users[username] = u
        APIKey.objects.get_or_create(name=f'Demo WordPress site {DEMO_TAG}', defaults={'can_read': True, 'can_write': True,
                                                                                        'created_by': users['demo.owner']})
        return users

    def _ops_people(self):
        for name, role, langs, rate in [('Emmanuel Laizer', 'guide_driver', 'English, Swahili, German', 120),
                                        ('Daudi Saning\'o', 'guide_driver', 'English, Swahili, French', 115),
                                        ('Hamisi Juma', 'driver', 'English, Swahili', 80),
                                        ('Lucy Mrema', 'guide', 'English, Swahili, Italian', 110),
                                        ('Peter Massawe', 'guide_driver', 'English, Swahili, Spanish', 120)]:
            StaffMember.objects.create(full_name=name, role=role, languages=langs, daily_rate=rate, phone=f'+2557{self.rng.randint(10000000, 99999999)}',
                                       license_number=f'TZ-DL-{self.rng.randint(100000, 999999)}', notes=DEMO_TAG)
        for name, cat, terms in [('Serengeti Sopa Lodge', 'accommodation', '30% on confirmation, balance 30 days prior'),
                                 ('Ngorongoro Conservation Area Authority', 'park_operator', 'Prepaid via TANAPA e-payment'),
                                 ('Hot Air Balloon Safaris Ltd', 'activity_operator', 'Net 14 days'),
                                 ('Kilimanjaro Fuel & Fleet', 'transport', 'Monthly invoice'),
                                 ('Zanzibar Beach Resorts Group', 'accommodation', '50% deposit, balance 21 days prior'),
                                 ('Maasai Cultural Boma Collective', 'other', 'Cash on day')]:
            Supplier.objects.create(name=name, category=cat, payment_terms=terms, contact_person=self._person()['name'],
                                    email=f'ops@{name.split()[0].lower()}.{DEMO_DOMAIN}', notes=DEMO_TAG)

    def _funnel(self):
        """Leads → quotations → bookings → payments, spread over the last 12 months."""
        packages = list(Package.objects.filter(is_active=True).select_related('itinerary'))
        stages = (['lead'] * 6 + ['qualified'] * 5 + ['quoted'] * 6 + ['negotiation'] * 3 + ['booked'] * 12 +
                  ['travelled'] * 4 + ['completed'] * 6 + ['lost'] * 5)
        self.rng.shuffle(stages)
        self.bookings = []
        for i, target_stage in enumerate(stages):
            p = self._person()
            pkg = self.rng.choice(packages)
            adults = self.rng.choice([1, 2, 2, 2, 3, 4, 4, 6])
            children = self.rng.choice([0, 0, 0, 1, 2]) if adults >= 2 else 0
            agent = self.rng.choice(self.agents + [None, None])  # ~40% direct (no agent commission)
            created_days_ago = self.rng.randint(5, 360)
            if target_stage in ('travelled', 'completed'):
                travel = self.today - timedelta(days=self.rng.randint(5, max(6, created_days_ago - 20)))
                created_days_ago = max(created_days_ago, (self.today - travel).days + 30)
            else:
                travel = self.today + timedelta(days=self.rng.randint(10, 240))
            lead = Lead.objects.create(
                full_name=p['name'], email=p['email'], phone=p['phone'], country=p['country'], source=self.rng.choice(SOURCES),
                package_name=pkg.name, party_size=adults + children, travel_date=travel, agent=agent,
                assigned_to=self.staff_user, budget_range=self.rng.choice(['$3k–5k', '$5k–10k', '$10k–20k', '$20k+', '']),
                destinations='Serengeti, Ngorongoro' if 'Zanzibar' not in pkg.name else 'Serengeti, Zanzibar',
                notes=self.rng.choice(['Honeymoon', 'Family trip with teens', 'Photography focus', 'First safari', 'Anniversary', '']),
                score=self.rng.randint(10, 95),
            )
            self._backdate(lead, created_days_ago)
            if target_stage in ('lead', 'qualified'):
                if target_stage == 'qualified':
                    pipeline.set_lead_stage_manual(lead, 'qualified')
                continue

            markup = self.rng.choice([0, 10, 15, 15, 20, 25])
            discount = self.rng.choice([0, 0, 0, 5])
            creator = agent if agent and self.rng.random() < 0.3 else self.rng.choice([self.users['demo.admin'], self.staff_user])
            quote = services.build_quotation(
                client={'name': p['name'], 'email': p['email'], 'phone': p['phone'], 'country': p['country']},
                package=pkg, adults=adults, children=children, rooms=max(1, (adults + 1) // 2), start_date=travel,
                accommodation_level=pkg.accommodation_level or 'midrange', markup_pct=markup, discount_pct=discount,
                user=creator, lead=lead,
            )
            self._backdate(quote, created_days_ago - 2)
            if target_stage in ('quoted', 'negotiation', 'lost'):
                services.send_quotation(quote)
                for _ in range(self.rng.randint(0, 4)):
                    quote.record_view()
                if target_stage == 'negotiation':
                    pipeline.set_lead_stage_manual(lead, 'negotiation')
                if target_stage == 'lost':
                    Quotation.objects.filter(pk=quote.pk).update(status=self.rng.choice(['declined', 'expired']))
                    pipeline.set_lead_stage_manual(lead, 'lost')
                continue

            # booked / travelled / completed → real booking through the conversion service
            services.send_quotation(quote)
            quote.record_view()
            booking, _ = services.convert_quotation(quote, user=creator, travel_date=travel)
            booked_days_ago = max(1, created_days_ago - self.rng.randint(3, 15))
            self._backdate(booking, booked_days_ago)
            lead.refresh_from_db()
            if lead.converted_at:
                self._backdate(lead, booked_days_ago, 'converted_at')
            self.bookings.append(booking)
            self._payments(booking, booked_days_ago, target_stage)
            if target_stage in ('travelled', 'completed'):
                pipeline.set_lead_stage_manual(lead, target_stage)
                self._assign(booking)
            elif self.rng.random() < 0.5:
                self._assign(booking)

        # a couple of cancellations to exercise the commission clawback
        for b in [b for b in self.bookings if b.travel_date > self.today][:2]:
            services.set_payment_status(Booking.objects.get(pk=b.pk), 'cancelled', user=self.users['demo.admin'])

    def _payments(self, booking, booked_days_ago, stage):
        booking = Booking.objects.get(pk=booking.pk)
        total = booking.total_amount or Decimal('0')
        deposit = booking.deposit_amount or (total * Decimal('0.25')).quantize(Decimal('0.01'))
        method = self.rng.choice(['bank_transfer', 'bank_transfer', 'paypal', 'wise', 'card'])
        dep_day = self.today - timedelta(days=max(0, booked_days_ago - self.rng.randint(0, 5)))
        roll = self.rng.random()
        if stage in ('travelled', 'completed') or roll < 0.35:
            services.record_payment(booking, deposit, method, f'DEMO-{self.rng.randint(100000, 999999)}', dep_day, user=self.staff_user)
            bal_day = min(self.today, dep_day + timedelta(days=self.rng.randint(20, 90)))
            booking.refresh_from_db()
            services.record_payment(booking, total - booking.amount_paid, self.rng.choice(['bank_transfer', 'wise', 'card']),
                                    f'DEMO-{self.rng.randint(100000, 999999)}', bal_day, user=self.staff_user)
        elif roll < 0.8:
            # deposits are often a round figure a little above/below the suggested amount
            paid = (deposit + Decimal(self.rng.choice([-50, 0, 0, 100]))).quantize(Decimal('1'))
            services.record_payment(booking, max(Decimal('100'), paid), method, f'DEMO-{self.rng.randint(100000, 999999)}', dep_day,
                                    user=self.staff_user)
        # else: still pending payment

    def _assign(self, booking):
        guide = StaffMember.objects.filter(notes=DEMO_TAG, role__in=['guide_driver', 'guide']).order_by('?').first()
        BookingAssignment.objects.create(booking=booking, staff=guide, vehicle=Vehicle.objects.order_by('?').first(), notes='Lead guide')

    def _agent_direct_bookings(self):
        packages = list(Package.objects.filter(is_active=True))
        for agent in self.agents:
            for _ in range(self.rng.randint(1, 3)):
                p = self._person()
                travel = self.today + timedelta(days=self.rng.randint(20, 200))
                booking, _, lead = services.agent_direct_booking(
                    agent, full_name=p['name'], email=p['email'], phone=p['phone'], country=p['country'],
                    package=self.rng.choice(packages), travel_date=travel, adults=self.rng.choice([2, 2, 3, 4]),
                    children=self.rng.choice([0, 0, 1]), notes='Booked through partner agent')
                days = self.rng.randint(2, 120)
                self._backdate(booking, days)
                self._backdate(lead, days)
                self._backdate(lead, days, 'converted_at')
                self.bookings.append(booking)
                if self.rng.random() < 0.6:
                    self._payments(booking, days, 'booked')

    def _commission_lifecycle(self):
        """Older commissions get approved/paid so the payout side of the agent portal has history."""
        admin = self.users['demo.owner']
        for c in Commission.objects.filter(agent__in=self.agents, status='pending').select_related('lead', 'agent'):
            booking = Booking.objects.filter(booking_ref=c.booking_ref or (c.lead.booking_ref if c.lead else '')).first()
            if booking and booking.payment_status == 'fully_paid':
                pipeline.set_commission_status(c, 'paid', admin)
                self._backdate(c, self.rng.randint(1, 60), 'paid_at')
            elif booking and booking.payment_status == 'deposit_paid' and self.rng.random() < 0.6:
                pipeline.set_commission_status(c, 'approved', admin)

    def _requests_messages(self):
        for i in range(9):
            p = self._person()
            req = CustomSafariRequest.objects.create(
                full_name=p['name'], email=p['email'], phone=p['phone'], country=p['country'], adults=self.rng.choice([2, 2, 4]),
                children=self.rng.choice([0, 1, 2]), start_date=self.today + timedelta(days=self.rng.randint(30, 300)),
                duration_days=self.rng.choice([7, 8, 10, 12, 14]), destinations=self.rng.choice(
                    ['Serengeti, Ngorongoro, Zanzibar', 'Ruaha, Nyerere', 'Tarangire, Lake Manyara, Serengeti', 'Kilimanjaro trek + safari']),
                message=self.rng.choice(['We would love to see the Great Migration river crossings.', 'Travelling with grandparents — gentle pace please.',
                                         'Interested in walking safaris and a night in a tree house.', 'Honeymoon — something special at the end on the beach.']),
                total_budget=self.rng.choice(['$8,000', '$12,000', '$20,000', 'Flexible']), guide_language=self.rng.choice(['English', 'German', 'French']),
                accommodation_standard=self.rng.choice(['Mid-range', 'Luxury', 'Ultra luxury']), meal_plan='Full board',
                status=self.rng.choice(['new', 'new', 'new', 'in_review', 'quoted', 'closed']),
            )
            self._backdate(req, self.rng.randint(0, 40))
        for i in range(10):
            p = self._person()
            m = ContactMessage.objects.create(
                full_name=p['name'], email=p['email'], phone=p['phone'],
                subject=self.rng.choice(['Availability in August', 'Kilimanjaro + safari combo', 'Group of 12 — corporate retreat',
                                         'Vegetarian meals?', 'Payment by card', 'Visa question']),
                message='Hello, could you tell me more about your safaris and what would suit us? Thanks in advance.',
                is_read=i > 3,
            )
            self._backdate(m, self.rng.randint(0, 30))

    def _reviews_incidents(self):
        travelled = [b for b in Booking.objects.filter(travel_date__lt=self.today).exclude(payment_status='cancelled')]
        comments = ['Absolutely magical — our guide Emmanuel spotted a leopard within minutes!', 'Seamless from airport pickup to the beach.',
                    'Great value for money, lodges were superb.', 'The balloon safari was the highlight of our lives.',
                    'Good trip, one long driving day but worth it.', 'Vehicle broke down briefly but the team fixed it fast.']
        for b in travelled:
            rating = self.rng.choice([5, 5, 5, 4, 4, 3])
            Review.objects.create(booking_ref=b.booking_ref, customer=b.customer, guest_name=b.full_name, guest_country=b.country,
                                  rating=rating, nps_score=min(10, rating * 2 + self.rng.choice([-1, 0, 0])), comment=self.rng.choice(comments),
                                  is_published=rating >= 4)
        for b, (kind, sev, status) in zip(travelled[:3] + self.bookings[:2], [('vehicle_breakdown', 'medium', 'resolved'), ('weather_delay', 'low', 'resolved'),
                                                                              ('medical', 'high', 'resolved'), ('accommodation_issue', 'medium', 'open'),
                                                                              ('other', 'low', 'open')]):
            Incident.objects.create(booking_ref=b.booking_ref, incident_type=kind, severity=sev, status=status, reported_by=self.staff_user,
                                    description=f'{DEMO_TAG} {kind.replace("_", " ").capitalize()} reported by guide.',
                                    resolution_notes='Handled on the ground, guest informed.' if status == 'resolved' else '',
                                    occurred_at=self.now - timedelta(days=self.rng.randint(1, 60)),
                                    resolved_at=self.now if status == 'resolved' else None)

    def _targets(self):
        month = self.today.replace(day=1)
        for a in self.agents:
            AgentTarget.objects.update_or_create(agent=a, month=month, defaults={
                'target_leads': 15, 'target_bookings': 4, 'target_value': a.target_monthly,
                'actual_leads': Lead.objects.filter(agent=a, created_at__date__gte=month).count(),
                'actual_bookings': Lead.objects.filter(agent=a, pipeline_stage='booked', converted_at__date__gte=month).count(),
            })

    # ── purge / report ─────────────────────────────────────────────────

    def _purge(self):
        demo_agents = User.objects.filter(username__in=[u[0] for u in DEMO_USERS])
        demo_bookings = Booking.objects.filter(email__endswith=DEMO_DOMAIN)
        refs = list(demo_bookings.values_list('booking_ref', flat=True))
        counts = {
            'commissions': Commission.objects.filter(agent__in=demo_agents).delete()[0] + Commission.objects.filter(lead__email__endswith=DEMO_DOMAIN).delete()[0],
            'reviews': Review.objects.filter(booking_ref__in=refs).delete()[0],
            'incidents': Incident.objects.filter(description__startswith=DEMO_TAG).delete()[0],
            'emails': EmailQueue.objects.filter(to_email__endswith=DEMO_DOMAIN).delete()[0],
            'reminders': BookingReminder.objects.filter(booking_ref__in=refs).delete()[0],
            'bookings': demo_bookings.delete()[0],  # cascades payments + assignments
            'quotations': Quotation.objects.filter(client_email__endswith=DEMO_DOMAIN).delete()[0],
            'leads': Lead.objects.filter(email__endswith=DEMO_DOMAIN).delete()[0],
            'requests': CustomSafariRequest.objects.filter(email__endswith=DEMO_DOMAIN).delete()[0],
            'messages': ContactMessage.objects.filter(email__endswith=DEMO_DOMAIN).delete()[0],
            'customers': Customer.objects.filter(email__endswith=DEMO_DOMAIN).delete()[0],
            'staff': StaffMember.objects.filter(notes=DEMO_TAG).delete()[0],
            'suppliers': Supplier.objects.filter(notes=DEMO_TAG).delete()[0],
            'api_keys': APIKey.objects.filter(name__endswith=DEMO_TAG).delete()[0],
            'targets': AgentTarget.objects.filter(agent__in=demo_agents).delete()[0],
            'activity': ActivityLog.objects.filter(actor__in=demo_agents).delete()[0],
            'users': demo_agents.delete()[0],
        }
        self.stdout.write('Removed demo data: ' + ', '.join(f'{k} {v}' for k, v in counts.items() if v))

    def _report(self):
        live = Booking.objects.exclude(payment_status='cancelled').filter(email__endswith=DEMO_DOMAIN)
        sales = sum((b.total_amount or 0 for b in live), Decimal('0'))
        collected = sum((p.amount for p in Payment.objects.filter(booking__email__endswith=DEMO_DOMAIN)), Decimal('0'))
        comm = Commission.objects.filter(agent__in=self.agents)
        self.stdout.write(self.style.SUCCESS('Demo data seeded:'))
        self.stdout.write(f'  leads {Lead.objects.filter(email__endswith=DEMO_DOMAIN).count()}, '
                          f'quotations {Quotation.objects.filter(client_email__endswith=DEMO_DOMAIN).count()}, '
                          f'bookings {Booking.objects.filter(email__endswith=DEMO_DOMAIN).count()} '
                          f'({Booking.objects.filter(email__endswith=DEMO_DOMAIN, payment_status="cancelled").count()} cancelled), '
                          f'payments {Payment.objects.filter(booking__email__endswith=DEMO_DOMAIN).count()}')
        self.stdout.write(f'  booked sales ${sales:,.2f} · collected ${collected:,.2f} · outstanding ${sales - collected:,.2f}')
        self.stdout.write(f'  commissions {comm.count()}: ' + ', '.join(f'{s} ${sum(c.commission_amount for c in comm.filter(status=s)):,.2f}'
                                                                       for s in ('pending', 'approved', 'paid', 'cancelled')))
        self.stdout.write(f'  logins (password {DEMO_PASSWORD}): ' + ', '.join(u[0] for u in DEMO_USERS))
