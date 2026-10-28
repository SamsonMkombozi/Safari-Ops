from rest_framework import serializers

from .models import Accommodation, Activity, Itinerary, Package, ParkFee, SeasonalRate, Vehicle


class AccommodationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Accommodation
        fields = '__all__'


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = '__all__'


class ParkFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParkFee
        fields = '__all__'


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = '__all__'


class SeasonalRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeasonalRate
        fields = '__all__'


class ItinerarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Itinerary
        fields = ['id', 'name', 'slug', 'duration_days', 'overview', 'accommodation_level',
                   'days', 'includes', 'excludes', 'base_price_pax', 'is_active', 'sort_order']


class ItinerarySummarySerializer(serializers.ModelSerializer):
    """Lighter shape for embedding inside PackagePublicSerializer — day titles/locations only, no internal costing."""
    day_titles = serializers.SerializerMethodField()

    class Meta:
        model = Itinerary
        fields = ['id', 'name', 'duration_days', 'day_titles', 'includes', 'excludes']

    def get_day_titles(self, obj):
        return [
            {'day': d.get('day', i + 1), 'title': d.get('title') or d.get('location') or ''}
            for i, d in enumerate(obj.days or [])
        ]


class PackagePublicSerializer(serializers.ModelSerializer):
    """What an external site (WordPress/Joomla/anything) sees — full marketing content, no internal cost_breakdown."""
    itinerary = ItinerarySummarySerializer(read_only=True)

    class Meta:
        model = Package
        fields = ['id', 'slug', 'name', 'duration_days', 'short_description', 'overview',
                  'itinerary', 'accommodation_level', 'includes', 'excludes', 'price_notes',
                  'price_1pax', 'hero_image', 'gallery_images', 'is_featured']


class PackageAdminSerializer(serializers.ModelSerializer):
    """Full shape for the dashboard/API consumers who are staff — includes internal cost_breakdown and housekeeping flags."""
    class Meta:
        model = Package
        fields = '__all__'
