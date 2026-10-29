from django.test import TestCase
from django.urls import reverse

from apps.bookings import services
from apps.crm.models import Lead
from apps.dashboard.crud import RESOURCES

from .factories import PASSWORD, catalog, future, user


class AccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pkg = catalog()
        cls.owner = user('owner1', 'owner')
        cls.manager = user('mgr', 'manager')
        cls.agent = user('agent1', 'agent')
        cls.other_agent = user('agent2', 'agent')
        lead = Lead.objects.create(full_name='Own', email='own@test.example.com', agent=cls.agent)
        cls.other_lead = Lead.objects.create(full_name='Other', email='oth@test.example.com', agent=cls.other_agent)
        q = services.build_quotation(client={'name': 'Own', 'email': 'own@test.example.com'}, package=cls.pkg,
                                     adults=2, start_date=future(), user=cls.agent, lead=lead)
        cls.booking, _ = services.convert_quotation(q, user=cls.agent)
        cls.quote, cls.lead = q, lead

    def get(self, who, url):
        self.client.force_login(who)
        return self.client.get(url)

    def staff_urls(self):
        b, q = self.booking.pk, self.quote.pk
        urls = [reverse('dashboard:' + n) for n in (
            'home', 'booking_list', 'payment_list', 'invoice_list', 'quotation_list', 'quotation_new', 'lead_list',
            'lead_new', 'request_list', 'commission_list', 'message_list', 'email_queue', 'reminder_list',
            'emergency_contacts', 'sales', 'customer_experience')]
        urls += [reverse('dashboard:booking_detail', args=[b]), reverse('dashboard:invoice_detail', args=[b]),
                 reverse('dashboard:quotation_detail', args=[q]), reverse('dashboard:package_detail', args=[self.pkg.pk]),
                 reverse('accounts:profile'), reverse('accounts:change_password')]
        for slug, r in RESOURCES.items():
            if not r.admin_only:
                urls += [reverse(f'crud:{slug}'), reverse(f'crud:{slug}-new')]
        return urls

    def test_every_staff_page_renders(self):
        for url in self.staff_urls():
            with self.subTest(url=url):
                self.assertEqual(self.get(self.manager, url).status_code, 200)

    def test_admin_only_pages(self):
        admin_only = [reverse('dashboard:' + n) for n in ('profitability', 'agent_performance', 'settings', 'user_list', 'activity_log')]
        admin_only += [reverse('crud:currencies'), reverse('dashboard:booking_edit', args=[self.booking.pk])]
        for url in admin_only:
            with self.subTest(url=url):
                self.assertEqual(self.get(self.owner, url).status_code, 200)
                self.assertEqual(self.get(self.manager, url).status_code, 403)

    def test_agent_portal_and_isolation(self):
        for name in ('home', 'lead_list', 'direct_booking', 'custom_request', 'booking_list', 'quotation_list', 'commission_list'):
            self.assertEqual(self.get(self.agent, reverse('agent_portal:' + name)).status_code, 200)
        self.assertEqual(self.get(self.agent, reverse('agent_portal:lead_detail', args=[self.lead.pk])).status_code, 200)
        self.assertEqual(self.get(self.agent, reverse('agent_portal:lead_detail', args=[self.other_lead.pk])).status_code, 404)
        self.assertEqual(self.get(self.agent, reverse('dashboard:home')).status_code, 403)
        self.assertEqual(self.get(self.owner, reverse('agent_portal:home')).status_code, 403)
        page = self.get(self.agent2_view(), reverse('agent_portal:booking_list')).content.decode()
        self.assertNotIn(self.booking.booking_ref, page)  # another agent never sees this booking

    def agent2_view(self):
        return self.other_agent

    def test_agent_cannot_change_stage_or_mint_commission(self):
        self.client.force_login(self.agent)
        self.assertEqual(self.client.post(reverse('dashboard:lead_stage', args=[self.lead.pk]), {'pipeline_stage': 'lost'}).status_code, 403)
        r = self.client.post('/api/v1/commissions/', {'agent': self.agent.pk, 'booking_value': '9999'}, content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        r = self.client.get(reverse('dashboard:home'))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('accounts:login'), r['Location'])

    def test_login_lockout_after_five_failures(self):
        for _ in range(5):
            self.client.post(reverse('accounts:login'), {'username': 'mgr', 'password': 'wrong'})
        r = self.client.post(reverse('accounts:login'), {'username': 'mgr', 'password': PASSWORD})
        self.assertContains(r, 'Too many failed attempts')

    def test_logout_requires_post(self):
        self.client.force_login(self.manager)
        self.client.get(reverse('accounts:logout'))
        self.assertEqual(self.client.get(reverse('dashboard:home')).status_code, 200)
        self.client.post(reverse('accounts:logout'))
        self.assertEqual(self.client.get(reverse('dashboard:home')).status_code, 302)

    def test_branding_uses_app_name(self):
        r = self.get(self.manager, reverse('dashboard:home'))
        self.assertContains(r, 'Safari-Ops')
        self.assertNotContains(r, 'Safari Zangu')

    def test_custom_404(self):
        r = self.get(self.manager, '/dashboard/does-not-exist/')
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, 'Page not found', status_code=404)


class HardeningTests(TestCase):
    def test_bad_host_header_is_400_not_500(self):
        from django.test.utils import override_settings
        with override_settings(ALLOWED_HOSTS=['testserver']):
            self.assertEqual(self.client.get('/accounts/login/', HTTP_HOST='evil.example').status_code, 400)


class StaticAssetTests(TestCase):
    def test_js_has_no_template_leftovers(self):
        """admin-layout.js once shipped with PHP/<script> lines from the legacy layout, so none of its handlers ever ran."""
        import shutil
        import subprocess
        from pathlib import Path
        from django.conf import settings
        for path in Path(settings.BASE_DIR, 'static', 'js').glob('*.js'):
            src = path.read_text()
            self.assertNotIn('<?', src, path.name)
            self.assertNotIn('</script>', src, path.name)
            if shutil.which('node'):
                result = subprocess.run(['node', '--check', str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, f'{path.name}: {result.stderr}')


class SharedHostCookieTests(TestCase):
    def test_login_survives_another_apps_cookies_on_same_host(self):
        """Regression: on the shared demo server another app's 'csrftoken'/'sessionid' broke every login."""
        from django.conf import settings
        self.assertNotIn(settings.CSRF_COOKIE_NAME, ('csrftoken',))
        self.assertNotIn(settings.SESSION_COOKIE_NAME, ('sessionid',))
        user('cookieuser', 'manager')
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.cookies['csrftoken'] = 'x' * 32          # another app's cookies on the same IP
        c.cookies['sessionid'] = 'someone-else'
        page = c.get(reverse('accounts:login'))
        token = page.context['csrf_token']
        r = c.post(reverse('accounts:login'), {'username': 'cookieuser', 'password': PASSWORD, 'csrfmiddlewaretoken': token})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get(reverse('dashboard:home')).status_code, 200)
