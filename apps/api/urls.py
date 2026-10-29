from django.urls import include, path
from rest_framework import routers
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from apps.bookings.views import (
    BookingReminderViewSet, BookingTrackingView, BookingViewSet, PaymentViewSet, QuotationPublicView, QuotationViewSet,
)
from apps.content.views import (
    ContactMessageViewSet, CustomSafariRequestViewSet, EmailTemplateViewSet, TeamMemberViewSet,
)
from apps.crm.views import AgentTargetViewSet, CommissionViewSet, CustomerViewSet, LeadViewSet
from apps.packages.views import (
    AccommodationViewSet, ActivityViewSet, ItineraryViewSet, PackageViewSet, ParkFeeViewSet,
    SeasonalRateViewSet, VehicleViewSet,
)

router = routers.DefaultRouter()

# Catalog — the data an external site/CMS integration cares about most
router.register('packages', PackageViewSet, basename='package')
router.register('itineraries', ItineraryViewSet, basename='itinerary')
router.register('accommodations', AccommodationViewSet, basename='accommodation')
router.register('vehicles', VehicleViewSet, basename='vehicle')
router.register('park-fees', ParkFeeViewSet, basename='parkfee')
router.register('activities', ActivityViewSet, basename='activity')
router.register('seasonal-rates', SeasonalRateViewSet, basename='seasonalrate')
router.register('team', TeamMemberViewSet, basename='teammember')

# Guest-facing form submissions (contact, custom safari request)
router.register('contact-messages', ContactMessageViewSet, basename='contactmessage')
router.register('custom-safari-requests', CustomSafariRequestViewSet, basename='customsafarirequest')

# Staff/agent-only business data
router.register('bookings', BookingViewSet, basename='booking')
router.register('payments', PaymentViewSet, basename='payment')
router.register('booking-reminders', BookingReminderViewSet, basename='bookingreminder')
router.register('quotations', QuotationViewSet, basename='quotation')
router.register('leads', LeadViewSet, basename='lead')
router.register('commissions', CommissionViewSet, basename='commission')
router.register('customers', CustomerViewSet, basename='customer')
router.register('agent-targets', AgentTargetViewSet, basename='agenttarget')
router.register('email-templates', EmailTemplateViewSet, basename='emailtemplate')

app_name = 'api'

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # Public guest-facing lookups — not part of the router since they're
    # not standard CRUD (proof-of-ownership gated, heavily throttled).
    path('bookings/track/', BookingTrackingView.as_view(), name='booking_track'),
    path('quotations/view/<str:token>/', QuotationPublicView.as_view(), name='quotation_view'),

    path('', include(router.urls)),
]
