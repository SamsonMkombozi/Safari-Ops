from decimal import Decimal

from django.test import TestCase

from apps.bookings import pricing

from .factories import catalog


class PricingTests(TestCase):
    def setUp(self):
        self.pkg = catalog()
        self.days = self.pkg.itinerary.days

    def amounts(self, built):
        return {li['description']: li['amount'] for li in built['line_items']}

    def test_two_adults_itemised(self):
        built = pricing.build(self.days, 2, 0)
        a = self.amounts(built)
        self.assertEqual(a['Accommodation – Room Lodge'], 200)                     # per-room model
        self.assertEqual(a['Accommodation – PP Camp (Per Person Sharing)'], 300)  # per-person sharing
        self.assertEqual(a['Cruiser'], 750)                                        # itemised vehicle components
        self.assertEqual(a['Serengeti NP Entry Fees'], 164)
        self.assertEqual(a['Balloon'], 1000)
        self.assertEqual(a['Service Charge (Adults)'], 200)
        self.assertNotIn('Spa', a)                                                 # optional activities never priced
        self.assertEqual(sum(a.values()), 2654)
        self.assertEqual(pricing.supplier_cost(built['line_items']), 2454)         # everything but our service charge
        self.assertIn('Walk', built['included_activities'])

    def test_solo_adult_with_child_supplements(self):
        a = self.amounts(pricing.build(self.days, 1, 1))
        self.assertEqual(a['Single Supplement – PP Camp'], 60)
        self.assertEqual(a['Single Supplement – Room Lodge'], 50)
        self.assertEqual(a['Child Rate – PP Camp'], 50)
        self.assertEqual(a['Serengeti NP Entry Fees'], 102)  # 82 adult + 20 child
        self.assertEqual(a['Service Charge (Children)'], 100)

    def test_eac_resident_park_rate(self):
        a = self.amounts(pricing.build(self.days, 2, 0, nationality='Tanzania'))
        self.assertEqual(a['Serengeti NP Entry Fees (Resident Rate)'], 20)

    def test_totals_markup_discount_vat_deposit(self):
        t = pricing.totals([{'amount': 1000}], discount_pct=10, markup_pct=20)
        self.assertEqual(t['markup'], 200)
        self.assertEqual(t['discount'], 120)          # 10% of the marked-up 1200
        self.assertEqual(t['vat'], 194.4)             # 18% of 1080
        self.assertEqual(t['grand_total'], 1274.4)
        self.assertEqual(t['deposit'], 318.6)         # default 25%
        self.assertEqual(t['balance'], 955.8)

    def test_flat_price_fallback_without_itinerary(self):
        self.pkg.itinerary = None
        self.pkg.save()
        built, t = pricing.price_package(self.pkg, 2, 1)
        self.assertEqual(t['grand_total'], 3000)
        self.assertEqual(Decimal(str(t['deposit'])), Decimal('750'))
