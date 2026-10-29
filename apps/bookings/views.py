import re

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.middleware import log_activity
from apps.core.permissions import IsStaffRole

from rest_framework.decorators import action

from . import services
from .models import Booking, BookingReminder, Payment, Quotation
from .serializers import (
    BookingReminderSerializer, BookingSerializer, BookingTrackingSerializer, PaymentSerializer,
    QuotationPublicSerializer, QuotationSerializer,
)

BOOKING_REF_RE = re.compile(r'^SZV[A-Z0-9]{4,17}$', re.IGNORECASE)


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.select_related('customer', 'package', 'itinerary').all()
    serializer_class = BookingSerializer
    permission_classes = [IsStaffRole]

    def perform_create(self, serializer):
        booking = serializer.save(created_by=self.request.user, booking_ref=services.generate_booking_ref())
        log_activity(self.request, self.request.user, 'create', 'Booking', booking.id, f'Created booking {booking.booking_ref}')

    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        """Same write path as the dashboard's Record Payment form — ledger row + amount_paid/status recompute."""
        booking = self.get_object()
        ser = PaymentSerializer(data={**request.data, 'booking': booking.pk})
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            booking, payment = services.record_payment(booking, d['amount'], d.get('method', 'bank_transfer'), d.get('reference', ''),
                                                       d.get('received_at'), d.get('notes', ''), request.user)
        except ValueError as exc:
            return Response({'success': False, 'message': str(exc)}, status=400)
        log_activity(request, request.user, 'create', 'Payment', payment.pk if payment else '', f'{booking.booking_ref} via API')
        return Response({'success': True, 'booking': BookingSerializer(booking).data,
                         'payment': PaymentSerializer(payment).data if payment else None})


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ledger — payments are only ever written through BookingViewSet.record_payment."""
    queryset = Payment.objects.select_related('booking').all()
    serializer_class = PaymentSerializer
    permission_classes = [IsStaffRole]


class QuotationViewSet(viewsets.ModelViewSet):
    queryset = Quotation.objects.select_related('customer', 'package', 'itinerary', 'vehicle').all()
    serializer_class = QuotationSerializer
    permission_classes = [IsStaffRole]

    def perform_create(self, serializer):
        quote = serializer.save(created_by=self.request.user, quote_ref=services.generate_quote_ref())
        log_activity(self.request, self.request.user, 'create', 'Quotation', quote.id, f'Created quotation {quote.quote_ref}')


class BookingReminderViewSet(viewsets.ModelViewSet):
    queryset = BookingReminder.objects.select_related('booking').all()
    serializer_class = BookingReminderSerializer
    permission_classes = [IsStaffRole]


class BookingTrackingView(APIView):
    """
    Public "Track My Booking" lookup — proof of ownership is booking_ref +
    the real tracking password (never ref+travel_date alone, which leaks
    far too easily). Heavily throttled per IP via the 'tracking' scope;
    on top of that, three wrong passwords for the SAME ref locks that ref
    out for 15 minutes regardless of which IP is trying, mirroring the
    legacy app's dual IP+account lockout. Lockout state lives in Django's
    cache framework (LocMemCache by default, correctly shared across
    worker processes the moment Redis/Memcached is configured — no code
    change needed when this scales past one process).
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'tracking'

    LOCKOUT_MAX_ATTEMPTS = 3
    LOCKOUT_MINUTES = 15

    def post(self, request):
        ref = str(request.data.get('ref', '')).strip().upper()
        password = str(request.data.get('password', '')).strip()

        if not ref or not password:
            return Response({'success': False, 'message': 'Booking reference and tracking password are required.'}, status=400)
        if not BOOKING_REF_RE.match(ref):
            return Response({'success': False, 'message': 'Invalid booking reference format.'}, status=400)

        cache_key = f'booking_track_attempts:{ref}'
        count = cache.get(cache_key, 0)
        if count >= self.LOCKOUT_MAX_ATTEMPTS:
            ttl = cache.ttl(cache_key) if hasattr(cache, 'ttl') else self.LOCKOUT_MINUTES * 60
            remaining = max(1, int((ttl or 0) / 60))
            return Response({'success': False, 'message': f'Too many failed attempts. Try again in {remaining} minute(s).'}, status=429)

        try:
            booking = Booking.objects.get(booking_ref=ref)
        except Booking.DoesNotExist:
            booking = None

        if not booking or not booking.check_tracking_password(password):
            cache.set(cache_key, count + 1, timeout=self.LOCKOUT_MINUTES * 60)
            return Response({'success': False, 'message': 'No booking found with those details.'}, status=404)

        cache.delete(cache_key)
        return Response({'success': True, 'booking': BookingTrackingSerializer(booking).data})


class QuotationPublicView(APIView):
    """The client-facing quote link: /api/v1/quotations/view/<token>/ — access is by the unguessable public_token only, numeric id never accepted. Mirrors api/quote_view.php exactly."""
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'quote_view'

    def get(self, request, token):
        if not re.match(r'^[a-f0-9]{48}$', token):
            return Response({'success': False, 'message': 'Quotation not found.'}, status=404)
        try:
            quote = Quotation.objects.get(public_token=token)
        except Quotation.DoesNotExist:
            return Response({'success': False, 'message': 'Quotation not found.'}, status=404)
        quote.record_view()
        return Response({'success': True, 'quotation': QuotationPublicSerializer(quote).data})
