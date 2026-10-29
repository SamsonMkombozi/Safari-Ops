from decimal import Decimal

from django.test import TestCase

from apps.bookings import services
from apps.bookings.models import Booking, Payment
from apps.content.models import EmailQueue
from apps.core.settings_store import set_setting
from apps.crm import pipeline
from apps.crm.models import Commission, Lead

from .factories import catalog, future, user


class MoneyFlowTests(TestCase):
    def setUp(self):
        self.pkg = catalog()
        self.admin = user('boss', 'admin')
        self.agent = user('ag', 'agent', commission_rate=Decimal('12'))
        self.lead = Lead.objects.create(full_name='Client One', email='c1@test.example.com', agent=self.agent)

    def quote(self, **kw):
        return services.build_quotation(
            client={'name': 'Client One', 'email': 'c1@test.example.com', 'country': 'Germany'}, package=self.pkg,
            adults=2, start_date=future(), user=self.admin, lead=self.lead, **kw)

    def test_quote_to_booking_creates_agent_commission(self):
        q = self.quote(markup_pct=10)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.pipeline_stage, 'quoted')
        self.assertEqual(q.grand_total, Decimal('3444.89'))  # (2654 * 1.10) * 1.18
        booking, password = services.convert_quotation(q, user=self.admin)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.pipeline_stage, 'booked')
        self.assertTrue(booking.check_tracking_password(password))
        self.assertEqual(booking.supplier_cost, Decimal('2454.00'))
        c = Commission.objects.get(lead=self.lead)
        self.assertEqual(c.commission_rate, Decimal('12'))
        self.assertEqual(c.commission_amount, (q.grand_total * Decimal('0.12')).quantize(Decimal('0.01')))
        self.assertTrue(EmailQueue.objects.filter(template='booking_confirmation', to_email=booking.email).exists())
        self.assertTrue(booking.reminders.exists())
        # converting twice is idempotent
        again, _ = services.convert_quotation(q, user=self.admin)
        self.assertEqual(again.pk, booking.pk)
        self.assertEqual(Commission.objects.filter(lead=self.lead).count(), 1)

    def test_payments_ledger_and_status(self):
        booking, _ = services.convert_quotation(self.quote(), user=self.admin)
        booking, _ = services.record_payment(booking, 500, 'bank_transfer', 'T1', user=self.admin)
        self.assertEqual(booking.payment_status, 'deposit_paid')
        booking = services.set_payment_status(booking, 'fully_paid', user=self.admin)
        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'fully_paid')
        self.assertEqual(booking.balance_due, 0)
        self.assertEqual(sum(p.amount for p in booking.payments.all()), booking.amount_paid)
        self.assertTrue(EmailQueue.objects.filter(template='invoice_paid').exists())

    def test_deposit_status_requires_amount(self):
        booking, _ = services.convert_quotation(self.quote(), user=self.admin)
        with self.assertRaises(ValueError):
            services.set_payment_status(booking, 'deposit_paid', amount_paid=0)

    def test_paypal_replay_is_idempotent(self):
        booking, _ = services.convert_quotation(self.quote(), user=self.admin)
        services.record_payment(booking, 300, 'paypal', 'PP-1')
        _, second = services.record_payment(Booking.objects.get(pk=booking.pk), 300, 'paypal', 'PP-1')
        self.assertIsNone(second)
        self.assertEqual(Payment.objects.filter(booking=booking).count(), 1)

    def test_cancellation_claws_back_unpaid_commission(self):
        booking, _ = services.convert_quotation(self.quote(), user=self.admin)
        services.set_payment_status(booking, 'cancelled', user=self.admin)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.pipeline_stage, 'lost')
        self.assertEqual(Commission.objects.get(lead=self.lead).status, 'cancelled')
        self.assertFalse(booking.reminders.filter(status='pending').exists())

    def test_paid_commission_is_never_clawed_back(self):
        booking, _ = services.convert_quotation(self.quote(), user=self.admin)
        c = Commission.objects.get(lead=self.lead)
        pipeline.set_commission_status(c, 'paid', self.admin)
        services.set_payment_status(booking, 'cancelled', user=self.admin)
        self.assertEqual(Commission.objects.get(pk=c.pk).status, 'paid')

    def test_agent_direct_booking(self):
        booking, password, lead = services.agent_direct_booking(
            self.agent, full_name='Walk In', email='walkin@test.example.com', phone='', country='Kenya',
            package=self.pkg, travel_date=future(), adults=2, children=0)
        self.assertEqual(booking.agent, self.agent)
        self.assertEqual(lead.pipeline_stage, 'booked')
        self.assertTrue(Commission.objects.filter(lead=lead, agent=self.agent).exists())

    def test_direct_booking_respects_setting(self):
        set_setting('agent_direct_booking_enabled', False)
        with self.assertRaises(ValueError):
            services.agent_direct_booking(self.agent, full_name='X', email='x@test.example.com', phone='', country='',
                                          package=self.pkg, travel_date=future(), adults=1, children=0)

    def test_deposit_percent_setting_drives_quotes(self):
        set_setting('deposit_percent', 40)
        q = self.quote()
        self.assertEqual(q.deposit_amount, (q.grand_total * Decimal('0.40')).quantize(Decimal('0.01')))
