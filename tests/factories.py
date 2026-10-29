"""Minimal, deterministic fixtures shared by the test modules."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User
from apps.packages.models import Accommodation, Itinerary, Package, ParkFee, Vehicle

PASSWORD = 'Test-Pass-2026!'


def user(username, role, **extra):
    u = User(username=username, role=role, email=f'{username}@test.example.com', first_name=username.title(), **extra)
    u.set_password(PASSWORD)
    u.save()
    return u


def catalog():
    """One 2-night itinerary: per-room lodge + per-person lodge, a vehicle, a park with child fee, one paid activity, meals."""
    Accommodation.objects.create(name='Room Lodge', rate_per_room=200, single_supplement=50, child_rate=40)
    Accommodation.objects.create(name='PP Camp', rate_per_person=150, single_supplement=60, child_rate=50)
    Vehicle.objects.create(vehicle_key='lc', name='Cruiser', daily_rate=250)
    ParkFee.objects.create(park_key='srg', name='Serengeti NP', adult_fee=82, child_fee=20, resident_adult=10, resident_child=5)
    itin = Itinerary.objects.create(name='Test Trip', slug='test-trip', duration_days=3, days=[
        {'day': 1, 'title': 'Day 1', 'location': 'Arusha', 'accommodation_name': 'Room Lodge', 'accommodation_rate': 200,
         'accommodation_rooms': 1, 'vehicle_name': 'Cruiser', 'vehicle_rate': 250, 'meals_cost_pp': 20},
        {'day': 2, 'title': 'Day 2', 'location': 'Serengeti', 'accommodation_name': 'PP Camp', 'accommodation_rate': 150,
         'vehicle_name': 'Cruiser', 'vehicle_rate': 250, 'park_fee_name': 'Serengeti NP', 'park_adult_fee': 82,
         'activities': [{'name': 'Balloon', 'type': 'paid', 'price_pp': 500}, {'name': 'Walk', 'type': 'included'},
                        {'name': 'Spa', 'type': 'optional', 'price_pp': 90}]},
        {'day': 3, 'title': 'Day 3', 'location': 'Arusha', 'vehicle_name': 'Cruiser', 'vehicle_rate': 250},
    ])
    return Package.objects.create(slug='test-pkg', name='Test Package', duration_days=3, itinerary=itin,
                                  accommodation_level='luxury', price_1pax=Decimal('1000'))


def future(days=60):
    return timezone.localdate() + timedelta(days=days)
