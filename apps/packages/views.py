from rest_framework import viewsets

from apps.api.permissions import IsStaffForWrite

from .models import Accommodation, Activity, Itinerary, Package, ParkFee, SeasonalRate, Vehicle
from .serializers import (
    AccommodationSerializer, ActivitySerializer, ItinerarySerializer, PackageAdminSerializer,
    PackagePublicSerializer, ParkFeeSerializer, SeasonalRateSerializer, VehicleSerializer,
)


class PackageViewSet(viewsets.ModelViewSet):
    """
    Public-catalog endpoint. GET is open to anyone with a valid API key
    (external CMS) or a logged-in user; only staff can create/update.
    An external integration gets the lighter PackagePublicSerializer
    (no internal cost_breakdown); a logged-in staff/agent user gets the
    full admin shape.
    """
    queryset = Package.objects.filter(is_active=True).select_related('itinerary')
    permission_classes = [IsStaffForWrite]
    lookup_field = 'slug'

    def get_serializer_class(self):
        user = self.request.user
        if user and user.is_authenticated and getattr(user, 'is_staff_role', False):
            return PackageAdminSerializer
        return PackagePublicSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        featured = self.request.query_params.get('featured')
        if featured is not None:
            qs = qs.filter(is_featured=featured.lower() in ('1', 'true', 'yes'))
        return qs.order_by('sort_order', 'id')


class ItineraryViewSet(viewsets.ModelViewSet):
    queryset = Itinerary.objects.filter(is_active=True)
    serializer_class = ItinerarySerializer
    permission_classes = [IsStaffForWrite]


class AccommodationViewSet(viewsets.ModelViewSet):
    queryset = Accommodation.objects.filter(is_active=True)
    serializer_class = AccommodationSerializer
    permission_classes = [IsStaffForWrite]


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.filter(is_active=True)
    serializer_class = VehicleSerializer
    permission_classes = [IsStaffForWrite]


class ParkFeeViewSet(viewsets.ModelViewSet):
    queryset = ParkFee.objects.filter(is_active=True)
    serializer_class = ParkFeeSerializer
    permission_classes = [IsStaffForWrite]


class ActivityViewSet(viewsets.ModelViewSet):
    queryset = Activity.objects.filter(is_active=True)
    serializer_class = ActivitySerializer
    permission_classes = [IsStaffForWrite]


class SeasonalRateViewSet(viewsets.ModelViewSet):
    queryset = SeasonalRate.objects.all()
    serializer_class = SeasonalRateSerializer
    permission_classes = [IsStaffForWrite]
