from django.contrib.auth.hashers import check_password
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Quotation
from apps.core.legacy import legacy_password
from apps.core.settings_store import set_setting
from apps.crm.models import Lead

from .factories import catalog, future, user

# Generated with PHP: password_hash('Test-Pass-123', PASSWORD_BCRYPT, ['cost' => 4])
PHP_HASH = '$2y$04$DlRXV3JeOlkMtkMD0.QCZuce4wNB9XEc5HczkNS4qKtdsMxVXlpWe'


class ThemeTests(TestCase):
    def test_theme_saved_to_profile_and_rendered(self):
        u = user('themer', 'manager')
        self.client.force_login(u)
        self.assertEqual(self.client.post(reverse('accounts:theme'), {'theme': 'mono'}).json()['theme'], 'mono')
        u.refresh_from_db()
        self.assertEqual(u.theme_preference, 'mono')
        self.assertContains(self.client.get(reverse('dashboard:home')), 'data-theme="mono"')
        self.assertEqual(self.client.post(reverse('accounts:theme'), {'theme': 'neon'}).status_code, 400)
        self.client.post(reverse('accounts:theme'), {'theme': 'system'})
        self.assertNotContains(self.client.get(reverse('dashboard:home')), 'data-theme="')

    def test_theme_endpoint_requires_login_and_post(self):
        self.assertEqual(self.client.post(reverse('accounts:theme'), {'theme': 'dark'}).status_code, 302)
        self.client.force_login(user('t2', 'agent'))
        self.assertEqual(self.client.get(reverse('accounts:theme')).status_code, 405)


class PublicQuoteTests(TestCase):
    def setUp(self):
        self.pkg = catalog()
        self.lead = Lead.objects.create(full_name='Q', email='q@test.example.com', pipeline_stage='quoted')
        self.quote = services.build_quotation(client={'name': 'Q', 'email': 'q@test.example.com'}, package=self.pkg,
                                              adults=2, start_date=future(), lead=self.lead)
        services.send_quotation(self.quote)

    def test_client_can_view_and_accept(self):
        url = reverse('quote_public', args=[self.quote.public_token])
        self.assertContains(self.client.get(url), 'Accept quotation')
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'viewed')
        r = self.client.post(reverse('quote_accept', args=[self.quote.public_token]))
        self.assertEqual(r.status_code, 302)
        self.quote.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertEqual(self.quote.status, 'accepted')
        self.assertEqual(self.lead.pipeline_stage, 'negotiation')

    def test_bad_token_404_and_expired_cannot_accept(self):
        self.assertEqual(self.client.get('/q/' + 'a' * 48 + '/').status_code, 404)
        self.assertEqual(self.client.get('/q/123/').status_code, 404)
        Quotation.objects.filter(pk=self.quote.pk).update(valid_until=future(-1))
        self.client.post(reverse('quote_accept', args=[self.quote.public_token]))
        self.assertNotEqual(Quotation.objects.get(pk=self.quote.pk).status, 'accepted')

    def test_email_links_to_public_page(self):
        from apps.content.models import EmailQueue
        body = EmailQueue.objects.get(template='quotation_sent').body
        self.assertIn(f'/q/{self.quote.public_token}/', body)
        self.assertNotIn('/api/v1/', body)


class AccountRecoveryTests(TestCase):
    def test_legacy_php_bcrypt_hash_verifies(self):
        encoded = legacy_password(PHP_HASH)
        self.assertTrue(check_password('Test-Pass-123', encoded))
        self.assertFalse(check_password('wrong', encoded))
        self.assertIsNone(legacy_password('not-a-hash'))

    def test_password_reset_reaches_users_without_a_password(self):
        u = User.objects.create(username='imported', email='imported@test.example.com', role='admin')
        u.set_unusable_password()
        u.save()
        self.client.post(reverse('accounts:password_reset'), {'email': 'IMPORTED@test.example.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/accounts/reset/', mail.outbox[0].body)


class SettingsEnforcementTests(TestCase):
    def test_maintenance_mode_pauses_public_submissions(self):
        from apps.core.models import APIKey
        key = APIKey.objects.create(name='site', can_write=True)
        set_setting('maintenance_mode', True)
        r = self.client.post('/api/v1/contact-messages/', {'full_name': 'A', 'email': 'a@test.example.com', 'message': 'hi'},
                             HTTP_X_API_KEY=key.key)
        self.assertEqual(r.status_code, 503)
        set_setting('maintenance_mode', False)
        r = self.client.post('/api/v1/contact-messages/', {'full_name': 'A', 'email': 'a@test.example.com', 'message': 'hi'},
                             HTTP_X_API_KEY=key.key)
        self.assertEqual(r.status_code, 201)

    def test_party_size_cap(self):
        from apps.dashboard.forms import QuotationForm
        pkg = catalog()
        set_setting('max_party_size', 4)
        form = QuotationForm({'client_name': 'Big', 'client_email': 'big@test.example.com', 'package': pkg.pk, 'adults': 4,
                              'children': 2, 'rooms': 3, 'accommodation_level': 'luxury', 'markup_pct': 0, 'discount_pct': 0})
        self.assertFalse(form.is_valid())
        self.assertIn('exceeds the maximum', str(form.errors))

    def test_luxury_level_is_valid(self):
        pkg = catalog()
        pkg.full_clean()  # used to raise: 'luxury' is not a valid choice
