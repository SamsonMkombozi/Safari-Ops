from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel

ACCOMMODATION_LEVELS = [
    ('budget', 'Budget'),
    ('midrange', 'Mid-Range'),
    ('highend', 'High-End'),
    ('ultra_luxury', 'Ultra Luxury'),
]


class Accommodation(TimeStampedModel):
    name = models.CharField(max_length=200)
    level = models.CharField(max_length=20, choices=ACCOMMODATION_LEVELS, default='midrange')
    category = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=150, blank=True)
    park_key = models.CharField(max_length=50, blank=True)
    rate_per_room = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rate_per_person = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rate_low = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    rate_high = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    single_supplement = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    child_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    meal_plan = models.CharField(max_length=10, default='fb')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    images = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Vehicle(TimeStampedModel):
    LEVEL_CHOICES = [('standard', 'Standard'), ('comfort', 'Comfort'), ('luxury', 'Luxury')]
    vehicle_key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    capacity = models.PositiveSmallIntegerField(default=6)
    daily_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fuel_cost_day = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    driver_cost_day = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='standard')
    is_active = models.BooleanField(default=True)
    images = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ParkFee(TimeStampedModel):
    park_key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    country = models.CharField(max_length=50, default='Tanzania')
    adult_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    child_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    resident_adult = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    resident_child = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fee_unit = models.CharField(max_length=30, default='per_person_per_entry')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Activity(TimeStampedModel):
    PRICE_UNIT_CHOICES = [('per_person', 'Per Person'), ('per_group', 'Per Group'), ('flat', 'Flat')]
    activity_key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    price_unit = models.CharField(max_length=20, choices=PRICE_UNIT_CHOICES, default='per_person')
    category = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class SeasonalRate(models.Model):
    name = models.CharField(max_length=50)
    season_key = models.SlugField(max_length=20, unique=True)
    multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    start_month = models.PositiveSmallIntegerField(null=True, blank=True)
    end_month = models.PositiveSmallIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Itinerary(TimeStampedModel):
    name = models.CharField(max_length=200, help_text='e.g. Classic Safari — 5 Days')
    slug = models.SlugField(max_length=100, unique=True)
    duration_days = models.PositiveSmallIntegerField(default=5)
    overview = models.TextField(blank=True)
    accommodation_level = models.CharField(max_length=50, choices=ACCOMMODATION_LEVELS, default='midrange')
    days = models.JSONField(default=list, blank=True, help_text='Array of day objects: title, location, description, accommodation, vehicle, park_fee, activities.')
    includes = models.JSONField(default=list, blank=True)
    excludes = models.JSONField(default=list, blank=True)
    base_price_pax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name_plural = 'Itineraries'

    def __str__(self):
        return self.name


class Package(TimeStampedModel):
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    duration_days = models.PositiveSmallIntegerField()
    short_description = models.TextField(blank=True)
    overview = models.TextField(blank=True)
    itinerary = models.ForeignKey(Itinerary, null=True, blank=True, on_delete=models.SET_NULL, related_name='packages')
    accommodation_level = models.CharField(max_length=50, choices=ACCOMMODATION_LEVELS, blank=True)
    includes = models.JSONField(default=list, blank=True)
    excludes = models.JSONField(default=list, blank=True)
    cost_breakdown = models.JSONField(default=dict, blank=True, help_text='accommodations[], transport, park_fees[], activities[], other[]')
    price_notes = models.TextField(blank=True)
    price_1pax = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)],
                                      help_text='"Starting from" single-traveler rate — the real per-booking price is computed fresh from the actual party size.')
    hero_image = models.CharField(max_length=255, blank=True)
    gallery_images = models.JSONField(default=list, blank=True)
    is_featured = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.name
